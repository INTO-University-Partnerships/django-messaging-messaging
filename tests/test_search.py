from django.contrib.auth import get_user_model
from django.test import TestCase

from messaging.search import search, _get_visible_user_ids, _get_visible_tutor_ids
from messaging.models import delimiter
from vle.models import CourseMember, GroupMember, CourseKVStore, GroupKVStore


class SearchUsersTestCase(TestCase):

    password = 'Wibble123!'

    def setUp(self):
        # some Lannisters (that aren't super users)
        self.users = {}
        for first_name in [u'Cersei', u'Jaime', u'Kevan', u'Lancel', u'Tyrion', u'Tywin']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name,
                email='%s.lannister@into.uk.com' % first_name,
                first_name=first_name,
                last_name='Lannister',
                password=self.password,
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

    def test_search_no_results(self):
        (users, count, _) = search(q='lanx', user=self.admin)
        self.assertEqual(0, count)
        self.assertListEqual([], users)

    def test_search_one_result(self):
        (users, count, _) = search(q='cersei', user=self.admin)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': ' '.join([self.users['Cersei'].first_name, self.users['Cersei'].last_name]),
            'id': self.users['Cersei'].id,
            'type': u'u'
        }, users[0])

    def test_search_two_results(self):
        (users, count, _) = search(q='ty', user=self.admin)
        self.assertEqual(2, count)
        self.assertDictEqual({
            'name': ' '.join([self.users['Tyrion'].first_name, self.users['Tyrion'].last_name]),
            'id': self.users['Tyrion'].id,
            'type': u'u'
        }, users[0])
        self.assertDictEqual({
            'name': ' '.join([self.users['Tywin'].first_name, self.users['Tywin'].last_name]),
            'id': self.users['Tywin'].id,
            'type': u'u'
        }, users[1])

    def test_search_many_results(self):
        (users, count, _) = search(q='lannister', user=self.admin)
        self.assertEqual(len(self.users), count)

    def test_search_result_count_exceeds_max(self):
        (users, count, per_page) = search(q='lannister', user=self.admin, per_page=5)
        self.assertEqual(5, len(users))
        self.assertEqual(6, count)
        self.assertEqual(5, per_page)

    def test_search_with_single_exclude(self):
        tyrion = {
            'id': self.users['Tyrion'].id,
            'type': u'u'
        }
        (users, count, _) = search(q='ty', exclude=[tyrion], user=self.admin)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': ' '.join([self.users['Tywin'].first_name, self.users['Tywin'].last_name]),
            'id': self.users['Tywin'].id,
            'type': u'u'
        }, users[0])

    def test_search_with_multiple_excludes(self):
        tyrion = {
            'id': self.users['Tyrion'].id,
            'type': u'u'
        }
        tywin = {
            'id': self.users['Tywin'].id,
            'type': u'u'
        }
        (users, count, _) = search(q='lannister', exclude=[tyrion, tywin], user=self.admin)
        self.assertEqual(len(self.users) - 2, count)

    def test_search_with_pagination_two_per_page(self):
        # page 0
        (users, count, per_page) = search(q='lannister', user=self.admin, per_page=2, page=0)
        self.assertEqual(6, count)
        self.assertEqual(2, len(users))
        self.assertEqual(2, per_page)
        self.assertEqual('Cersei Lannister', users[0]['name'])
        self.assertEqual('Jaime Lannister', users[1]['name'])

        # page 1
        (users, count, per_page) = search(q='lannister', user=self.admin, per_page=2, page=1)
        self.assertEqual(6, count)
        self.assertEqual(2, len(users))
        self.assertEqual(2, per_page)
        self.assertEqual('Kevan Lannister', users[0]['name'])
        self.assertEqual('Lancel Lannister', users[1]['name'])

        # page 2
        (users, count, per_page) = search(q='lannister', user=self.admin, per_page=2, page=2)
        self.assertEqual(6, count)
        self.assertEqual(2, len(users))
        self.assertEqual(2, per_page)
        self.assertEqual('Tyrion Lannister', users[0]['name'])
        self.assertEqual('Tywin Lannister', users[1]['name'])

    def test_search_with_pagination_four_per_page(self):
        # page 0
        (users, count, per_page) = search(q='lannister', user=self.admin, per_page=4, page=0)
        self.assertEqual(6, count)
        self.assertEqual(4, len(users))
        self.assertEqual(4, per_page)
        self.assertEqual('Cersei Lannister', users[0]['name'])
        self.assertEqual('Jaime Lannister', users[1]['name'])
        self.assertEqual('Kevan Lannister', users[2]['name'])
        self.assertEqual('Lancel Lannister', users[3]['name'])

        # page 1
        (users, count, per_page) = search(q='lannister', user=self.admin, per_page=4, page=1)
        self.assertEqual(6, count)
        self.assertEqual(2, len(users))
        self.assertEqual(4, per_page)
        self.assertEqual('Tyrion Lannister', users[0]['name'])
        self.assertEqual('Tywin Lannister', users[1]['name'])

    def test_search_with_pagination_ten_per_page(self):
        # page 0
        (users, count, per_page) = search(q='lannister', user=self.admin, per_page=10, page=0)
        self.assertEqual(6, count)
        self.assertEqual(6, len(users))
        self.assertEqual(10, per_page)

        # page 1 (empty, because only 6 users)
        (users, count, per_page) = search(q='lannister', user=self.admin, per_page=10, page=1)
        self.assertEqual(6, count)
        self.assertEqual(0, len(users))
        self.assertEqual(10, per_page)


