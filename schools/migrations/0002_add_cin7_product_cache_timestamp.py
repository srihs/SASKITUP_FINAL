# Generated manually for CIN7 price update caching feature
# Adds last_api_fetch field to Cin7Product model for 24-hour caching

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cin7product',
            name='last_api_fetch',
            field=models.DateTimeField(blank=True, db_index=True, help_text='Last time data was fetched from CIN7 API', null=True),
        ),
        migrations.AddIndex(
            model_name='cin7product',
            index=models.Index(fields=['price_type', 'last_api_fetch'], name='cin7_produc_price_t_idx'),
        ),
    ]
