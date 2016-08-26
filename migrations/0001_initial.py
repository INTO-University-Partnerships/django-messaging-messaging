# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
import mptt.fields
from django.conf import settings
import django.core.files.storage


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Message',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('is_notification', models.BooleanField(default=False)),
                ('url', models.URLField(blank=True)),
                ('subject', models.CharField(max_length=200, blank=True)),
                ('body', models.TextField(blank=True)),
                ('sent', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('target_all', models.BooleanField(default=False, db_index=True)),
                ('lft', models.PositiveIntegerField(editable=False, db_index=True)),
                ('rght', models.PositiveIntegerField(editable=False, db_index=True)),
                ('tree_id', models.PositiveIntegerField(editable=False, db_index=True)),
                ('level', models.PositiveIntegerField(editable=False, db_index=True)),
                ('parent', mptt.fields.TreeForeignKey(related_name='children', blank=True, to='messaging.Message', null=True)),
                ('user', models.ForeignKey(blank=True, to=settings.AUTH_USER_MODEL, null=True)),
            ],
            options={
                'abstract': False,
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='MessageAttachment',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('file', models.FileField(storage=django.core.files.storage.FileSystemStorage(location=settings.MESSAGE_ATTACHMENT_ROOT), upload_to=b'%Y/%m/%d')),
                ('message', models.ForeignKey(to='messaging.Message')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='MessageItem',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('source', models.BooleanField(default=False)),
                ('read', models.DateTimeField(db_index=True, null=True, blank=True)),
                ('deleted', models.DateTimeField(db_index=True, null=True, blank=True)),
                ('message', models.ForeignKey(to='messaging.Message')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='MessageTargetCourse',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('vle_course_id', models.CharField(max_length=100, db_index=True)),
                ('message', models.ForeignKey(to='messaging.Message')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='MessageTargetGroup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('vle_course_id', models.CharField(max_length=100, db_index=True)),
                ('vle_group_id', models.CharField(max_length=100, db_index=True)),
                ('message', models.ForeignKey(to='messaging.Message')),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.CreateModel(
            name='MessageTargetUser',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('message', models.ForeignKey(to='messaging.Message')),
                ('user', models.ForeignKey(to=settings.AUTH_USER_MODEL)),
            ],
            options={
            },
            bases=(models.Model,),
        ),
        migrations.AlterUniqueTogether(
            name='messagetargetuser',
            unique_together=set([('message', 'user')]),
        ),
        migrations.AlterUniqueTogether(
            name='messagetargetgroup',
            unique_together=set([('message', 'vle_course_id', 'vle_group_id')]),
        ),
        migrations.AlterUniqueTogether(
            name='messagetargetcourse',
            unique_together=set([('message', 'vle_course_id')]),
        ),
        migrations.AlterUniqueTogether(
            name='messageitem',
            unique_together=set([('message', 'user')]),
        ),
    ]