class GetGroupsFilterTestCase(TestCase):

    password = 'Wibble123!'
    course001 = '001'
    course002 = '002'
    group001 = '001'
    group002 = '002'

    def setUp(self):
        # some courses
        l = [
            (self.course001, 'Course One (Maths)'),
            (self.course002, 'Course Two (Physics)'),
        ]
        list(map(lambda p: CourseKVStore.objects.create(vle_course_id=p[0], name=p[1]), l))

        # some groups
        l = [
            (self.course001, self.group001, 'Group One'),
            (self.course001, self.group002, 'Group Two'),
            (self.course002, self.group001, 'Group One'),
            (self.course002, self.group002, 'Group Two'),
        ]
        list(map(lambda p: GroupKVStore.objects.create(vle_course_id=p[0], vle_group_id=p[1], name=p[2]), l))

        # a user
        self.user = get_user_model().objects.create_user(
            username='sansa.stark',
            email='sansa.stark@into.uk.com',
            first_name='Sansa',
            last_name='Stark',
            password=self.password,
        )

        # a super user
        self.admin = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@into.uk.com',
            first_name='Admin',
            last_name='User',
            password=self.password,
        )

    def test_excludes(self):
        excludes = [
            {
                'id': delimiter.join([self.course001, self.group001]),
                'type': u'g'
            },
            {
                'id': delimiter.join([self.course001, self.group002]),
                'type': u'g'
            },
            {
                'id': delimiter.join([self.course002, self.group001]),
                'type': u'g'
            },
        ]
        (groups, count, _) = search(q='Group', exclude=excludes, user=self.admin)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': 'Course Two (Physics) - Group Two (Group)',
            'id': delimiter.join([self.course002, self.group002]),
            'type': u'g'
        }, groups[0])


