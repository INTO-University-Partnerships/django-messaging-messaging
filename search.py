from operator import itemgetter

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db import connection
from django.utils.translation import gettext as _

from vle.models import CourseKVStore, GroupKVStore, GroupMember, CourseMember
from .models import delimiter


def search(q='', exclude=None, user=None, per_page=None, page=0):
    """
    search users, groups and courses
    """

    if exclude is None:
        exclude = []

    if user is None:
        return [], 0

    if per_page is None:
        per_page = settings.MESSAGING_SEARCH_RESULTS_PER_PAGE if hasattr(settings, 'MESSAGING_SEARCH_RESULTS_PER_PAGE') else 10

    (users, users_count) = _search_users(q=q, exclude=exclude, user=user)
    (groups, groups_count) = _search_groups(q=q, exclude=exclude, user=user)
    (courses, courses_count) = _search_courses(q=q, exclude=exclude, user=user)

    total = sorted(users + groups + courses, key=itemgetter('name'))
    total_count = users_count + groups_count + courses_count
    index_from = per_page * page
    index_to = index_from + per_page

    return total[index_from:index_to], total_count, per_page


def _search_users(q, exclude, user):
    """
    search users by first_name, last_name, username and email according to the given query
    if the given user is not a super user, restrict visibility of (other) users according to the given user's courses
    """

    # text search according to given query
    f = Q(first_name__icontains=q) | \
        Q(last_name__icontains=q) | \
        Q(username__icontains=q) | \
        Q(email__icontains=q)
    u = get_user_model().objects.filter(f)

    # if the user isn't a super user then filter by visible users
    if not user.is_superuser:
        visible_user_ids = _get_visible_user_ids(user) + _get_visible_tutor_ids(user)
        if not visible_user_ids:
            return [], 0
        u = u.filter(pk__in=visible_user_ids)

    # exclude given users
    exclude_pks = [r.get('id') for r in exclude if r.get('id', '') and r.get('type', '') == u'u']
    exclude_pks.append(user.id)
    u = u.exclude(pk__in=exclude_pks)

    # return a list of users and a (total) count
    return [
        {
            u'name': u' '.join([user.first_name, user.last_name]),
            u'id': user.pk,
            u'type': u'u'
        }
        for user in u
    ], u.count()


def _search_groups(q, exclude, user):
    """
    search groups by vle_course_id, vle_group_id and name according to the given query
    if the given user is not a super user, restrict visibility of groups according to the given user's groups
    """

    # text search according to given query
    f = Q(vle_course_id__icontains=q) | \
        Q(vle_group_id__icontains=q) | \
        Q(name__icontains=q)
    g = GroupKVStore.objects.filter(f)

    # if the user isn't a super user then filter by visible groups
    if not user.is_superuser:
        visible_groups = GroupMember.objects.filter(user=user).values_list('vle_course_id', 'vle_group_id')
        if not visible_groups:
            return [], 0
        g = g.filter(GroupMember.get_groups_filter(visible_groups))

    # exclude given groups
    exclude_ids = [r.get('id').split(delimiter) for r in exclude if r.get('id', '') and r.get('type', '') == u'g']
    if exclude_ids:
        g = g.exclude(GroupMember.get_groups_filter(exclude_ids))

    # create a map of vle_course_id to course names
    courses = dict(CourseKVStore.objects.filter(vle_course_id__in=[grp.vle_course_id for grp in g]).values_list('vle_course_id', 'name').distinct())

    # return a list of groups and a (total) count
    return [
        {
            u'name': u''.join([courses.get(group.vle_course_id, ''), ' - ', group.name, u' (', _('Group'), u')']),
            u'id': delimiter.join([group.vle_course_id, group.vle_group_id]),
            u'type': u'g'
        }
        for group in g
    ], g.count()


def _search_courses(q, exclude, user):
    """
    search courses by vle_course_id and name according to the given query
    if the given user is not a super user, restrict visibility of courses according to the given user's courses
    """

    # text search according to given query
    f = Q(vle_course_id__icontains=q) | \
        Q(name__icontains=q)
    c = CourseKVStore.objects.filter(f)

    # if the user isn't a super user then filter by visible courses
    if not user.is_superuser:
        visible_courses = CourseMember.objects.filter(user=user).values_list('vle_course_id', flat=True)
        if not visible_courses:
            return [], 0
        c = c.filter(vle_course_id__in=visible_courses)

    # exclude given courses
    exclude_ids = [r.get('id') for r in exclude if r.get('id', '') and r.get('type', '') == u'c']
    if exclude_ids:
        c = c.exclude(vle_course_id__in=exclude_ids)

    # return a list of courses and a (total) count
    return [
        {
            u'name': u''.join([course.name, u' (', _('Module'), u')']),
            u'id': course.vle_course_id,
            u'type': u'c'
        }
        for course in c
    ], c.count()


def _get_visible_user_ids(user):
    """
    get a collection of user ids that are visible to the given user according to the given user's courses
    the given user's groups do not matter!
    the given user can message any user who is (also) a member of any of the courses that the given user is a member of
    """

    cursor = connection.cursor()
    sql = """
        SELECT DISTINCT cm1.user_id
        FROM vle_coursemember cm1
        INNER JOIN vle_coursemember cm2
            ON cm2.vle_course_id = cm1.vle_course_id
            AND cm2.user_id = %s
        WHERE cm1.user_id != %s
        ORDER BY 1
    """
    cursor.execute(sql, [user.id, user.id])

    return list(map(lambda t: t[0], cursor.fetchall()))


def _get_visible_tutor_ids(user):
    """
    if the given user is a tutor in at least one course, then that user can see all other users who are also tutors
    in at least one course (even if the two users aren't members of the same courses)
    """

    # if the given user isn't a tutor in at least one course, they can't see other tutors
    if not CourseMember.objects.filter(user=user, is_tutor=True).exists():
        return []

    # otherwise, return a list of all (other) user ids who are tutors in at least one course
    cursor = connection.cursor()
    sql = """
        SELECT DISTINCT cm.user_id
        FROM vle_coursemember cm
        WHERE cm.user_id != %s
            AND cm.is_tutor = %s
        ORDER BY 1
    """
    cursor.execute(sql, [user.id, True])

    return list(map(lambda t: t[0], cursor.fetchall()))
