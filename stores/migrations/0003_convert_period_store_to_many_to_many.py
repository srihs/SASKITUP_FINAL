# Generated manually to convert StorePeriod.store from ForeignKey to ManyToManyField

from django.db import migrations, models


def migrate_store_to_stores(apps, schema_editor):
    """
    Migrate existing data from the old ForeignKey 'store' field
    to the new ManyToManyField 'stores' field.
    """
    StorePeriod = apps.get_model('stores', 'StorePeriod')

    # For each existing period, add the single store to the stores M2M field
    for period in StorePeriod.objects.all():
        # The old 'store' field still exists at this point in the migration
        # We need to get the store_id from the old field
        if hasattr(period, 'store_id') and period.store_id:
            period.stores.add(period.store_id)


class Migration(migrations.Migration):

    dependencies = [
        ('stores', '0002_alter_storeopeninghours_options_storeperiod_and_more'),
    ]

    operations = [
        # Step 1: Create the new ManyToManyField
        migrations.AddField(
            model_name='storeperiod',
            name='stores',
            field=models.ManyToManyField(
                help_text='Stores this period applies to',
                related_name='periods_new',  # Temporary related_name to avoid conflict
                to='stores.store'
            ),
        ),

        # Step 2: Migrate data from old field to new field
        migrations.RunPython(migrate_store_to_stores, reverse_code=migrations.RunPython.noop),

        # Step 3: Remove the old ForeignKey field
        migrations.RemoveField(
            model_name='storeperiod',
            name='store',
        ),

        # Step 4: Update the related_name on the ManyToManyField to the correct one
        migrations.AlterField(
            model_name='storeperiod',
            name='stores',
            field=models.ManyToManyField(
                help_text='Stores this period applies to',
                related_name='periods',
                to='stores.store'
            ),
        ),
    ]
