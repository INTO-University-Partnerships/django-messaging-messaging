import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http.response import HttpResponseForbidden, HttpResponseRedirect, HttpResponse, Http404
from django.shortcuts import render, get_object_or_404
from django.template.defaultfilters import linebreaksbr
from django.utils import timezone
from django.utils.html import escape, strip_tags
from django.utils.translation import gettext as _
from django.utils.encoding import force_str
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from vle.models import CourseKVStore, GroupKVStore
from vle.decorators import basic_auth
from .models import Message, MessageItem
from .models import MessageTargetUser, MessageTargetGroup, MessageTargetCourse
from .models import delimiter
from .search import search


@login_required
@require_http_methods(['GET'])
def messaging(request):
    data = {
        'trans': [
            ('empty_inbox', _('There are no messages in your inbox')),
            ('empty_thread', _('There are no messages in this thread')),
        ],
        'show_message_item_ids': settings.DEBUG,
        'angularjs_debug': settings.ANGULARJS_DEBUG,
    }
    return render(request, 'messaging.html', data)


@login_required
@require_http_methods(['GET'])
def read(request, message_id):
    """
    redirect the user to a deep link within the messaging app in order for them to read the thread
    """
    message = get_object_or_404(Message, pk=message_id)
    message_items = MessageItem.objects.filter(user=request.user, message=message).order_by('-message__sent')[:1]
    if len(message_items) != 1:
        raise Http404
    return HttpResponseRedirect('{0}#/read/{1}'.format(reverse('messaging_home'), message_items[0].id))


@require_http_methods(['GET'])
def partial_base(request):
    """
    only used as a base URL for requests for partials
    """
    return HttpResponseForbidden()


@require_http_methods(['GET'])
def partial(request, template):
    """
    serve a partial (which is just a template in the 'partials/' subdirectory with a '.html' file extension)
    """
    return render(request, ''.join(['partials/', template, '.html']))


@login_required
@require_http_methods(['POST'])
def search_recipient(request):
    """
    search for potential recipients (users, groups, courses)
    """

    # get the query 'q' from the request
    data = json.loads(force_str(request.body))
    q = data.get('q', '')
    recipients = data.get('recipients', [])
    page = data.get('page', 0)

    # get recipients, count and max number given a search query and a list of recipients to exclude
    (recipients, count, per_page) = search(q=q, exclude=recipients, user=request.user, page=page)

    # JSON encode search results and return JSON response
    data = json.dumps({
        'searchResults': recipients,
        'count': count,
        'perPage': per_page,
    })
    return HttpResponse(data, content_type='application/json')


@login_required
@require_http_methods(['POST'])
def send_message(request):
    """
    send a new message
    """

    # get the data from the request
    data = json.loads(force_str(request.body))
    recipients = data.get('recipients', [])
    target_all = data.get('targetAll', False)
    subject = strip_tags(data.get('subject', ''))
    body = strip_tags(data.get('body', ''))
    miid = data.get('miid', None)

    # only super users can target all (i.e. send a message to everyone)
    if target_all and not request.user.is_superuser:
        return HttpResponse(json.dumps({
            'errorMessage': _('Only super users can send messages to everyone'),
            'type': 'error'
        }), content_type='application/json', status=403)

    # find the parent message that's being replied to (if any)
    parent = None
    if miid:
        (mi, parent, response) = _get_message_item_and_message(request.user, miid)
        if response:
            return response

    # 'send' (i.e. create) the message
    if target_all:
        Message.send_message_all(request.user, subject, body, parent)
    else:
        Message.send_message(request.user, recipients, subject, body, parent, send_email=True)

    # return JSON response
    return HttpResponse(json.dumps({
        'successMessage': _('Message sent successfully!')
    }), content_type='application/json')


@csrf_exempt  # has to be the first decorator, apparently, or it doesn't work
@basic_auth(settings.NOTIFICATION_BASIC_AUTH)
@require_http_methods(['POST'])
def send_notification(request):
    """
    send a new notification to some users given by usernames
    can be invoked from curl on the command line with:
    curl -X POST http://localhost:8000/messaging/send/notification/ -u username:password -d '{"url": "http://foobar.com/blah", "subject": "my subject", "body": "my body"}'
    """

    # get the data from the request
    data = json.loads(force_str(request.body))
    usernames = data.get('usernames', [])
    url = data.get('url', '')
    subject = data.get('subject', '')
    body = data.get('body', '')

    # 'send' (i.e. create) the notifications
    Message.send_notification(usernames, url, subject, body)

    # return JSON response
    return HttpResponse(json.dumps({
        'successMessage': _('Notification sent successfully!')
    }), content_type='application/json')