class SearchGroupsTestCase(TestCase):

    password = 'Wibble123!'
    course001 = 'c001'
    course002 = 'c002'
    course003 = 'c003'
    group001 = 'g001'
    group002 = 'g002'
    group003 = 'g003'

    def setUp(self):
        # some courses
        l = [
            (self.course001, 'Course One (Maths)'),
            (self.course002, 'Course Two (Physics)'),
            (self.course003, 'Course Three (Maths)'),
        ]
        list(map(lambda p: CourseKVStore.objects.create(vle_course_id=p[0], name=p[1]), l))

        # some groups
        l = [
            (self.course001, self.group001, 'Group One'),
            (self.course001, self.group002, 'Group Two'),
            (self.course002, self.group001, 'Group One'),
            (self.course002, self.group002, 'Group Two'),
            (self.course003, self.group001, 'Group One'),
            (self.course003, self.group002, 'Group Two'),
            (self.course003, self.group003, 'Group Three'),
        ]
        list(map(lambda p: GroupKVStore.objects.create(vle_course_id=p[0], vle_group_id=p[1], name=p[2]), l))

        # a user
        self.user = get_user_model().objects.create_user(
            username='sansa.stark',
            email='sansa.stark@into.uk.com',
            first_name='Sansa',
            last_name='Stark',
            password=self.password,
        )

        # a super user
        self.admin = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@into.uk.com',
            first_name='Admin',
            last_name='User',
            password=self.password,
        )

        # make user member of some (but not all) groups
        l = [
            (self.course001, self.group001),
            (self.course001, self.group002),
            (self.course002, self.group001),
        ]
        list(map(lambda p: GroupMember.objects.create(user=self.user, vle_course_id=p[0], vle_group_id=p[1]), l))

    def test_search_no_results_against_name(self):
        (groups, count, _) = search(q='Group Three', user=self.user)
        self.assertEqual(0, count)
        self.assertListEqual([], groups)

    def test_search_no_results_against_vle_group_id(self):
        (groups, count, _) = search(q=self.group003, user=self.user)
        self.assertEqual(0, count)
        self.assertListEqual([], groups)

    def test_search_no_results_against_vle_course_id(self):
        (groups, count, _) = search(q=self.course003, user=self.user)
        self.assertEqual(0, count)
        self.assertListEqual([], groups)

    def test_search_one_result_against_name(self):
        """
        there are three groups entitled "Group Two" of which Sansa Stark is in one
        """
        (groups, count, _) = search(q='Group Two', user=self.user)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': 'Course One (Maths) - Group Two (Group)',
            'id': delimiter.join([self.course001, self.group002]),
            'type': u'g'
        }, groups[0])

    def test_search_one_result_against_vle_group_id(self):
        (groups, count, _) = search(q=self.group002, user=self.user)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': 'Course One (Maths) - Group Two (Group)',
            'id': delimiter.join([self.course001, self.group002]),
            'type': u'g'
        }, groups[0])

    def test_search_one_result_against_vle_course_id(self):
        (groups, count, _) = search(q=self.course002, user=self.user)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': 'Course Two (Physics) - Group One (Group)',
            'id': delimiter.join([self.course002, self.group001]),
            'type': u'g'
        }, groups[0])

    def test_search_two_results_against_name(self):
        """
        there are three groups entitled "Group One" of which Sansa Stark is in two
        """
        (groups, count, _) = search(q='Group One', user=self.user)
        self.assertEqual(2, count)
        self.assertDictEqual({
            'name': 'Course One (Maths) - Group One (Group)',
            'id': delimiter.join([self.course001, self.group001]),
            'type': u'g'
        }, groups[0])
        self.assertDictEqual({
            'name': 'Course Two (Physics) - Group One (Group)',
            'id': delimiter.join([self.course002, self.group001]),
            'type': u'g'
        }, groups[1])

    def test_search_two_results_against_vle_group_id(self):
        (groups, count, _) = search(q=self.group001, user=self.user)
        self.assertEqual(2, count)
        self.assertDictEqual({
            'name': 'Course One (Maths) - Group One (Group)',
            'id': delimiter.join([self.course001, self.group001]),
            'type': u'g'
        }, groups[0])
        self.assertDictEqual({
            'name': 'Course Two (Physics) - Group One (Group)',
            'id': delimiter.join([self.course002, self.group001]),
            'type': u'g'
        }, groups[1])

    def test_search_many_results(self):
        (groups, count, _) = search(q='Group', user=self.admin)
        self.assertEqual(GroupKVStore.objects.count(), count)

    def test_search_result_count_exceeds_max(self):
        (groups, count, per_page) = search(q='Group', user=self.admin, per_page=5)
        self.assertEqual(5, len(groups))
        self.assertEqual(GroupKVStore.objects.count(), count)
        self.assertEqual(5, per_page)

    def test_search_with_single_exclude(self):
        g = {
            'id': delimiter.join([self.course001, self.group001]),
            'type': u'g'
        }
        (groups, count, _) = search(q='Group One', exclude=[g], user=self.user)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': 'Course Two (Physics) - Group One (Group)',
            'id': delimiter.join([self.course002, self.group001]),
            'type': u'g'
        }, groups[0])

    def test_search_with_multiple_excludes(self):
        g1 = {
            'id': delimiter.join([self.course001, self.group001]),
            'type': u'g'
        }
        g2 = {
            'id': delimiter.join([self.course002, self.group001]),
            'type': u'g'
        }
        (groups, count, _) = search(q='Group One', exclude=[g1, g2], user=self.admin)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': 'Course Three (Maths) - Group One (Group)',
            'id': delimiter.join([self.course003, self.group001]),
            'type': u'g'
        }, groups[0])


