from django.conf.urls import patterns, url


urlpatterns = patterns(
    '',
    url(r'^read/message/(?P<message_id>\d+)/$', 'messaging.views.read', name='read_message'),
    url(r'^$', 'messaging.views.messaging', name='messaging_home'),
)
