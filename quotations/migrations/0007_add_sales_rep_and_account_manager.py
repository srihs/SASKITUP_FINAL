# Generated migration for adding assigned_sales_rep and account_manager fields

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('quotations', '0006_quotation_additional_emails'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotation',
            name='assigned_sales_rep',
            field=models.ForeignKey(
                blank=True,
                help_text='Sales representative assigned to this quotation',
                limit_choices_to={'user_type': 'sales_rep'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_quotations_sales',
                to=settings.AUTH_USER_MODEL
            ),
        ),
        migrations.AddField(
            model_name='quotation',
            name='account_manager',
            field=models.ForeignKey(
                blank=True,
                help_text='Account manager assigned to this quotation',
                limit_choices_to={'user_type': 'account_manager'},
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_quotations_manager',
                to=settings.AUTH_USER_MODEL
            ),
        ),
    ]
