# -*- coding: UTF-8 -*-

from datetime import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django.utils.timezone import utc
from django.utils.six import iteritems

import pytest
from mock import patch, ANY

from messaging.models import Message, MessageAttachment, MessageItem
from messaging.models import MessageTargetUser, MessageTargetCourse, MessageTargetGroup
from messaging.models import date_format, delimiter
from vle.models import CourseMember, GroupMember, expand_user_group_course_ids_to_user_ids


@pytest.mark.urls('messaging.test_urls')
class ModelsTestCase(TestCase):

    def setUp(self):
        self.users = {}
        for first_name in [u'Cersei', u'Jaime', u'Kevan', u'Lancel', u'Tyrion', u'Tywin']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name.lower(),
                email='%s.lannister@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Lannister',
                password='Wibble123!'
            )
            self.users[first_name] = u

    def test_send_message(self):
        recipients = [
            {
                'id': self.users['Jaime'].id,
                'type': u'u'
            },
            {
                'id': self.users['Tywin'].id,
                'type': u'u'
            },
            {
                'id': 'c001',
                'type': u'c'
            },
            {
                'id': delimiter.join(['c002', 'g001']),
                'type': u'g'
            },
            {
                'id': delimiter.join(['c002', 'g002']),
                'type': u'g'
            }
        ]

        subject = 'I want him dead!'
        body = 'The Imp, that is. Incase you were wondering.'

        t0 = timezone.now()
        message = Message.send_message(
            sender=self.users['Cersei'],
            recipients=recipients,
            subject=subject,
            body=body
        )

        # check the Message itself
        self.assertIsInstance(message, Message)
        self.assertEqual(self.users['Cersei'].id, message.user.id)
        self.assertFalse(message.is_notification)
        self.assertEqual('', message.url)
        self.assertEqual(subject, message.subject)
        self.assertEqual(body, message.body)
        self.assertGreaterEqual(message.sent, t0)
        self.assertFalse(message.target_all)

        # check there's a MessageItem for each recipient
        message_item = MessageItem.objects.filter(message=message, read=None, deleted=None).order_by('user__first_name')
        self.assertEqual(2, message_item.count())
        self.assertEqual(self.users['Jaime'].id, message_item[0].user.id)
        self.assertEqual(self.users['Tywin'].id, message_item[1].user.id)

        # check there's a MessageTargetUser for each user recipient
        message_target_user = MessageTargetUser.objects.filter(message=message).order_by('user__first_name')
        self.assertEqual(2, message_target_user.count())
        self.assertEqual(self.users['Jaime'].id, message_target_user[0].user.id)
        self.assertEqual(self.users['Tywin'].id, message_target_user[1].user.id)

        # check there's a MessageTargetCourse for each course recipient
        message_target_course = MessageTargetCourse.objects.filter(message=message).order_by('vle_course_id')
        self.assertEqual(1, message_target_course.count())
        self.assertEqual('c001', message_target_course[0].vle_course_id)

        # check there's a MessageTargetGroup for each group recipient
        message_target_group = MessageTargetGroup.objects.filter(message=message).order_by('vle_course_id', 'vle_group_id')
        self.assertEqual(2, message_target_group.count())
        self.assertEqual('c002', message_target_group[0].vle_course_id)
        self.assertEqual('g001', message_target_group[0].vle_group_id)
        self.assertEqual('c002', message_target_group[1].vle_course_id)
        self.assertEqual('g002', message_target_group[1].vle_group_id)

    @patch('messaging.models.send_mass_mail')
    def test_email_thread(self, mock_send_mass_mail):
        # create a message
        message = Message.objects.create(
            user=self.users['Cersei'],
            subject='The High Sparrow',
            body='He is a little self-righteous, is he not?',
            parent=None
        )

        # email the thread (which obviously only consists of one message)
        all_user_ids = list(map(lambda k: self.users[k].pk, ['Kevan', 'Jaime', 'Tywin']))
        Message.email_thread(message, all_user_ids)

        # ensure send_mass_mail was called with a tuple of 3 tuples as its first argument
        emails = get_user_model().objects.filter(pk__in=all_user_ids).values_list('email', flat=True)
        l = [(ANY, ANY, None, [email]) for email in emails]
        mock_send_mass_mail.assert_called_once_with(tuple(l), fail_silently=True)

    def test_send_message_all(self):
        subject = 'I want him dead!'
        body = 'The Imp, that is. Incase you were wondering.'

        t0 = timezone.now()
        message = Message.send_message_all(
            sender=self.users['Cersei'],
            subject=subject,
            body=body
        )

        # check the Message itself
        self.assertIsInstance(message, Message)
        self.assertEqual(self.users['Cersei'].id, message.user.id)
        self.assertFalse(message.is_notification)
        self.assertEqual('', message.url)
        self.assertEqual(subject, message.subject)
        self.assertEqual(body, message.body)
        self.assertGreaterEqual(message.sent, t0)
        self.assertTrue(message.target_all)

        # check there's a MessageItem for each recipient
        message_item = MessageItem.objects.filter(message=message, read=None, deleted=None).order_by('user__first_name')
        self.assertEqual(len(self.users), message_item.count())

        # check there's no MessageTargetUser, MessageTargetCourse, MessageTargetGroup
        self.assertEqual(0, MessageTargetUser.objects.all().count())
        self.assertEqual(0, MessageTargetCourse.objects.all().count())
        self.assertEqual(0, MessageTargetGroup.objects.all().count())

    def test_create_message_items(self):
        m = Message.objects.create(subject='foo')

        # put Cersei in the course and the group
        CourseMember.objects.create(vle_course_id='001', user=self.users['Cersei'])
        GroupMember.objects.create(vle_course_id='001', vle_group_id='001', user=self.users['Cersei'])

        # put Lancel in the course but not the group
        CourseMember.objects.create(vle_course_id='001', user=self.users['Lancel'])

        # put Jaime in the course and the group
        CourseMember.objects.create(vle_course_id='001', user=self.users['Jaime'])
        GroupMember.objects.create(vle_course_id='001', vle_group_id='001', user=self.users['Jaime'])

        # send to Cersei, everyone in the course, everyone in the group
        user_ids = [self.users['Cersei'].id]
        group_ids = [delimiter.join(['001', '001'])]
        course_ids = ['001']
        all_user_ids = expand_user_group_course_ids_to_user_ids(delimiter, user_ids, group_ids, course_ids)
        MessageItem.create_message_items(m, all_user_ids)
        self.assertEqual(3, MessageItem.objects.count())

        # test that the three recipients are as expected
        messages = MessageItem.objects.all().order_by('user__first_name')
        self.assertEqual('Cersei', messages[0].user.first_name)
        self.assertEqual('Jaime', messages[1].user.first_name)
        self.assertEqual('Lancel', messages[2].user.first_name)

    def test_mark_all_read(self):
        """
        tests that marking all given messages as read only marks those that aren't already read
        """
        now = timezone.now()
        subjects = ['foo', 'bar', 'woo']
        messages = list(map(lambda subject: Message.objects.create(subject=subject), subjects))
        m1 = MessageItem.objects.create(user=self.users['Cersei'], message=messages[0])
        m2 = MessageItem.objects.create(user=self.users['Cersei'], message=messages[1], read=now)
        m3 = MessageItem.objects.create(user=self.users['Cersei'], message=messages[2])
        self.assertIsNone(m1.read)
        self.assertEqual(now, m2.read)
        self.assertIsNone(m3.read)
        MessageItem.mark_all_read([m1, m2, m3])
        self.assertIsNotNone(m1.read)
        self.assertGreaterEqual(m1.read, now)
        self.assertEqual(now, m2.read)
        self.assertIsNotNone(m3.read)
        self.assertGreaterEqual(m3.read, now)

    def test_mark_all_deleted(self):
        """
        tests that marking all given messages as deleted only marks those that aren't already deleted
        """
        now = timezone.now()
        subjects = ['foo', 'bar', 'woo']
        messages = list(map(lambda subject: Message.objects.create(subject=subject), subjects))
        m1 = MessageItem.objects.create(user=self.users['Cersei'], message=messages[0])
        m2 = MessageItem.objects.create(user=self.users['Cersei'], message=messages[1], deleted=now)
        m3 = MessageItem.objects.create(user=self.users['Cersei'], message=messages[2])
        self.assertIsNone(m1.deleted)
        self.assertEqual(now, m2.deleted)
        self.assertIsNone(m3.deleted)
        MessageItem.mark_all_deleted([m1, m2, m3])
        self.assertIsNotNone(m1.deleted)
        self.assertGreaterEqual(m1.deleted, now)
        self.assertEqual(now, m2.deleted)
        self.assertIsNotNone(m3.deleted)
        self.assertGreaterEqual(m3.deleted, now)

    def test_message_instance_str(self):
        m = Message.objects.create(subject='foo')
        self.assertEqual('(Message) subject "foo" sent @ %s' % m.sent.strftime(date_format), str(m))

    def test_notification_instance_str(self):
        n = Message.objects.create(is_notification=True, subject='foo')
        self.assertEqual('(Notification) subject "foo" sent @ %s' % n.sent.strftime(date_format), str(n))

    def test_message_attachment_instance_str(self):
        m = Message.objects.create(subject='foo')
        a = MessageAttachment.objects.create(message=m, file='/path/goes/here')
        self.assertEqual('subject "foo" attachment "/path/goes/here"', str(a))

    def test_message_item_unread_instance_str(self):
        m = Message.objects.create(subject='foo')
        i = MessageItem.objects.create(message=m, user=self.users['Cersei'])
        self.assertEqual('subject "foo" read @ never by "Cersei Lannister"', str(i))

    def test_message_item_read_instance_str(self):
        now = timezone.now()
        m = Message.objects.create(subject='foo')
        i = MessageItem.objects.create(message=m, user=self.users['Cersei'], read=now)
        self.assertEqual('subject "foo" read @ %s by "Cersei Lannister"' % now.strftime(date_format), str(i))

    def test_message_item_deleted_instance_str(self):
        now = timezone.now()
        m = Message.objects.create(subject='foo')
        i = MessageItem.objects.create(message=m, user=self.users['Cersei'], deleted=now)
        self.assertEqual('subject "foo" deleted @ %s by "Cersei Lannister"' % now.strftime(date_format), str(i))

    def test_message_target_user_instance_str(self):
        m = Message.objects.create(subject='foo')
        t = MessageTargetUser.objects.create(message=m, user=self.users['Jaime'])
        self.assertEqual('subject "foo" was sent to user "Jaime Lannister"', str(t))

    def test_message_target_course_instance_str(self):
        m = Message.objects.create(subject='foo')
        t = MessageTargetCourse.objects.create(message=m, vle_course_id=u'c001')
        self.assertEqual('subject "foo" was sent to course "c001"', str(t))

    def test_message_target_group_instance_str(self):
        m = Message.objects.create(subject='foo')
        t = MessageTargetGroup.objects.create(message=m, vle_course_id=u'c001', vle_group_id=u'g001')
        self.assertEqual('subject "foo" was sent to group "c001|g001"', str(t))

    def test_str(self):
        m = Message.objects.create(subject=u'Mucho dinero £££')
        self.assertEqual(type(m.__str__()), str)