class SearchCoursesTestCase(TestCase):

    password = 'Wibble123!'
    course001 = 'c001'
    course002 = 'c002'
    course003 = 'c003'
    course004 = 'c004'

    def setUp(self):
        # some courses
        l = [
            (self.course001, 'Course One (Maths)'),
            (self.course002, 'Course Two (Physics)'),
            (self.course003, 'Course Three (Maths)'),
            (self.course004, 'Course Four (Chemistry)'),
        ]
        list(map(lambda p: CourseKVStore.objects.create(vle_course_id=p[0], name=p[1]), l))

        # a user
        self.user = get_user_model().objects.create_user(
            username='sansa.stark',
            email='sansa.stark@into.uk.com',
            first_name='Sansa',
            last_name='Stark',
            password=self.password,
        )

        # a super user
        self.admin = get_user_model().objects.create_superuser(
            username='admin',
            email='admin@into.uk.com',
            first_name='Admin',
            last_name='User',
            password=self.password,
        )

        # make user member of some (but not all) courses
        l = [
            self.course001,
            self.course002,
        ]
        list(map(lambda p: CourseMember.objects.create(user=self.user, vle_course_id=p), l))

    def test_search_no_results_against_name(self):
        (courses, count, _) = search(q='Chemistry', user=self.user)
        self.assertEqual(0, count)
        self.assertListEqual([], courses)

    def test_search_no_results_against_vle_course_id(self):
        (courses, count, _) = search(q=self.course003, user=self.user)
        self.assertEqual(0, count)
        self.assertListEqual([], courses)

    def test_search_one_result_against_name(self):
        (courses, count, _) = search(q='Maths', user=self.user)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': 'Course One (Maths) (Module)',
            'id': self.course001,
            'type': u'c'
        }, courses[0])

    def test_search_one_result_against_vle_course_id(self):
        (courses, count, _) = search(q=self.course002, user=self.user)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': 'Course Two (Physics) (Module)',
            'id': self.course002,
            'type': u'c'
        }, courses[0])

    def test_search_two_results_against_name(self):
        (courses, count, _) = search(q='Course', user=self.user)
        self.assertEqual(2, count)
        self.assertDictEqual({
            'name': 'Course One (Maths) (Module)',
            'id': self.course001,
            'type': u'c'
        }, courses[0])
        self.assertDictEqual({
            'name': 'Course Two (Physics) (Module)',
            'id': self.course002,
            'type': u'c'
        }, courses[1])

    def test_search_many_results(self):
        (courses, count, _) = search(q='Course', user=self.admin)
        self.assertEqual(CourseKVStore.objects.count(), count)

    def test_search_result_count_exceeds_max(self):
        (courses, count, per_page) = search(q='Course', user=self.admin, per_page=2)
        self.assertEqual(2, len(courses))
        self.assertEqual(CourseKVStore.objects.count(), count)
        self.assertEqual(2, per_page)

    def test_search_with_single_exclude(self):
        c = {
            'id': self.course001,
            'type': u'c'
        }
        (courses, count, _) = search(q='Course', exclude=[c], user=self.user)
        self.assertEqual(1, count)
        self.assertDictEqual({
            'name': 'Course Two (Physics) (Module)',
            'id': self.course002,
            'type': u'c'
        }, courses[0])

    def test_search_with_multiple_excludes(self):
        c1 = {
            'id': self.course001,
            'type': u'c'
        }
        c2 = {
            'id': self.course002,
            'type': u'c'
        }
        (courses, count, _) = search(q='Course', exclude=[c1, c2], user=self.user)
        self.assertEqual(0, count)


