import base64
import copy
import json
from datetime import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse
from django.test import TestCase
from django.test.utils import override_settings
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.timezone import utc
from django.utils.six import iteritems
from django.utils.encoding import force_str

import pytest
from mock import patch, ANY

from messaging.models import Message, MessageItem
from messaging.models import MessageTargetUser, MessageTargetGroup, MessageTargetCourse
from messaging.models import delimiter
from vle.models import CourseMember, GroupKVStore, CourseKVStore


def _get_auth_headers():
    joined = ':'.join([settings.VLE_SYNC_BASIC_AUTH[0], settings.VLE_SYNC_BASIC_AUTH[1]])
    b = b'Basic ' + base64.b64encode(joined.encode('utf-8'))
    return {
        'HTTP_AUTHORIZATION': force_str(b)
    }


@pytest.mark.urls('messaging.test_urls')
class SearchRecipientAndSendMessageTestCase(TestCase):

    password = 'Wibble123!'
    course001 = '001'

    def setUp(self):
        # some Lannisters (that aren't super users)
        self.users = {}
        for first_name in [u'Cersei', u'Jaime', u'Kevan', u'Lancel', u'Tyrion', u'Tywin']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name.lower(),
                email='%s.lannister@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Lannister',
                password=self.password
            )
            self.users[first_name] = u

        # one super user
        self.admin = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@into.uk.com',
            first_name='Admin',
            last_name='User',
            password=self.password,
        )

        # put Cersei and Jaime in the same course
        l = [
            ('Jaime', self.course001),
            ('Cersei', self.course001),
        ]
        list(map(lambda p: CourseMember.objects.create(user=self.users[p[0]], vle_course_id=p[1]), l))

    def login(self, username):
        login_successful = self.client.login(username=username, password=self.password)
        self.assertTrue(login_successful)

    def test_search_recipient(self):
        self.login('cersei.lannister')

        # make a request
        post_data = {
            'q': 'Jaime',
            'recipients': [],
        }
        response = self.client.post(reverse('messaging_api:search_recipient'), content_type='application/json', data=json.dumps(post_data))

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(1, data.get('count', 0))
        self.assertEqual(10, data.get('max', 0))
        self.assertListEqual([
            {
                u'id': self.users['Jaime'].id,
                u'name': ' '.join([self.users['Jaime'].first_name, self.users['Jaime'].last_name]),
                u'type': u'u'
            }
        ], data.get('searchResults', []))

    def test_search_recipient_as_superuser(self):
        self.login('admin')

        # make a request
        post_data = {
            'q': '',
            'recipients': [],
        }
        response = self.client.post(reverse('messaging_api:search_recipient'), content_type='application/json', data=json.dumps(post_data))

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(len(self.users), data.get('count', 0))
        self.assertEqual(10, data.get('max', 0))

    @patch('messaging.models.send_mass_mail')
    def test_send_message(self, mock_send_mass_mail):
        self.login('cersei.lannister')

        # make a request
        post_data = {
            'recipients': [
                {
                    u'id': self.users['Jaime'].id,
                    u'type': u'u'
                },
                {
                    u'id': self.users['Tywin'].id,
                    u'type': u'u'
                }
            ],
            'subject': 'The Imp',
            'body': 'I want him dead!'
        }
        response = self.client.post(reverse('messaging_api:send_message'), content_type='application/json', data=json.dumps(post_data))

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Message sent successfully!'), data.get('successMessage', ''))

        # count the number of Messages
        self.assertEqual(1, Message.objects.all().count())

    @patch('messaging.models.send_mass_mail')
    def test_send_message_sends_email(self, mock_send_mass_mail):
        self.login('cersei.lannister')

        # make a request
        post_data = {
            'recipients': [
                {
                    u'id': self.users['Jaime'].id,
                    u'type': u'u'
                },
                {
                    u'id': self.users['Tywin'].id,
                    u'type': u'u'
                }
            ],
            'subject': 'The Imp',
            'body': 'I want him dead!'
        }
        response = self.client.post(reverse('messaging_api:send_message'), content_type='application/json', data=json.dumps(post_data))

        # check email was sent
        emails = get_user_model().objects.filter(pk__in=[self.users['Jaime'].id, self.users['Tywin'].id]).values_list('email', flat=True)
        l = [(ANY, ANY, None, [email]) for email in emails]
        mock_send_mass_mail.assert_called_once_with(tuple(l), fail_silently=True)

    @override_settings(MIDDLEWARE_CLASSES=(
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ))
    def test_message_item_not_found(self):
        """
        This test has to be run without django.middleware.locale.LocaleMiddleware.
        It's because without a language in the requested URL (e.g. '/en/whatever') the middleware detects a 404 and decides
        to try and redirect, so we actually get a 302 and not the 404 we're expecting.
        (The overridden middleware is the minimum required to pass the test.)
        """
        self.login('cersei.lannister')

        # make a request
        post_data = {
            'miid': 999
        }
        response = self.client.post(reverse('messaging_api:send_message'), content_type='application/json', data=json.dumps(post_data))

        # check it wasn't successful
        self.assertEqual(404, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Message item not found'), data.get('errorMessage', ''))
        self.assertEqual('warning', data.get('type', ''))

    def test_can_only_reply_to_own_message_items(self):
        self.login('cersei.lannister')

        # some recipients
        recipients = [
            {
                'id': self.users['Tyrion'].id,
                'type': u'u'
            }
        ]

        # make a top-level message to try to reply to
        m1 = Message.send_message(sender=self.users['Jaime'], recipients=recipients, subject='Happy birthday, brother!', body='')

        # get the message item that was sent to Tyrion
        mi = MessageItem.objects.get(user=self.users['Tyrion'], message=m1)

        # make a request
        post_data = {
            'recipients': recipients,
            'subject': 'Happy birthday, brother!',
            'body': 'But he killed our mother!',
            'miid': mi.id,
        }
        response = self.client.post(reverse('messaging_api:send_message'), content_type='application/json', data=json.dumps(post_data))

        # check it wasn't successful
        self.assertEqual(403, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Access denied'), data.get('errorMessage', ''))
        self.assertEqual('error', data.get('type', ''))

        # count the number of Messages
        self.assertEqual(1, Message.objects.all().count())

    @patch('messaging.models.send_mass_mail')
    def test_send_messages_as_replies(self, mock_send_mass_mail):
        self.login('cersei.lannister')

        # some recipients
        recipients = [
            {
                u'id': self.users['Jaime'].id,
                u'type': u'u'
            },
            {
                'id': self.users['Cersei'].id,
                'type': u'u'
            }
        ]

        # make a top-level message to reply to
        m1 = Message.send_message(sender=self.users['Jaime'], recipients=recipients, subject='Tyrion', body="He didn't do it")
        self.assertIsNone(m1.parent)
        self.assertEqual(0, m1.level)

        # first reply

        # get the message item that was sent to Cersei
        mi = MessageItem.objects.get(user=self.users['Cersei'], message=m1)

        # make a request
        post_data = {
            'recipients': recipients,
            'subject': 'Tyrion',
            'body': "I don't care, I want him dead!",
            'miid': mi.id,
        }
        self.client.post(reverse('messaging_api:send_message'), content_type='application/json', data=json.dumps(post_data))

        # count the number of Messages
        self.assertEqual(2, Message.objects.filter(tree_id=m1.tree_id).count())

        # check parent/child relationship between the two messages
        m2 = Message.objects.get(user=self.users['Cersei'], subject='Tyrion', parent__isnull=False)
        self.assertEqual(m1, m2.parent)
        self.assertEqual(1, m2.level)

        # second reply

        # for Jaime to reply, need to logout Cersei and login Jaime
        self.client.logout()
        self.login('jaime.lannister')

        # get the message item that was sent to Jaime
        mi = MessageItem.objects.get(user=self.users['Jaime'], message=m2)

        # make a request
        post_data = {
            'recipients': recipients,
            'subject': 'Tyrion',
            'body': "I'm not gonna kill my own brother.",
            'miid': mi.id,
        }
        self.client.post(reverse('messaging_api:send_message'), content_type='application/json', data=json.dumps(post_data))

        # count the number of Messages
        self.assertEqual(3, Message.objects.filter(tree_id=m1.tree_id).count())

        # check parent/child relationship between the three messages
        m3 = Message.objects.get(user=self.users['Jaime'], subject='Tyrion', parent__isnull=False)
        self.assertEqual(m2, m3.parent)
        self.assertEqual(2, m3.level)

    def test_send_message_all(self):
        self.login('admin')

        # make a request
        post_data = {
            'recipients': [],
            'targetAll': True,
            'subject': 'Downtime',
            'body': 'Next week'
        }
        response = self.client.post(reverse('messaging_api:send_message'), content_type='application/json', data=json.dumps(post_data))

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Message sent successfully!'), data.get('successMessage', ''))

        # count the number of Messages
        self.assertEqual(1, Message.objects.all().count())

        # count the number of MessageItems
        self.assertEqual(len(self.users), MessageItem.objects.all().count())

    def test_send_message_target_all_not_superuser(self):
        self.login('cersei.lannister')

        # make a request
        post_data = {
            'recipients': [],
            'targetAll': True,
            'subject': 'Downtime',
            'body': 'Next week'
        }
        response = self.client.post(reverse('messaging_api:send_message'), content_type='application/json', data=json.dumps(post_data))

        # check it wasn't successful
        self.assertEqual(403, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Only super users can send messages to everyone'), data.get('errorMessage', ''))
        self.assertEqual('error', data.get('type', ''))

        # count the number of Messages
        self.assertEqual(0, Message.objects.all().count())

        # count the number of MessageItems
        self.assertEqual(0, MessageItem.objects.all().count())


class SendNotificationTestCase(TestCase):

    password = 'Wibble123!'
    url = 'http://somevle.com/vocabcards/blah/blah'
    subject = 'Vocabulary cards'
    body = 'There are some vocabulary cards that need reviewing.'

    def setUp(self):
        # some Lannisters
        self.users = {}
        for first_name in [u'Cersei', u'Jaime', u'Kevan', u'Lancel', u'Tyrion', u'Tywin']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name.lower(),
                email='%s.lannister@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Lannister',
                password=self.password
            )
            self.users[first_name] = u

        self.auth_headers = _get_auth_headers()

    def test_basic_auth_required(self):
        post_data = {
            'usernames': ['irrelevant'],
        }

        # make a request with no header and check it wasn't successful
        response = self.client.post(reverse('messaging_api:send_notification'), content_type='application/json', data=json.dumps(post_data))
        self.assertEqual(403, response.status_code)

        # make a request with invalid username and invalid password and check it wasn't successful
        joined = ':'.join(['invalid', 'invalid'])
        b = b'Basic ' + base64.b64encode(joined.encode('utf-8'))
        auth_headers = {
            'HTTP_AUTHORIZATION': force_str(b)
        }
        response = self.client.post(reverse('messaging_api:send_notification'), content_type='application/json', data=json.dumps(post_data), **auth_headers)
        self.assertEqual(403, response.status_code)

        # make a request with valid username but invalid password and check it wasn't successful
        joined = ':'.join([settings.NOTIFICATION_BASIC_AUTH[0], 'invalid'])
        b = b'Basic ' + base64.b64encode(joined.encode('utf-8'))
        auth_headers = {
            'HTTP_AUTHORIZATION': force_str(b)
        }
        response = self.client.post(reverse('messaging_api:send_notification'), content_type='application/json', data=json.dumps(post_data), **auth_headers)
        self.assertEqual(403, response.status_code)

        # make a request with an invalid username but valid password and check it wasn't successful
        joined = ':'.join(['invalid', settings.NOTIFICATION_BASIC_AUTH[1]])
        b = b'Basic ' + base64.b64encode(joined.encode('utf-8'))
        auth_headers = {
            'HTTP_AUTHORIZATION': force_str(b)
        }
        response = self.client.post(reverse('messaging_api:send_notification'), content_type='application/json', data=json.dumps(post_data), **auth_headers)
        self.assertEqual(403, response.status_code)

        # make a request with a valid username and password and check it was successful
        response = self.client.post(reverse('messaging_api:send_notification'), content_type='application/json', data=json.dumps(post_data), **self.auth_headers)
        self.assertEqual(200, response.status_code)

    def test_send_notification(self):
        # make a request
        post_data = {
            'usernames': [v.username for k, v in iteritems(self.users)],
            'url': self.url,
            'subject': self.subject,
            'body': self.body,
        }
        response = self.client.post(reverse('messaging_api:send_notification'), content_type='application/json', data=json.dumps(post_data), **self.auth_headers)

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Notification sent successfully!'), data.get('successMessage', ''))

        # count the number of Messages
        self.assertEqual(1, Message.objects.filter(is_notification=True, subject=self.subject, body=self.body, url=self.url).count())
        notification = Message.objects.get(is_notification=True)

        # ensure the notification doesn't have a sender
        self.assertIsNone(notification.user)

        # count the number of MessageItems
        self.assertEqual(len(self.users), MessageItem.objects.filter(message=notification).count())

    def test_send_notification_duplicate_username_ignored(self):
        # make a request
        post_data = {
            'usernames': ['cersei.lannister', 'cersei.lannister'],
            'url': self.url,
            'subject': self.subject,
            'body': self.body,
        }
        response = self.client.post(reverse('messaging_api:send_notification'), content_type='application/json', data=json.dumps(post_data), **self.auth_headers)

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Notification sent successfully!'), data.get('successMessage', ''))

        # count the number of Messages
        self.assertEqual(1, Message.objects.filter(is_notification=True, subject=self.subject, body=self.body, url=self.url).count())
        notification = Message.objects.get(is_notification=True)

        # ensure the notification doesn't have a sender
        self.assertIsNone(notification.user)

        # count the number of MessageItems
        self.assertEqual(1, MessageItem.objects.filter(message=notification).count())

    def test_send_notification_no_valid_usernames(self):
        # make a request
        post_data = {
            'usernames': ['invalid', 'does.not.exist', 'neither.does.this'],
            'url': self.url,
            'subject': self.subject,
            'body': self.body,
        }
        response = self.client.post(reverse('messaging_api:send_notification'), content_type='application/json', data=json.dumps(post_data), **self.auth_headers)

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Notification sent successfully!'), data.get('successMessage', ''))

        # count the number of Messages
        self.assertEqual(1, Message.objects.filter(is_notification=True, subject=self.subject, body=self.body, url=self.url).count())
        notification = Message.objects.get(is_notification=True)

        # ensure the notification doesn't have a sender
        self.assertIsNone(notification.user)

        # count the number of MessageItems
        self.assertEqual(0, MessageItem.objects.filter(message=notification).count())


class GetNotificationsTestCase(TestCase):

    password = 'Wibble123!'

    def setUp(self):
        self.users = {}
        for first_name in [u'Cersei']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name.lower(),
                email='%s.lannister@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Lannister',
                password=self.password,
            )
            self.users[first_name] = u

    def login(self, username):
        login_successful = self.client.login(username=username, password=self.password)
        self.assertTrue(login_successful)

    def test_get_notifications_empty(self):
        self.login('cersei.lannister')

        # make a request
        response = self.client.get(reverse('messaging_api:get_notifications'), content_type='application/json')
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(2, len(data))
        self.assertEqual(0, len(data['notifications']))
        self.assertEqual(0, data['total'])

    def test_get_notifications(self):
        self.login('cersei.lannister')

        # send some notifications
        l = [
            ('Loras Tyrell', 'Marry him!', 'http://foobar.com'),
            ('Casterly Rock', '', 'http://whatever.com'),
            ('Stop drinking so much wine!', 'Your liver will explode.', 'http://wibble.into.uk.com'),
        ]
        list(map(lambda p: Message.send_notification(usernames=[self.users['Cersei'].username], url=p[2], subject=p[0], body=p[1]), l))

        # make a request
        response = self.client.get(reverse('messaging_api:get_notifications'), content_type='application/json')
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(2, len(data))
        self.assertEqual(3, len(data['notifications']))
        self.assertEqual(3, data['total'])

        # check the urls, subjects and bodies
        urls = list(map(lambda x: x[2], l))
        bodies = list(map(lambda x: x[1], l))
        subjects = list(map(lambda x: x[0], l))
        for i in range(0, 3):
            self.assertIn(data['notifications'][i]['url'], urls)
            self.assertIn(data['notifications'][i]['subject'], subjects)
            self.assertIn(data['notifications'][i]['body'], bodies)

    def test_get_notification_pagination(self):
        self.login('cersei.lannister')

        # send some notifications
        l = [('Subject %d' % i, 'Body %d' % i) for i in range(1, 13)]
        list(map(lambda p: Message.send_notification(usernames=[self.users['Cersei'].username], url='http://foobar.com', subject=p[0], body=p[1]), l))
        self.assertEqual(len(l), Message.objects.filter(subject__startswith='Subject').count())
        self.assertEqual(len(l), Message.objects.filter(body__startswith='Body').count())

        # make a request for page 1 (at 5 items per page)
        response = self.client.get(''.join([reverse('messaging_api:get_notifications'), '?page=0&per_page=5']), content_type='application/json')
        data = json.loads(force_str(response.content))
        self.assertEqual(5, len(data['notifications']))
        self.assertEqual(12, data['total'])

        # make a request for page 2 (at 5 items per page)
        response = self.client.get(''.join([reverse('messaging_api:get_notifications'), '?page=1&per_page=5']), content_type='application/json')
        data = json.loads(force_str(response.content))
        self.assertEqual(5, len(data['notifications']))
        self.assertEqual(12, data['total'])

        # make a request for page 3 (at 5 items per page)
        response = self.client.get(''.join([reverse('messaging_api:get_notifications'), '?page=2&per_page=5']), content_type='application/json')
        data = json.loads(force_str(response.content))
        self.assertEqual(2, len(data['notifications']))
        self.assertEqual(12, data['total'])


class MarkNotificationReadTestCase(TestCase):

    password = 'Wibble123!'

    def setUp(self):
        self.users = {}
        for first_name in [u'Cersei']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name.lower(),
                email='%s.lannister@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Lannister',
                password=self.password,
            )
            self.users[first_name] = u

    def login(self, username):
        login_successful = self.client.login(username=username, password=self.password)
        self.assertTrue(login_successful)

    def test_mark_notification_read(self):
        self.login('cersei.lannister')

        # send a notification
        notification = Message.send_notification(usernames=['cersei.lannister'], url='http://foobar.com', subject='Subject', body='Body')

        # get the corresponding message item and ensure it's not (yet) read
        mi = MessageItem.objects.get(message=notification, user=self.users['Cersei'])
        self.assertIsNone(mi.read)

        # make a request
        t0 = timezone.now().replace(microsecond=0)
        response = self.client.get(''.join([reverse('messaging_api:mark_notification_read'), '?miid=', str(mi.id)]), content_type='application/json')

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the message item is now marked as read
        mi = MessageItem.objects.get(message=notification, user=self.users['Cersei'])
        self.assertIsNotNone(mi.read)
        self.assertGreaterEqual(mi.read, t0)