class InboxTestCase(TestCase):
    def setUp(self):
        # some Lannisters
        self.users = {}
        for first_name in [u'Cersei', u'Jaime', u'Kevan', u'Lancel', u'Tyrion', u'Tywin']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name.lower(),
                email='%s.lannister@into.uk.com' % first_name.lower(),
                first_name=first_name,
                last_name='Lannister',
                password='Wibble123!'
            )
            self.users[first_name] = u

        # create a group to send messages to
        list(map(lambda p: GroupMember.objects.create(vle_course_id='c001', vle_group_id='g001', user=p[1]), iteritems(self.users)))
        recipients = [
            {
                'id': delimiter.join(['c001', 'g001']),
                'type': u'g'
            }
        ]

        # create a thread of messages
        self.thread = Message.send_message(sender=self.users['Tywin'], recipients=recipients, subject="King's Landing", body="Sort it out!")
        reply1 = Message.send_message(sender=self.users['Tyrion'], recipients=recipients, subject="King's Landing", body="By when?", parent=self.thread)
        Message.send_message(sender=self.users['Tywin'], recipients=recipients, subject="King's Landing", body="Next Tuesday, please.", parent=reply1)
        Message.send_message(sender=self.users['Cersei'], recipients=recipients, subject="King's Landing", body="Do it yourself!", parent=self.thread)

        # ensure each group member has four messages in the thread
        for k, v in iteritems(self.users):
            self.assertEqual(4, MessageItem.objects.filter(user=v, message__tree_id=self.thread.tree_id).count())

        # ensure there are 4 times the number of users message items in total
        self.assertEqual(4 * len(self.users), MessageItem.objects.count())

    def test_get_inbox_has_threads(self):
        """
        inbox consists of threads (i.e. groups of messages with the same tree_id)
        """

        # for each user
        for k, v in iteritems(self.users):
            # check there is only one thread in the inbox
            (inbox, count) = MessageItem.get_inbox(v)
            self.assertEqual(1, count)

    def test_get_inbox_omits_thread_if_all_constituent_messages_deleted(self):
        """
        inbox should not contain a thread if all its constituent messages are deleted
        """

        # get message items for Cersei
        message_items = MessageItem.objects.filter(user=self.users['Cersei'], message__tree_id=self.thread.tree_id, deleted__isnull=True).order_by('-message__sent')
        self.assertEqual(4, message_items.count())

        # delete message items within the thread one at a time
        for i in range(3, 0, -1):
            mi = MessageItem.objects.get(pk=message_items[i].id)
            mi.deleted = timezone.now()
            mi.save()
            (inbox, count) = MessageItem.get_inbox(self.users['Cersei'])
            self.assertEqual(1, count)

        # delete the final message
        mi = MessageItem.objects.get(pk=message_items[0].id)
        mi.deleted = timezone.now()
        mi.save()

        # get the deleted message items, of which there should now be four
        message_items = MessageItem.objects.filter(user=self.users['Cersei'], message__tree_id=self.thread.tree_id, deleted__isnull=False).order_by('-message__sent')
        self.assertEqual(4, message_items.count())

        # check there's now no items in the inbox
        (inbox, count) = MessageItem.get_inbox(self.users['Cersei'])
        self.assertEqual(0, count)

    def test_get_undeleted_message_item_count_for_message_trees(self):
        # create another thread
        recipients = [
            {
                'id': self.users['Cersei'].id,
                'type': u'u'
            }
        ]
        thread2 = Message.send_message(sender=self.users['Tywin'], recipients=recipients, subject='Loras Tyrell', body='Marry him!')

        # get a list of tree ids
        tree_ids = [self.thread.tree_id, thread2.tree_id]

        # get counts of undeleted message items and unread message items in each thread in the inbox page
        undeleted_dict = MessageItem.get_undeleted_message_item_count_for_message_trees(self.users['Cersei'], tree_ids)
        self.assertEqual(2, len(undeleted_dict))
        self.assertDictEqual({
            self.thread.tree_id: 4,
            thread2.tree_id: 1,
        }, undeleted_dict)

    def test_get_unread_message_item_count_for_message_trees(self):
        # create another thread
        recipients = [
            {
                'id': self.users['Cersei'].id,
                'type': u'u'
            }
        ]
        thread2 = Message.send_message(sender=self.users['Tywin'], recipients=recipients, subject='Loras Tyrell', body='Marry him!')

        # get a list of tree ids
        tree_ids = [self.thread.tree_id, thread2.tree_id]

        # read a message
        mi = MessageItem.objects.get(user=self.users['Cersei'], message=self.thread)
        mi.read = timezone.now()
        mi.save()

        # get counts of unread message items and unread message items in each thread in the inbox page
        undeleted_dict = MessageItem.get_unread_message_item_count_for_message_trees(self.users['Cersei'], tree_ids)
        self.assertEqual(2, len(undeleted_dict))
        self.assertDictEqual({
            self.thread.tree_id: 3,
            thread2.tree_id: 1,
        }, undeleted_dict)

    def test_sorting(self):
        self.thread.delete()

        # create more threads
        recipients = [
            {
                'id': self.users['Cersei'].id,
                'type': u'u'
            }
        ]
        senders = ['Tywin', 'Tyrion', 'Jaime', 'Lancel']
        threads = list(map(lambda first_name: Message.send_message(sender=self.users[first_name], recipients=recipients, subject='Irrelevant', body='Irrelevant'), senders))

        # check sorted by sender asc
        (inbox, total) = MessageItem.get_inbox(self.users['Cersei'], sort_field='sender', sort_dir='asc')
        self.assertEqual(len(threads), total)
        self.assertListEqual(
            list(map(lambda t: t.id, [threads[2], threads[3], threads[1], threads[0]])),
            list(map(lambda m: m.message.id, inbox))
        )

        # check sorted by sender desc
        (inbox, total) = MessageItem.get_inbox(self.users['Cersei'], sort_field='sender', sort_dir='desc')
        self.assertListEqual(
            list(map(lambda t: t.id, [threads[0], threads[1], threads[3], threads[2]])),
            list(map(lambda m: m.message.id, inbox))
        )

        # give the threads different sent datetimes
        l = [
            (threads[0], 25, 16),
            (threads[1], 25, 9),
            (threads[2], 24, 13),
            (threads[3], 24, 10),
        ]
        for triple in l:
            thread = triple[0]
            thread.sent = datetime(year=2014, month=7, day=triple[1], hour=triple[2], minute=0, second=0).replace(tzinfo=utc)
            thread.save()

        # check sorted by date asc (i.e. oldest first)
        (inbox, total) = MessageItem.get_inbox(self.users['Cersei'], sort_field='date', sort_dir='asc')
        self.assertListEqual(
            list(map(lambda t: t.id, reversed(threads))),
            list(map(lambda m: m.message.id, inbox))
        )

        # check sorted by date desc (i.e. newest first)
        (inbox, total) = MessageItem.get_inbox(self.users['Cersei'], sort_field='date', sort_dir='desc')
        self.assertListEqual(
            list(map(lambda t: t.id, threads)),
            list(map(lambda m: m.message.id, inbox))
        )


