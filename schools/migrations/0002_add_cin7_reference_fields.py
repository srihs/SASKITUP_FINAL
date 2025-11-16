"""
Migration to add optional CIN7 reference fields to TUSProductVariation.

These fields allow TUS products to optionally reference their CIN7 wholesale
equivalents without requiring actual synchronization. This is for informational
purposes only and does not create a hard dependency between systems.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('schools', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='tusproductvariation',
            name='related_cin7_code',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                help_text='CIN7 product code for reference only (if a wholesale equivalent exists)'
            ),
        ),
        migrations.AddField(
            model_name='tusproductvariation',
            name='cin7_conversion_factor',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=5,
                null=True,
                help_text='Unit conversion factor to CIN7 equivalent (e.g., 3.0 for 3-pack)'
            ),
        ),
        migrations.AddField(
            model_name='tusproductvariation',
            name='is_retail_only',
            field=models.BooleanField(
                default=True,
                help_text='True if this product only exists in TUS shop (not in CIN7 wholesale)'
            ),
        ),
        migrations.AddIndex(
            model_name='tusproductvariation',
            index=models.Index(fields=['related_cin7_code'], name='tus_pv_cin7_code_idx'),
        ),
    ]