class GetInboxTestCase(TestCase):

    password = 'Wibble123!'

    def setUp(self):
        # some Lannisters
        self.users = {}
        for first_name in [u'Cersei', u'Jaime', u'Kevan', u'Lancel', u'Tyrion', u'Tywin']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name.lower(),
                email='%s.lannister@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Lannister',
                password=self.password,
            )
            self.users[first_name] = u

        # a message recipient
        self.recipients = [
            {
                'id': self.users['Cersei'].id,
                'type': u'u'
            }
        ]

    def login(self, username):
        login_successful = self.client.login(username=username, password=self.password)
        self.assertTrue(login_successful)

    def test_get_inbox_empty(self):
        self.login('cersei.lannister')

        # make a request
        response = self.client.get(reverse('messaging_api:get_inbox'), content_type='application/json')
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(2, len(data))
        self.assertEqual(0, len(data['messages']))
        self.assertEqual(0, data['total'])

    def test_get_inbox(self):
        self.login('cersei.lannister')

        # send some messages
        l = [
            ('Loras Tyrell', 'Marry him!'),
            ('Casterly Rock', ''),
            ('Stop drinking so much wine!', 'Your liver will explode.'),
        ]
        list(map(lambda p: Message.send_message(sender=self.users['Tywin'], recipients=self.recipients, subject=p[0], body=[1]), l))

        # make a request
        response = self.client.get(reverse('messaging_api:get_inbox'), content_type='application/json')
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(2, len(data))
        self.assertEqual(3, len(data['messages']))
        self.assertEqual(3, data['total'])

        # check the subjects and sender
        subjects = list(map(lambda x: x[0], l))
        for i in range(0, 3):
            self.assertIn(data['messages'][i]['subject'], subjects)
            self.assertEqual(' '.join([self.users['Tywin'].first_name, self.users['Tywin'].last_name]), data['messages'][i]['sender'])

    def test_get_inbox_pagination(self):
        self.login('cersei.lannister')

        # send some messages
        l = [('Subject %d' % i, 'Body %d' % i) for i in range(1, 13)]
        list(map(lambda p: Message.send_message(sender=self.users['Tywin'], recipients=self.recipients, subject=p[0], body=p[1]), l))
        self.assertEqual(len(l), Message.objects.filter(subject__startswith='Subject').count())
        self.assertEqual(len(l), Message.objects.filter(body__startswith='Body').count())

        # make a request for page 1 (at 5 items per page)
        response = self.client.get(''.join([reverse('messaging_api:get_inbox'), '?page=0&per_page=5']), content_type='application/json')
        data = json.loads(force_str(response.content))
        self.assertEqual(5, len(data['messages']))
        self.assertEqual(12, data['total'])

        # make a request for page 2 (at 5 items per page)
        response = self.client.get(''.join([reverse('messaging_api:get_inbox'), '?page=1&per_page=5']), content_type='application/json')
        data = json.loads(force_str(response.content))
        self.assertEqual(5, len(data['messages']))
        self.assertEqual(12, data['total'])

        # make a request for page 3 (at 5 items per page)
        response = self.client.get(''.join([reverse('messaging_api:get_inbox'), '?page=2&per_page=5']), content_type='application/json')
        data = json.loads(force_str(response.content))
        self.assertEqual(2, len(data['messages']))
        self.assertEqual(12, data['total'])


