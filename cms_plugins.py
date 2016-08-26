from django.conf import settings
from django.utils.translation import gettext as _

from cms.plugin_base import CMSPluginBase
from cms.plugin_pool import plugin_pool
from cms.models.pluginmodel import CMSPlugin


class NotificationsPlugin(CMSPluginBase):
    model = CMSPlugin
    render_template = 'notifications.html'
    cache = False

    def render(self, context, instance, placeholder):
        data = {
            'trans': [
                ('no_notifications', _('You have no notifications')),
            ],
            'show_message_item_ids': settings.DEBUG,
            'angularjs_debug': settings.ANGULARJS_DEBUG,
        }
        context.update(data)
        return context


plugin_pool.register_plugin(NotificationsPlugin)