class GetVisibleUserIdsTestCase(TestCase):

    course001 = '001'
    course002 = '002'
    course003 = '003'
    course004 = '004'
    course005 = '005'

    def setUp(self):
        # set up some users
        self.users = {}
        for first_name in [u'Cersei', u'Jaime', u'Kevan', u'Lancel', u'Tyrion', u'Tywin', u'Willem']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name,
                email='%s.lannister@into.uk.com' % first_name,
                first_name=first_name,
                last_name='Lannister',
                password='Wibble123!'
            )
            self.users[first_name] = u

        # put users in courses
        l = [
            ('Tywin', self.course001),
            ('Tywin', self.course003),
            ('Tyrion', self.course001),
            ('Jaime', self.course001),
            ('Jaime', self.course005),
            ('Cersei', self.course003),
            ('Kevan', self.course004),
            ('Willem', self.course005),
        ]
        list(map(lambda p: CourseMember.objects.create(user=self.users[p[0]], vle_course_id=p[1]), l))

    def test_users_visible_to_lancel_lannister(self):
        """
        Lancel Lannister isn't in any courses
        """
        user = self.users['Lancel']
        user_ids = _get_visible_user_ids(user)
        self.assertListEqual([], user_ids)

    def test_users_visible_to_kevan_lannister(self):
        """
        Kevan Lannister is alone in course 004
        """
        user = self.users['Kevan']
        user_ids = _get_visible_user_ids(user)
        self.assertListEqual([], user_ids)

    def test_get_users_visible_to_tywin_lannister(self):
        """
        Tywin Lannister is in course 001, course 003
        """
        user = self.users['Tywin']
        user_ids = _get_visible_user_ids(user)
        self.assertListEqual(sorted([
            self.users['Tyrion'].id,  # since Tyrion is also in course 001
            self.users['Jaime'].id,   # since Jaime is also in course 001
            self.users['Cersei'].id,  # since Cersei is also in course 003
        ]), user_ids)

    def test_get_users_visible_cersei_lannister(self):
        """
        Cersei Lannister is in course 003
        """
        user = self.users['Cersei']
        user_ids = _get_visible_user_ids(user)
        self.assertListEqual(sorted([
            self.users['Tywin'].id,  # since Tywin is also in course 003
        ]), user_ids)

    def test_get_users_visible_to_tyrion_lannister(self):
        """
        Tyrion Lannister is in course 001
        """
        user = self.users['Tyrion']
        user_ids = _get_visible_user_ids(user)
        self.assertListEqual(sorted([
            self.users['Tywin'].id,  # since Tywin is also in course 001
            self.users['Jaime'].id,  # since Jaime is also in course 001
        ]), user_ids)

    def test_get_users_visible_to_jaime_lannister(self):
        """
        Jaime Lannister is in course 001, course 005
        """
        user = self.users['Jaime']
        user_ids = _get_visible_user_ids(user)
        self.assertListEqual(sorted([
            self.users['Tywin'].id,   # since Tywin is also in course 001
            self.users['Tyrion'].id,  # since Tyrion is also in course 001
            self.users['Willem'].id,  # since Willem is also in course 005
        ]), user_ids)


class GetVisibleTutorIdsTestCase(TestCase):

    course001 = '001'
    course002 = '002'

    def setUp(self):
        # set up some users
        self.users = {}
        for first_name in [u'Cersei', u'Kevan', u'Lancel', u'Tyrion', u'Tywin']:
            u = get_user_model().objects.create_user(
                username='%s.lannister' % first_name,
                email='%s.lannister@into.uk.com' % first_name,
                first_name=first_name,
                last_name='Lannister',
                password='Wibble123!'
            )
            self.users[first_name] = u

        # put users in courses
        l = [
            ('Tywin', self.course001, True),
            ('Cersei', self.course002, True),
            ('Lancel', self.course001, False),
            ('Kevan', self.course002, False),
            ('Tyrion', self.course001, True),
            ('Tyrion', self.course002, True),
        ]
        list(map(lambda p: CourseMember.objects.create(user=self.users[p[0]], vle_course_id=p[1], is_tutor=p[2]), l))

    def test_tutor_visible_to_other_tutor_1(self):
        """
        Tywin should be able to see Cersei (even though they're not in the same course) because they're both tutors
        """
        user = self.users['Tywin']
        tutor_ids = _get_visible_tutor_ids(user)
        self.assertListEqual(sorted([
            self.users['Cersei'].id,
            self.users['Tyrion'].id,
        ]), tutor_ids)

    def test_tutor_visible_to_other_tutor_2(self):
        """
        Cersei should be able to see Tywin (even though they're not in the same course) because they're both tutors
        """
        user = self.users['Cersei']
        tutor_ids = _get_visible_tutor_ids(user)
        self.assertListEqual(sorted([
            self.users['Tywin'].id,
            self.users['Tyrion'].id,
        ]), tutor_ids)

    def test_tutor_visible_when_both_course_members(self):
        """
        Tyrion should be able to see Tywin and Cersei
        """
        user = self.users['Tyrion']
        tutor_ids = _get_visible_tutor_ids(user)
        self.assertListEqual(sorted([
            self.users['Cersei'].id,
            self.users['Tywin'].id,
        ]), tutor_ids)

    def test_non_tutor_cannot_see_tutors_1(self):
        """
        Lancel is not a tutor and should not be able to see tutors
        """
        user = self.users['Lancel']
        tutor_ids = _get_visible_tutor_ids(user)
        self.assertListEqual([], tutor_ids)

    def test_non_tutor_cannot_see_tutors_2(self):
        """
        Kevan is not a tutor and should not be able to see tutors
        """
        user = self.users['Kevan']
        tutor_ids = _get_visible_tutor_ids(user)
        self.assertListEqual([], tutor_ids)
