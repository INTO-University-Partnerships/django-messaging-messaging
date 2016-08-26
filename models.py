import re

from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.conf import settings
from django.core.mail import send_mass_mail
from django.core.urlresolvers import reverse
from django.db import models, connection
from django.utils import timezone
from django.template import loader
from django.utils.encoding import python_2_unicode_compatible

from mptt.models import MPTTModel, TreeForeignKey

from vle.models import CourseMember, GroupMember, expand_user_group_course_ids_to_user_ids


date_format = '%d/%m/%Y %H:%M:%S'
delimiter = '::'


@python_2_unicode_compatible
class Message(MPTTModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True)
    is_notification = models.BooleanField(default=False)
    url = models.URLField(blank=True)
    subject = models.CharField(max_length=200, blank=True)
    body = models.TextField(blank=True)
    sent = models.DateTimeField(auto_now_add=True, db_index=True)
    target_all = models.BooleanField(default=False, db_index=True)
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children')

    def __str__(self):
        t = (
            u'Notification' if self.is_notification else u'Message',
            self.subject,
            self.sent.strftime(date_format),
        )
        return u'(%s) subject "%s" sent @ %s' % t

    def get_sent_display(self):
        """
        if it's today, return the time
        otherwise, return the date
        """
        fmt = '%H:%M' if self.sent.date() == timezone.now().date() else '%a %d/%m'
        return timezone.localtime(self.sent).strftime(fmt)

    @classmethod
    def send_message(cls, sender, recipients, subject, body, parent=None, send_email=False):
        # create one Message
        message = Message.objects.create(user=sender, subject=subject, body=body, parent=parent)

        # TODO create one MessageAttachment per attachment

        # get a list of ids of each user, course and group recipient and create message items based on those
        f = lambda _type: [r.get('id') for r in recipients if r.get('id', '') and r.get('type', '') == _type]
        user_ids = f(u'u')
        group_ids = f(u'g')
        course_ids = f(u'c')
        all_user_ids = expand_user_group_course_ids_to_user_ids(delimiter, user_ids, group_ids, course_ids)
        MessageItem.create_message_items(message, all_user_ids)

        # email the message thread
        if send_email:
            Message.email_thread(message, all_user_ids)

        # create one 'source' MessageItem for the sender if the sender wasn't a recipient
        if not MessageItem.objects.filter(message=message, user=sender).exists():
            MessageItem.objects.create(user=sender, message=message, source=True, read=timezone.now())

        # create exactly one MessageTargetUser per user recipient
        for _id in user_ids:
            MessageTargetUser.objects.create(user=get_user_model().objects.get(pk=_id), message=message)

        # create exactly one MessageTargetCourse per course recipient
        for _id in course_ids:
            MessageTargetCourse.objects.create(vle_course_id=_id, message=message)

        # create exactly one MessageTargetGroup per group recipient
        for _id in map(lambda p: p.split(delimiter), group_ids):
            MessageTargetGroup.objects.create(vle_course_id=_id[0], vle_group_id=_id[1], message=message)

        # return the newly created message
        return message

    @classmethod
    def send_message_all(cls, sender, subject, body, parent=None):
        # create one Message
        message = Message.objects.create(user=sender, subject=subject, body=body, target_all=True, parent=parent)

        # TODO create one MessageAttachment per attachment

        # create exactly one MessageItem per user (except (other) super users)
        for u in get_user_model().objects.filter(is_superuser=False):
            MessageItem.objects.create(user=u, message=message)

        # return the newly created message
        return message

    @classmethod
    def email_thread(cls, message, all_user_ids):
        # use mptt to get ancestors of the message (including the message itself)
        messages = message.get_ancestors(ascending=True, include_self=True)

        # build email body
        c = {
            'wwwroot': settings.WWWROOT,
            'messages': messages,
            'link': reverse('read_message', args=(message.id,))
        }
        subject = ''.join(loader.render_to_string('messaging/email/subject.txt', c).splitlines())
        email_body = loader.render_to_string('messaging/email/body.txt', c)

        # send mass mail
        emails = get_user_model().objects.filter(pk__in=all_user_ids).values_list('email', flat=True)
        l = [(subject, email_body, None, [email]) for email in emails]
        send_mass_mail(tuple(l), fail_silently=True)

    @classmethod
    def send_notification(cls, usernames, url, subject, body):
        # create one notification
        notification = Message.objects.create(is_notification=True, url=url, subject=subject, body=body)

        # send a MessageItem to each user
        for username in usernames:
            try:
                user = get_user_model().objects.get(username=username)
                MessageItem.objects.get_or_create(user=user, message=notification)
            except get_user_model().DoesNotExist:
                pass

        # return the newly created notification
        return notification


