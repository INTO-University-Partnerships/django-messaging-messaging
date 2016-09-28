from django.utils.translation import ugettext_lazy as _

from cms.app_base import CMSApp
from cms.apphook_pool import apphook_pool


class MessagingApp(CMSApp):
    name = _('Messaging app')
    urls = ['messaging.urls']

apphook_pool.register(MessagingApp)
