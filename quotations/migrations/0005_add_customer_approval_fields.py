# Generated migration for adding customer approval fields to Quotation model

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('quotations', '0004_add_account_manager_edit_tracking'),
    ]

    operations = [
        # Add customer approval timestamp
        migrations.AddField(
            model_name='quotation',
            name='customer_approved_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                verbose_name="Customer Approved At",
                help_text="Timestamp when customer approved the quotation"
            ),
        ),

        # Add customer approval user reference
        migrations.AddField(
            model_name='quotation',
            name='customer_approved_by',
            field=models.ForeignKey(
                on_delete=models.SET_NULL,
                null=True,
                blank=True,
                to=settings.AUTH_USER_MODEL,
                related_name='quotations_customer_approved',
                verbose_name="Customer Approved By",
                help_text="User who gave customer approval (customer or sales rep on their behalf)"
            ),
        ),

        # Add approval override tracking
        migrations.AddField(
            model_name='quotation',
            name='approval_override_by',
            field=models.ForeignKey(
                on_delete=models.SET_NULL,
                null=True,
                blank=True,
                to=settings.AUTH_USER_MODEL,
                related_name='quotations_approval_override',
                verbose_name="Approval Override By",
                help_text="Account manager who overrode customer approval requirement"
            ),
        ),

        # Add approval override timestamp
        migrations.AddField(
            model_name='quotation',
            name='approval_override_at',
            field=models.DateTimeField(
                null=True,
                blank=True,
                verbose_name="Approval Override At",
                help_text="Timestamp when account manager overrode customer approval requirement"
            ),
        ),

        # Add index for customer approval queries
        migrations.AddIndex(
            model_name='quotation',
            index=models.Index(
                fields=['customer_approved_at', 'account_manager_approved_at'],
                name='quotation_approval_idx'
            ),
        ),
    ]
