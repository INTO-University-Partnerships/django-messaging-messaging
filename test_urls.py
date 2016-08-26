from django.conf.urls import *

from .urls import urlpatterns


urlpatterns = patterns(
    '',
    url(r'^irrelevant/', include('messaging.urls')),  # these URLs just need to be mounted (under anything)
    url(r'^messaging/', include('messaging.urls_json_api', namespace='messaging_api')),
    url(r'^vle/', include('vle.urls_json_api')),
) + urlpatterns