@python_2_unicode_compatible
class MessageAttachment(models.Model):
    message = models.ForeignKey(Message)
    file = models.FileField(upload_to='%Y/%m/%d', storage=FileSystemStorage(location=settings.MESSAGE_ATTACHMENT_ROOT))

    def __str__(self):
        t = (
            self.message.subject,
            self.file,
        )
        return u'subject "%s" attachment "%s"' % t


@python_2_unicode_compatible
class MessageItem(models.Model):
    message = models.ForeignKey(Message)
    user = models.ForeignKey(settings.AUTH_USER_MODEL)
    source = models.BooleanField(default=False)
    read = models.DateTimeField(null=True, blank=True, db_index=True)
    deleted = models.DateTimeField(null=True, blank=True, db_index=True)

    def get_thread(self):
        """
        Gets a thread (a list of undeleted message items) given by self.message.
        To do this, we select all undeleted message items (belonging to self.user) that have a message.tree_id
        equal to self.message.tree_id.
        The ordering is newest first, like OWA (as opposed to gmail, which orders by oldest first).
        """

        # query
        sql = """
            FROM messaging_messageitem mi1
            INNER JOIN messaging_message m1
                ON m1.id = mi1.message_id
                AND m1.is_notification = %s
            INNER JOIN messaging_message m2
                ON m2.tree_id = m1.tree_id
                AND m2.is_notification = %s
            INNER JOIN messaging_messageitem mi2
                ON mi2.message_id = m2.id
                AND mi2.user_id = mi1.user_id
                AND mi2.deleted IS NULL
            WHERE mi1.id = %s
        """

        # get items
        params = [False, False, self.id]
        items = MessageItem.objects.raw(''.join(['SELECT mi2.*', sql, ' ORDER BY m2.sent DESC']), params)

        # get count
        cursor = connection.cursor()
        cursor.execute(''.join(['SELECT COUNT(mi2.id)', sql]), params)
        count = cursor.fetchone()

        # return a pair
        return items, count[0]

    @classmethod
    def mark_all_read(cls, message_items):
        """
        marks each of the given message items as read
        """
        unread = filter(lambda mi: mi.read is None, message_items)
        n = timezone.now()
        for message_item in unread:
            message_item.read = n
            message_item.save()

    @classmethod
    def mark_all_deleted(cls, message_items):
        """
        marks each of the given message items as deleted
        """
        unread = filter(lambda mi: mi.deleted is None, message_items)
        n = timezone.now()
        for message_item in unread:
            message_item.deleted = n
            message_item.save()

    @classmethod
    def create_message_items(cls, message, all_user_ids):
        """
        create exactly one MessageItem per user
        """
        for _id in all_user_ids:
            MessageItem.objects.create(user=get_user_model().objects.get(pk=_id), message=message)

    @classmethod
    def get_notifications(cls, user):
        """
        gets the message items which comprise the given user's notifications
        """
        mi = MessageItem.objects.filter(message__is_notification=True, user=user, deleted=None).order_by('-message__sent')
        return mi, mi.count()

    @classmethod
    def get_inbox(cls, user, sort_field='date', sort_dir='desc'):
        """
        gets the message items which comprise the given user's inbox
        main query: select all the message items that should appear in the given user's inbox
        sub query: select the most recently sent message (that was sent to the given user) within the thread
        """

        # query
        sql = """
            FROM messaging_messageitem mi
            INNER JOIN messaging_message m
                ON mi.message_id = m.id
            INNER JOIN auth_user u
                ON u.id = m.user_id
            WHERE mi.user_id = %s
                AND m.is_notification = %s
                AND m.id = (
                    SELECT m1.id
                    FROM messaging_message m1
                    INNER JOIN messaging_messageitem mi1
                        ON mi1.message_id = m1.id
                    WHERE mi1.user_id = mi.user_id
                        AND m1.is_notification = %s
                        AND m1.tree_id = m.tree_id
                        AND mi1.deleted IS NULL
                        AND mi1.source = %s
                    ORDER BY m1.sent DESC
                    LIMIT 1
                )
        """

        # determine order by clause
        order_by = {
            'date asc': 'm.sent',
            'date desc': 'm.sent DESC',
            'sender asc': 'u.first_name, u.last_name',
            'sender desc': 'u.first_name DESC, u.last_name DESC',
        }
        order_by_clause = order_by[' '.join([sort_field, sort_dir])]

        # get items
        params = [user.id, False, False, False]
        items = MessageItem.objects.raw(''.join(['SELECT mi.*', sql, ' ORDER BY ', order_by_clause]), params)

        # get count
        cursor = connection.cursor()
        cursor.execute(''.join(['SELECT COUNT(mi.id)', sql]), params)
        count = cursor.fetchone()

        # return a pair
        return items, count[0]

    @classmethod
    def get_undeleted_message_item_count_for_message_trees(cls, user, tree_ids):
        """
        counts the number of undeleted message items belonging to the given user for each given message tree
        """
        return MessageItem._get_general_message_item_count_for_message_trees(user, tree_ids, exclude_read=False)

    @classmethod
    def get_unread_message_item_count_for_message_trees(cls, user, tree_ids):
        """
        counts the number of unread message items belonging to the given user for each given message tree
        """
        return MessageItem._get_general_message_item_count_for_message_trees(user, tree_ids, exclude_read=True)

    @classmethod
    def _get_general_message_item_count_for_message_trees(cls, user, tree_ids, exclude_read):
        """
        counts the number of message items belonging to the given user for each given message tree
        """

        if not tree_ids:
            return {}

        # query
        sql = """
            SELECT m.tree_id, COUNT(mi.id)
            FROM messaging_messageitem mi
            INNER JOIN messaging_message m
                ON mi.message_id = m.id
            WHERE mi.user_id = %s
                AND m.is_notification = %s
                AND m.tree_id IN {TREE_IDS}
                AND mi.deleted IS NULL
                {UNREAD}
            GROUP BY m.tree_id
        """

        # substitute '{TREE_IDS}' with a comma-separated list of tree ids
        sql = re.sub(r'\{TREE_IDS\}', '(%s)' % ','.join(map(lambda x: str(x), tree_ids)), sql)

        # substitute 'UNREAD' with a clause that excludes read (if we're excluding read) or nothing (if we're not)
        sql = re.sub(r'\{UNREAD\}', 'AND mi.read IS NULL' if exclude_read else '', sql)

        # execute query
        params = [user.id, False]
        cursor = connection.cursor()
        cursor.execute(sql, params)

        # return a dictionary mapping tree_ids to message item counts
        return {x[0]: int(x[1]) for x in cursor.fetchall()}

    def __str__(self):
        if self.deleted:
            s = self.deleted.strftime(date_format)
        else:
            s = u'never' if self.read is None else self.read.strftime(date_format)
        t = (
            self.message.subject,
            u'deleted' if self.deleted else u'read',
            s,
            ' '.join([self.user.first_name, self.user.last_name]),
        )
        return u'subject "%s" %s @ %s by "%s"' % t

    class Meta:
        unique_together = ('message', 'user',)


