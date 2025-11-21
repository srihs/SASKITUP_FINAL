# Generated manually to make postcode field optional
# Postcode should only be required for customers, not admin/sales_rep/account_manager users

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0004_make_postcode_required'),
    ]

    operations = [
        # Make the postcode field optional (blank=True)
        # This allows admin, sales rep, and account manager users to be created without postcodes
        # Customers who need delivery addresses should still provide postcodes
        migrations.AlterField(
            model_name='user',
            name='postcode',
            field=models.CharField(
                blank=True,
                help_text='Postcode (required for customers)',
                max_length=10
            ),
        ),
    ]
