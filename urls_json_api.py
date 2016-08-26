from django.conf.urls import patterns, url


urlpatterns = patterns(
    'messaging.views',
    url(r'^partial/$', 'partial_base', name='partial_base'),
    url(r'^partial/(?P<template>[a-zA-Z0-9/]+)$', 'partial'),
    url(r'^search/recipient/$', 'search_recipient', name='search_recipient'),
    url(r'^send/message/$', 'send_message', name='send_message'),
    url(r'^send/notification/$', 'send_notification', name='send_notification'),
    url(r'^get/notifications/$', 'get_notifications', name='get_notifications'),
    url(r'^mark/notification/read/$', 'mark_notification_read', name='mark_notification_read'),
    url(r'^get/inbox/$', 'get_inbox', name='get_inbox'),
    url(r'^get/unread/count/$', 'get_unread_count', name='get_unread_count'),
    url(r'^get/thread/$', 'get_thread', name='get_thread'),
    url(r'^get/reply/info/$', 'get_reply_info', name='get_reply_info'),
    url(r'^delete/message/item/$', 'delete_message_item', name='delete_message_item'),
)