@login_required
@require_http_methods(['GET'])
def get_notifications(request):
    """
    get notifications for the logged in user
    """

    # get data from the request
    page = int(request.GET['page']) if 'page' in request.GET else 0
    per_page = int(request.GET['per_page']) if 'per_page' in request.GET else 10

    # get notifications for the logged in user
    (notifications, total) = MessageItem.get_notifications(request.user)

    # determine pagination parameters and use these to get one page of inbox items
    offset = page * per_page
    limit = offset + per_page
    notifications = notifications[offset:limit]

    # convert to a list of dictionaries
    notifications = [
        {
            u'id': mi.id,
            u'subject': mi.message.subject,
            u'body': mi.message.body,
            u'url': mi.message.url,
            u'sent': mi.message.get_sent_display(),
            u'read': mi.read is not None,
        }
        for mi in notifications
    ]

    # return JSON response
    data = json.dumps({
        'notifications': notifications,
        'total': total,
    })
    return HttpResponse(data, content_type='application/json')


@login_required
@require_http_methods(['GET'])
def mark_notification_read(request):
    """
    marks the given notification as read
    """

    # get data from the request
    miid = int(request.GET['miid']) if 'miid' in request.GET else 0

    # get MessageItem and Message from miid
    (mi, m, response) = _get_message_item_and_message(request.user, miid)
    if response:
        return response

    # mark read (if it isn't already)
    if mi.read is None:
        mi.read = timezone.now()
        mi.save()

    # return JSON response
    return HttpResponse(json.dumps({
        'successMessage': _('Notification marked as read successfully!')
    }), content_type='application/json')


@login_required
@require_http_methods(['GET'])
def get_inbox(request):
    """
    get threads that comprise the logged in user's inbox
    """

    # get data from the request
    page = int(request.GET['page']) if 'page' in request.GET else 0
    per_page = int(request.GET['per_page']) if 'per_page' in request.GET else 10
    sort_field = request.GET['sort_field'] if 'sort_field' in request.GET else 'date'
    sort_dir = request.GET['sort_dir'] if 'sort_dir' in request.GET else 'desc'

    # get inbox for the logged in user
    (inbox, total) = MessageItem.get_inbox(request.user, sort_field, sort_dir)

    # determine pagination parameters and use these to get one page of inbox items
    offset = page * per_page
    limit = offset + per_page
    inbox_page = inbox[offset:limit]

    # get message tree ids for each thread in the inbox page
    tree_ids = [mi.message.tree_id for mi in inbox_page]

    # get counts of undeleted message items and unread message items in each thread in the inbox page
    undeleted_dict = MessageItem.get_undeleted_message_item_count_for_message_trees(request.user, tree_ids)
    unread_dict = MessageItem.get_unread_message_item_count_for_message_trees(request.user, tree_ids)

    # convert inbox page to a list of dictionaries
    messages = [
        {
            u'id': mi.id,
            u'sender': ' '.join([mi.message.user.first_name, mi.message.user.last_name]),
            u'subject': mi.message.subject,
            u'sent': mi.message.get_sent_display(),
            u'count': 0 if mi.message.tree_id not in undeleted_dict else undeleted_dict[mi.message.tree_id],
            u'unread': 0 if mi.message.tree_id not in unread_dict else unread_dict[mi.message.tree_id],
        }
        for mi in inbox_page
    ]

    # return JSON response
    data = json.dumps({
        'messages': messages,
        'total': total,
    })
    return HttpResponse(data, content_type='application/json')


@login_required
@require_http_methods(['GET'])
def get_unread_count(request):
    """
    gets the number of unread messages (or unread notifications) for the logged in user
    """

    # get whether we're counting unread messages (or unread notifications) from the request
    notifications = 'n' in request.GET

    # count the number of unread (and undeleted) items
    count = MessageItem.objects.filter(message__is_notification=notifications, user=request.user, read=None, deleted=None).count()

    # return JSON response
    data = json.dumps({
        'count': count,
    })
    return HttpResponse(data, content_type='application/json')


@login_required
@require_http_methods(['GET'])
def get_thread(request):
    """
    given a message item in a thread, gets the entire corresponding thread
    """

    # get data from the request
    miid = int(request.GET['miid']) if 'miid' in request.GET else 0

    # get MessageItem and Message from miid
    (mi, m, response) = _get_message_item_and_message(request.user, miid)
    if response:
        return response

    # store the original subject
    original_subject = mi.message.subject

    # get thread
    (thread, total) = mi.get_thread()

    # convert thread to a list of dictionaries
    messages = [
        {
            u'id': mi.id,
            u'sender': ' '.join([mi.message.user.first_name, mi.message.user.last_name]),
            u'subject': mi.message.subject,
            u'body': linebreaksbr(escape(mi.message.body)),
            u'sent': mi.message.get_sent_display(),
            u'read': mi.read is not None,
        }
        for mi in thread
    ]

    # mark thread as read
    MessageItem.mark_all_read(thread)

    # return JSON response
    data = json.dumps({
        'subject': original_subject,
        'messages': messages,
        'total': total,
    })
    return HttpResponse(data, content_type='application/json')