class GetUnreadCountTestCase(TestCase):

    password = 'Wibble123!'

    def setUp(self):
        self.oberyn = get_user_model().objects.create_user(
            username='oberyn.martell',
            email='oberyn.martell@into.uk.com',
            first_name='Oberyn',
            last_name='Martell',
            password=self.password
        )

        self.elia = get_user_model().objects.create_user(
            username='elia.martell',
            email='elia.martell@into.uk.com',
            first_name='Elia',
            last_name='Martell',
            password=self.password
        )

    def login(self, username):
        login_successful = self.client.login(username=username, password=self.password)
        self.assertTrue(login_successful)

    def test_unread_message_count(self):
        # seed the database
        recipient = {
            'id': self.oberyn.id,
            'type': 'u',
        }
        messages = list(map(lambda i: Message.send_message(sender=self.elia, recipients=[recipient], subject='Justice for me 1', body=''), range(1, 5)))

        # mark one of the messages as read
        mi = MessageItem.objects.get(user=self.oberyn, message=messages[1])
        mi.read = timezone.now()
        mi.save()

        # mark one of the messages as deleted
        mi = MessageItem.objects.get(user=self.oberyn, message=messages[3])
        mi.deleted = timezone.now()
        mi.save()

        # login Oberyn
        self.login(self.oberyn)

        # make a request
        response = self.client.get(reverse('messaging_api:get_unread_count'), content_type='application/json')

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(2, data['count'])

    def test_unread_notification_count(self):
        # seed the database
        notifications = list(map(lambda i: Message.send_notification(usernames=['oberyn.martell'], url='http://foobar.com', subject='Subject', body='Body'), range(1, 5)))

        # mark one of the messages as read
        mi = MessageItem.objects.get(user=self.oberyn, message=notifications[1])
        mi.read = timezone.now()
        mi.save()

        # mark one of the messages as deleted
        mi = MessageItem.objects.get(user=self.oberyn, message=notifications[3])
        mi.deleted = timezone.now()
        mi.save()

        # login Oberyn
        self.login(self.oberyn)

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:get_unread_count'), '?n=1']), content_type='application/json')

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(2, data['count'])


