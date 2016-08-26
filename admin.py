from django.contrib import admin

from .models import Message, MessageAttachment, MessageItem, MessageTargetUser, MessageTargetCourse, MessageTargetGroup


class MessageItemInline(admin.TabularInline):
    model = MessageItem
    exclude = ('deleted',)
    fields = ('user', 'read', 'deleted',)
    readonly_fields = ('user', 'read', 'deleted',)
    can_delete = False
    max_num = 0


class MessageTargetUserInline(admin.TabularInline):
    model = MessageTargetUser
    readonly_fields = ('user',)
    can_delete = False
    max_num = 0


class MessageTargetCourseInline(admin.TabularInline):
    model = MessageTargetCourse
    readonly_fields = ('vle_course_id',)
    can_delete = False
    max_num = 0


class MessageTargetGroupInline(admin.TabularInline):
    model = MessageTargetGroup
    readonly_fields = ('vle_course_id', 'vle_group_id',)
    can_delete = False
    max_num = 0


class MessageAttachmentInline(admin.TabularInline):
    model = MessageAttachment
    readonly_fields = ('file',)
    can_delete = False
    max_num = 0


class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'subject', 'body', 'sent', 'is_notification',)
    list_filter = ('sent', 'is_notification',)
    search_fields = (
        'user__first_name',
        'user__last_name',
        'user__username',
        'user__email',
        'subject',
        'body',
    )
    inlines = [
        MessageItemInline,
        MessageAttachmentInline,
        MessageTargetUserInline,
        MessageTargetCourseInline,
        MessageTargetGroupInline,
    ]

    def sender(self, obj):
        return obj.user
    sender.short_description = 'Sender'


admin.site.register(Message, MessageAdmin)