@python_2_unicode_compatible
class MessageTargetUser(models.Model):
    message = models.ForeignKey(Message)
    user = models.ForeignKey(settings.AUTH_USER_MODEL)

    def __str__(self):
        t = (
            self.message.subject,
            ' '.join([self.user.first_name, self.user.last_name]),
        )
        return u'subject "%s" was sent to user "%s"' % t

    class Meta:
        unique_together = ('message', 'user',)


@python_2_unicode_compatible
class MessageTargetCourse(models.Model):
    message = models.ForeignKey(Message)
    vle_course_id = models.CharField(max_length=100, db_index=True)

    def __str__(self):
        t = (
            self.message.subject,
            self.vle_course_id,
        )
        return u'subject "%s" was sent to course "%s"' % t

    class Meta:
        unique_together = ('message', 'vle_course_id',)


@python_2_unicode_compatible
class MessageTargetGroup(models.Model):
    message = models.ForeignKey(Message)
    vle_course_id = models.CharField(max_length=100, db_index=True)
    vle_group_id = models.CharField(max_length=100, db_index=True)

    def __str__(self):
        t = (
            self.message.subject,
            self.vle_course_id,
            self.vle_group_id,
        )
        return u'subject "%s" was sent to group "%s|%s"' % t

    class Meta:
        unique_together = ('message', 'vle_course_id', 'vle_group_id',)