class GetThreadTestCase(TestCase):

    password = 'Wibble123!'

    def setUp(self):
        # Oberyn
        self.oberyn = get_user_model().objects.create_user(
            username='oberyn.martell',
            email='oberyn.martell@into.uk.com',
            first_name='Oberyn',
            last_name='Martell',
            password=self.password
        )

        # the Sand Snakes
        self.sand_snakes = {}
        for first_name in [u'Nymeria', u'Tyene', u'Obara']:
            u = get_user_model().objects.create_user(
                username='%s.sand' % first_name.lower(),
                email='%s.sand@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Sand',
                password=self.password
            )
            self.sand_snakes[first_name] = u

        # Sand Snake recipients
        self.sand_snake_recipients = list(map(lambda p: {
            'id': p[1].id,
            'type': u'u'
        }, iteritems(self.sand_snakes)))

        # create a thread of messages
        self.thread = Message.send_message(sender=self.oberyn, recipients=self.sand_snake_recipients, subject='Justice for Elia', body='')
        self.thread.sent = datetime(year=2014, month=7, day=28, hour=9, minute=0, second=0).replace(tzinfo=utc)
        self.thread.save()

        # create a thread that won't be the focus of this test case
        Message.send_message(sender=self.oberyn, recipients=self.sand_snake_recipients, subject='Poison', body='Anyone got any spare?')

    def login(self, username):
        login_successful = self.client.login(username=username, password=self.password)
        self.assertTrue(login_successful)

    @override_settings(MIDDLEWARE_CLASSES=(
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ))
    def test_message_item_not_found(self):
        """
        This test has to be run without django.middleware.locale.LocaleMiddleware.
        It's because without a language in the requested URL (e.g. '/en/whatever') the middleware detects a 404 and decides
        to try and redirect, so we actually get a 302 and not the 404 we're expecting.
        (The overridden middleware is the minimum required to pass the test.)
        """
        self.login(self.sand_snakes['Obara'])

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:get_thread'), '?miid=999']), content_type='application/json')

        # check it wasn't successful
        self.assertEqual(404, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Message item not found'), data.get('errorMessage', ''))
        self.assertEqual('warning', data.get('type', ''))

    def test_access_denied(self):
        self.login(self.sand_snakes['Nymeria'])

        # get Obara's message item
        top_level_mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.thread)

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:get_thread'), '?miid=', str(top_level_mi.id)]), content_type='application/json')

        # check it wasn't successful
        self.assertEqual(403, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Access denied'), data.get('errorMessage', ''))
        self.assertEqual('error', data.get('type', ''))

    def test_three_message_items(self):
        self.login(self.sand_snakes['Obara'])

        # get Obara's message item
        top_level_mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.thread)

        # have two of the other Sand Snakes reply to it
        m1 = Message.send_message(sender=self.sand_snakes['Tyene'], recipients=self.sand_snake_recipients, subject='Justice for Elia', body='', parent=self.thread)
        m1.sent = datetime(year=2014, month=7, day=28, hour=10, minute=0, second=0).replace(tzinfo=utc)
        m1.save()
        m2 = Message.send_message(sender=self.sand_snakes['Nymeria'], recipients=self.sand_snake_recipients, subject='Justice for Elia', body='', parent=self.thread)
        m2.sent = datetime(year=2014, month=7, day=28, hour=10, minute=30, second=0).replace(tzinfo=utc)
        m2.save()

        # before (round down microseconds, otherwise the test fails on MySQL as it seems to be accurate only to the nearest second)
        before = timezone.now().replace(microsecond=0)

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:get_thread'), '?miid=', str(top_level_mi.id)]), content_type='application/json')
        data = json.loads(force_str(response.content))
        self.assertEqual('Justice for Elia', data['subject'])
        self.assertEqual(3, len(data['messages']))
        self.assertEqual(3, data['total'])

        # ensure all message items which comprise the thread are marked as read
        message_items = MessageItem.objects.filter(user=self.sand_snakes['Obara'], message__tree_id=self.thread.tree_id)
        self.assertEqual(3, message_items.count())
        read_states = list(map(lambda mi: mi.read >= before, message_items))
        self.assertTrue(all(read_states))