class ThreadTestCase(TestCase):

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

    def test_single_message_item(self):
        # get Obara's message item
        top_level_mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.thread)

        # get thread corresponding to this message item
        (t, count) = top_level_mi.get_thread()

        # at this point, check thread consists of only one message item
        self.assertEqual(1, count)

        # check the message item itself
        mi = t[0]
        self.assertIsInstance(mi, MessageItem)
        self.assertEqual(top_level_mi, mi)
        self.assertEqual(self.sand_snakes['Obara'], mi.user)
        self.assertIsNone(mi.deleted)

    def test_two_message_items(self):
        # get Obara's message item
        top_level_mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.thread)

        # have one of the other Sand Snakes reply to it
        m = Message.send_message(sender=self.sand_snakes['Tyene'], recipients=self.sand_snake_recipients, subject='Justice for Elia', body='', parent=self.thread)
        m.sent = datetime(year=2014, month=7, day=28, hour=10, minute=0, second=0).replace(tzinfo=utc)
        m.save()

        # get thread corresponding to this message item
        (t, count) = top_level_mi.get_thread()

        # check thread consists of two message items
        self.assertEqual(2, count)

        # check the top-level message item (the newest)
        mi = t[0]
        self.assertIsInstance(mi, MessageItem)
        self.assertEqual(MessageItem.objects.get(user=self.sand_snakes['Obara'], message=m), mi)
        self.assertEqual(self.sand_snakes['Obara'], mi.user)
        self.assertIsNone(mi.deleted)

        # check the second message item (the oldest)
        mi = t[1]
        self.assertIsInstance(mi, MessageItem)
        self.assertEqual(top_level_mi, mi)
        self.assertEqual(self.sand_snakes['Obara'].id, mi.user.id)
        self.assertIsNone(mi.deleted)

    def test_deleting_top_level_message_still_gets_thread(self):
        # get Obara's message item
        top_level_mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.thread)

        # delete (strictly: mark as deleted) the top-level message item
        deleted_datetime = datetime(year=2014, month=7, day=28, hour=10, minute=0, second=0).replace(tzinfo=utc)
        top_level_mi.deleted = deleted_datetime
        top_level_mi.save()

        # have one of the other Sand Snakes reply to it
        m = Message.send_message(sender=self.sand_snakes['Tyene'], recipients=self.sand_snake_recipients, subject='Justice for Elia', body='', parent=self.thread)
        m.sent = datetime(year=2014, month=7, day=28, hour=11, minute=0, second=0).replace(tzinfo=utc)
        m.save()

        # get thread corresponding to this message item
        (t, count) = top_level_mi.get_thread()

        # check thread consists of only one message item
        self.assertEqual(1, count)

        # check the newest message item
        mi = t[0]
        self.assertIsInstance(mi, MessageItem)
        self.assertEqual(MessageItem.objects.get(user=self.sand_snakes['Obara'], message=m), mi)
        self.assertEqual(self.sand_snakes['Obara'], mi.user)
        self.assertIsNone(mi.deleted)

    def test_deleting_reply_excludes_reply_from_thread(self):
        # get Obara's message item
        top_level_mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=self.thread)

        # have one of the other Sand Snakes reply to it
        m = Message.send_message(sender=self.sand_snakes['Tyene'], recipients=self.sand_snake_recipients, subject='Justice for Elia', body='', parent=self.thread)
        m.sent = datetime(year=2014, month=7, day=28, hour=11, minute=0, second=0).replace(tzinfo=utc)
        m.save()

        # delete (strictly: mark as deleted) the reply message item
        reply_mi = MessageItem.objects.get(user=self.sand_snakes['Obara'], message=m)
        deleted_datetime = datetime(year=2014, month=7, day=28, hour=13, minute=0, second=0).replace(tzinfo=utc)
        reply_mi.deleted = deleted_datetime
        reply_mi.save()

        # get thread corresponding to this message item
        (t, count) = top_level_mi.get_thread()

        # check thread consists of one message item
        self.assertEqual(1, count)

        # check the message item itself
        mi = t[0]
        self.assertIsInstance(mi, MessageItem)
        self.assertEqual(top_level_mi, mi)
        self.assertEqual(self.sand_snakes['Obara'], mi.user)
        self.assertIsNone(mi.deleted)
