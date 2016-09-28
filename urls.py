from django.conf.urls import url

from .views import read, messaging

urlpatterns = [
    url(r'^read/message/(?P<message_id>\d+)/$', read, name='read_message'),
    url(r'^$', messaging, name='messaging_home'),
]