class GetReplyInfoTestCase(TestCase):

    password = 'Wibble123!'
    group001 = u'001'
    course001 = u'001'

    def setUp(self):
        # Oberyn
        self.oberyn = get_user_model().objects.create_user(
            username='oberyn.martell',
            email='oberyn.martell@into.uk.com',
            first_name='Oberyn',
            last_name='Martell',
            password=self.password
        )

        # the Sand Snakes
        self.sand_snakes = {}
        for first_name in [u'Nymeria', u'Tyene', u'Obara']:
            u = get_user_model().objects.create_user(
                username='%s.sand' % first_name.lower(),
                email='%s.sand@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Sand',
                password=self.password
            )
            self.sand_snakes[first_name] = u

        # user recipients
        self.user_recipients = list(map(lambda p: {
            u'id': p[1].id,
            u'type': u'u'
        }, iteritems(self.sand_snakes)))

        # a group recipient (it's irrelevant whether there's any group members)
        self.group_recipient = {
            u'id': delimiter.join([self.course001, self.group001]),
            u'type': u'g'
        }

        # a course recipient (it's irrelevant whether there's any course members)
        self.course_recipient = {
            u'id': self.course001,
            u'type': u'c'
        }

        # a group and a course
        GroupKVStore.objects.create(vle_course_id=self.course001, vle_group_id=self.group001, name=u'Group 001')
        CourseKVStore.objects.create(vle_course_id=self.course001, name=u'Course 001')

        # send a message to a total of 5 recipients (3 users, 1 group, 1 course)
        all_recipients = []
        all_recipients.extend(self.user_recipients)
        all_recipients.append(self.group_recipient)
        all_recipients.append(self.course_recipient)
        self.message = Message.send_message(sender=self.oberyn, recipients=all_recipients, subject='Justice for Elia', body='')

        # check message targets
        self.assertEqual(len(self.user_recipients), MessageTargetUser.objects.all().count())
        self.assertEqual(1, MessageTargetGroup.objects.all().count())
        self.assertEqual(1, MessageTargetCourse.objects.all().count())

    def login(self, username):
        login_successful = self.client.login(username=username, password=self.password)
        self.assertTrue(login_successful)

    @override_settings(MIDDLEWARE_CLASSES=(
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ))
    def test_message_item_not_found(self):
        """
        This test has to be run without django.middleware.locale.LocaleMiddleware.
        It's because without a language in the requested URL (e.g. '/en/whatever') the middleware detects a 404 and decides
        to try and redirect, so we actually get a 302 and not the 404 we're expecting.
        (The overridden middleware is the minimum required to pass the test.)
        """
        self.login(self.sand_snakes['Obara'])

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:get_reply_info'), '?miid=999']), content_type='application/json')

        # check it wasn't successful
        self.assertEqual(404, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Message item not found'), data.get('errorMessage', ''))
        self.assertEqual('warning', data.get('type', ''))

    def test_access_denied(self):
        self.login(self.sand_snakes['Nymeria'])

        # get Obara's message item
        mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.message)

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:get_reply_info'), '?miid=', str(mi.id)]), content_type='application/json')

        # check it wasn't successful
        self.assertEqual(403, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Access denied'), data.get('errorMessage', ''))
        self.assertEqual('error', data.get('type', ''))

    def test_get_recipients_course_only(self):
        self.login(self.sand_snakes['Obara'])

        # make Obara a course member so she receives the message
        CourseMember.objects.create(user=self.sand_snakes['Obara'], vle_course_id=self.course001)

        # send a message to a total of 1 recipient (1 course)
        self.message = Message.send_message(sender=self.oberyn, recipients=[self.course_recipient], subject='Justice for Elia', body='')

        # get MessageItem
        mi = MessageItem.objects.get(message=self.message, user=self.sand_snakes['Obara'])

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:get_reply_info'), '?miid=', str(mi.id)]), content_type='application/json')
        data = json.loads(force_str(response.content))

        # check recipients (the sender of the message being replied to will always be the first recipient)
        self.assertListEqual([
            {
                u'id': self.oberyn.id,
                u'name': ' '.join([self.oberyn.first_name, self.oberyn.last_name]),
                u'type': u'u'
            },
            {
                u'id': self.course001,
                u'name': u'Course 001',
                u'type': u'c'
            },
        ], data['recipients'])

    def test_get_recipients(self):
        self.login(self.sand_snakes['Obara'])

        # get MessageItem
        mi = MessageItem.objects.get(message=self.message, user=self.sand_snakes['Obara'])

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:get_reply_info'), '?miid=', str(mi.id)]), content_type='application/json')
        data = json.loads(force_str(response.content))

        # check recipients (the sender of the message being replied to will always be the first recipient)
        self.assertLess(self.sand_snakes['Nymeria'].id, self.sand_snakes['Tyene'].id)
        self.assertListEqual([
            {
                u'id': self.oberyn.id,
                u'name': ' '.join([self.oberyn.first_name, self.oberyn.last_name]),
                u'type': u'u'
            },
            {
                u'id': self.sand_snakes['Nymeria'].id,
                u'name': ' '.join([self.sand_snakes['Nymeria'].first_name, self.sand_snakes['Nymeria'].last_name]),
                u'type': u'u'
            },
            {
                u'id': self.sand_snakes['Tyene'].id,
                u'name': ' '.join([self.sand_snakes['Tyene'].first_name, self.sand_snakes['Tyene'].last_name]),
                u'type': u'u'
            },
            {
                u'id': delimiter.join([self.course001, self.group001]),
                u'name': u'Group 001',
                u'type': u'g'
            },
            {
                u'id': self.course001,
                u'name': u'Course 001',
                u'type': u'c'
            },
        ], data['recipients'])

        # check sender, subject and body
        self.assertEqual(' '.join([self.oberyn.first_name, self.oberyn.last_name]), data['sender'])
        self.assertEqual(self.message.subject, data['subject'])
        self.assertEqual(self.message.body, data['body'])


class DeleteMessageItemTestCase(TestCase):

    password = 'Wibble123!'
    group001 = u'001'
    course001 = u'001'

    def setUp(self):
        # Oberyn
        self.oberyn = get_user_model().objects.create_user(
            username='oberyn.martell',
            email='oberyn.martell@into.uk.com',
            first_name='Oberyn',
            last_name='Martell',
            password=self.password
        )

        # the Sand Snakes
        self.sand_snakes = {}
        for first_name in [u'Nymeria', u'Tyene', u'Obara']:
            u = get_user_model().objects.create_user(
                username='%s.sand' % first_name.lower(),
                email='%s.sand@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Sand',
                password=self.password
            )
            self.sand_snakes[first_name] = u

        # user recipients
        user_recipients = list(map(lambda p: {
            u'id': p[1].id,
            u'type': u'u'
        }, iteritems(self.sand_snakes)))

        # Oberyn recipient
        user_recipients.append({
            u'id': self.oberyn.id,
            u'type': u'u'
        })

        # create a thread
        self.message = Message.send_message(sender=self.oberyn, recipients=user_recipients, subject='Justice for Elia', body='')
        self.reply_from_obara = Message.send_message(sender=self.sand_snakes['Obara'], recipients=user_recipients, subject='Justice for Elia', body='Reply from Obara', parent=self.message)
        self.reply_from_nymeria = Message.send_message(sender=self.sand_snakes['Nymeria'], recipients=user_recipients, subject='Justice for Elia', body='Reply from Nymeria', parent=self.message)

    def login(self, username):
        login_successful = self.client.login(username=username, password=self.password)
        self.assertTrue(login_successful)

    @override_settings(MIDDLEWARE_CLASSES=(
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
    ))
    def test_message_item_not_found(self):
        """
        This test has to be run without django.middleware.locale.LocaleMiddleware.
        It's because without a language in the requested URL (e.g. '/en/whatever') the middleware detects a 404 and decides
        to try and redirect, so we actually get a 302 and not the 404 we're expecting.
        (The overridden middleware is the minimum required to pass the test.)
        """
        self.login(self.sand_snakes['Obara'])

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:delete_message_item'), '?miid=999']), content_type='application/json')

        # check it wasn't successful
        self.assertEqual(404, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Message item not found'), data.get('errorMessage', ''))
        self.assertEqual('warning', data.get('type', ''))

    def test_access_denied(self):
        self.login(self.sand_snakes['Nymeria'])

        # get Obara's message item
        mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.message)

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:delete_message_item'), '?miid=', str(mi.id)]), content_type='application/json')

        # check it wasn't successful
        self.assertEqual(403, response.status_code)

        # check the JSON
        data = json.loads(force_str(response.content))
        self.assertEqual(_('Access denied'), data.get('errorMessage', ''))
        self.assertEqual('error', data.get('type', ''))

    def test_delete_one_message_item(self):
        self.login(self.sand_snakes['Obara'])

        # get Obara's message item
        mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.message)

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:delete_message_item'), '?miid=', str(mi.id)]), content_type='application/json')

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check it's marked deleted
        mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.message)
        self.assertIsNotNone(mi.deleted)

        # check it's the only message item marked deleted
        self.assertEqual(1, MessageItem.objects.filter(user=self.sand_snakes['Obara'], deleted__isnull=False).count())

    def test_delete_entire_thread(self):
        self.login(self.sand_snakes['Obara'])

        # get Obara's message item
        mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.message)

        # make a request
        response = self.client.get(''.join([reverse('messaging_api:delete_message_item'), '?miid=', str(mi.id), '&thread=1']), content_type='application/json')

        # check it was successful
        self.assertEqual(200, response.status_code)

        # check all the message items belonging to Obara are now deleted
        mi = MessageItem.objects.filter(user=self.sand_snakes['Obara'], message__tree_id=self.message.tree_id)
        self.assertEqual(3, mi.count())
        mi = MessageItem.objects.filter(user=self.sand_snakes['Obara'], message__tree_id=self.message.tree_id, deleted__isnull=False)
        self.assertEqual(3, mi.count())
        mi = MessageItem.objects.filter(user=self.sand_snakes['Obara'], message__tree_id=self.message.tree_id, deleted__isnull=True)
        self.assertEqual(0, mi.count())

        # check no other message items are deleted
        mi = MessageItem.objects.filter(message__tree_id=self.message.tree_id, deleted__isnull=False)
        self.assertEqual(3, mi.count())


