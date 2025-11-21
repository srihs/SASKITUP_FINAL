# Generated manually for sync logging feature
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('schools', '0005_add_cin7_contact_address_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='SyncLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_id', models.CharField(db_index=True, help_text='Unique session identifier for grouping related logs', max_length=255)),
                ('entity_type', models.CharField(choices=[('cin7_contact_mapping', 'CIN7 Contact Mapping'), ('wholesale_price_update', 'Wholesale Price Update'), ('tus_price_update', 'TUS Price Update'), ('product_sync', 'Product Sync'), ('other', 'Other')], db_index=True, help_text='Type of sync operation', max_length=50)),
                ('level', models.CharField(choices=[('debug', 'Debug'), ('info', 'Info'), ('warning', 'Warning'), ('error', 'Error'), ('success', 'Success')], db_index=True, default='info', help_text='Log level (debug, info, warning, error, success)', max_length=20)),
                ('message', models.TextField(help_text='Log message content')),
                ('details', models.JSONField(blank=True, help_text='Additional structured data (e.g., counts, IDs, errors)', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='Timestamp when log was created')),
                ('user', models.ForeignKey(blank=True, help_text='User who initiated the sync operation', null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Sync Log',
                'verbose_name_plural': 'Sync Logs',
                'db_table': 'sync_logs',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='synclog',
            index=models.Index(fields=['session_id', 'created_at'], name='sync_logs_session_8f82ea_idx'),
        ),
        migrations.AddIndex(
            model_name='synclog',
            index=models.Index(fields=['entity_type', 'created_at'], name='sync_logs_entity__3f5af8_idx'),
        ),
        migrations.AddIndex(
            model_name='synclog',
            index=models.Index(fields=['level', 'created_at'], name='sync_logs_level_e66f6c_idx'),
        ),
    ]