@login_required
@require_http_methods(['GET'])
def get_reply_info(request):
    """
    given a message item, gets relevant information needed in order to compose a reply to the corresponding message
    gets the sender, the message's recipients and its subject and body
    """

    # get data from the request
    miid = int(request.GET['miid']) if 'miid' in request.GET else 0

    # get MessageItem and Message from miid
    (mi, m, response) = _get_message_item_and_message(request.user, miid)
    if response:
        return response

    # get list of user, group and course recipients
    recipients = [{
        u'name': u' '.join([m.user.first_name, m.user.last_name]),
        u'id': m.user.pk,
        u'type': u'u'
    }]
    recipients.extend([
        {
            u'name': u' '.join([tu.user.first_name, tu.user.last_name]),
            u'id': tu.user.pk,
            u'type': u'u'
        }
        for tu in MessageTargetUser.objects.filter(message=m).order_by('user__id')
        if tu.user.id != m.user.id and tu.user.id != request.user.id
    ])
    recipients.extend([
        {
            u'name': GroupKVStore.objects.get(vle_course_id=tg.vle_course_id, vle_group_id=tg.vle_group_id).name,
            u'id': delimiter.join([tg.vle_course_id, tg.vle_group_id]),
            u'type': u'g'
        }
        for tg in MessageTargetGroup.objects.filter(message=m).order_by('id')
        if GroupKVStore.objects.filter(vle_course_id=tg.vle_course_id, vle_group_id=tg.vle_group_id).exists()
    ])
    recipients.extend([
        {
            u'name': CourseKVStore.objects.get(vle_course_id=tc.vle_course_id).name,
            u'id': tc.vle_course_id,
            u'type': u'c'
        }
        for tc in MessageTargetCourse.objects.filter(message=m).order_by('id')
        if CourseKVStore.objects.filter(vle_course_id=tc.vle_course_id).exists()
    ])

    # return JSON response
    data = json.dumps({
        'sender': ' '.join([m.user.first_name, m.user.last_name]),
        'recipients': recipients,
        'subject': m.subject,
        'body': linebreaksbr(escape(m.body))
    })
    return HttpResponse(data, content_type='application/json')


@login_required()
@require_http_methods(['GET'])
def delete_message_item(request):
    """
    given a message item, either marks it as deleted, or marks the entire corresponding thread as deleted
    """

    # get data from the request
    miid = int(request.GET['miid']) if 'miid' in request.GET else 0
    thread = 'thread' in request.GET

    # get MessageItem and Message from miid
    (mi, m, response) = _get_message_item_and_message(request.user, miid)
    if response:
        return response

    # mark the message item, or the entire thread, as deleted
    if thread:
        messages = Message.objects.filter(is_notification=False, tree_id=m.tree_id)
        message_items = MessageItem.objects.filter(user=request.user, deleted__isnull=True, message__in=messages)
    else:
        message_items = [mi]
    MessageItem.mark_all_deleted(message_items)

    # determine whether the message is a notification
    entity = 'Notification' if m.is_notification else 'Message'

    # return JSON response
    return HttpResponse(json.dumps({
        'successMessage': _('Conversation deleted!' if thread else ('%s deleted!' % entity))
    }), content_type='application/json')


def _get_message_item_and_message(user, miid):
    """
    given a user and a MessageItem id, gets a MessageItem and its corresponding Message
    if a MessageItem doesn't exist with the given miid, returns a 404
    if a MessageItem does exist, but is not owned by the given user, returns a 403
    """

    # ensure MessageItem exists
    try:
        mi = MessageItem.objects.get(id=miid)
    except MessageItem.DoesNotExist:
        response = HttpResponse(json.dumps({
            'errorMessage': _('Message item not found'),
            'type': 'warning'
        }), content_type='application/json', status=404)
        return None, None, response

    # ensure MessageItem is owned by the given user
    try:
        m = Message.objects.get(messageitem__id=miid, messageitem__user=user)
    except Message.DoesNotExist:
        response = HttpResponse(json.dumps({
            'errorMessage': _('Access denied'),
            'type': 'error'
        }), content_type='application/json', status=403)
        return mi, None, response

    return mi, m, None