@pytest.fixture
def lannisters():
    users = {}
    for first_name in ['Cersei', 'Jaime', 'Kevan', 'Lancel', 'Tyrion', 'Tywin']:
        users[first_name] = get_user_model().objects.create_user(
            username='%s.lannister' % first_name.lower(),
            email='%s.lannister@into.uk.com' % first_name.lower(),
            first_name=first_name,
            last_name='Lannister',
            password='Wibble123!'
        )
    return users


@pytest.mark.urls('messaging.test_urls')
@pytest.mark.django_db()
def test_read_without_message_raises_404(client, lannisters):
    templates_setting = copy.deepcopy(settings.TEMPLATES)
    templates_setting[0]['DIRS'] = []
    with override_settings(TEMPLATES=templates_setting):
        client.login(username=lannisters['Cersei'], password='Wibble123!')
        response = client.get(reverse('read_message', args=(999,)))
    assert response.status_code == 404


@pytest.mark.urls('messaging.test_urls')
@pytest.mark.django_db()
def test_read_without_message_item_raises_404(client, lannisters):
    templates_setting = copy.deepcopy(settings.TEMPLATES)
    templates_setting[0]['DIRS'] = []
    with override_settings(TEMPLATES=templates_setting):
        client.login(username=lannisters['Cersei'], password='Wibble123!')
        message = Message.objects.create(
            user=lannisters['Cersei'],
            subject='The High Sparrow',
            body='He is a little self-righteous, is he not?',
            parent=None
        )
        response = client.get(reverse('read_message', args=(message.id,)))
    assert response.status_code == 404


@pytest.mark.urls('messaging.test_urls')
@pytest.mark.django_db()
def test_read_with_message_and_message_item_redirects(client, lannisters):
    client.login(username=lannisters['Jaime'], password='Wibble123!')
    message = Message.objects.create(
        user=lannisters['Cersei'],
        subject='The High Sparrow',
        body='He is a little self-righteous, is he not?',
        parent=None
    )
    message_item = MessageItem.objects.create(
        user=lannisters['Jaime'],
        message=message
    )
    response = client.get(reverse('read_message', args=(message.id,)))
    assert response.status_code == 302
    assert response.url.endswith('read/{0}'.format(message_item.id))
