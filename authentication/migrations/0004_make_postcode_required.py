# Generated manually to make postcode field required

from django.db import migrations, models


def set_default_postcode(apps, schema_editor):
    """
    Set a default postcode for users who don't have one.
    This ensures no blank values exist before we make the field non-blank.
    """
    User = apps.get_model('authentication', 'User')
    # Update users with empty or null postcodes to have a default value
    User.objects.filter(postcode__in=['', None]).update(postcode='0000')


def reverse_default_postcode(apps, schema_editor):
    """
    Reverse the default postcode setting.
    Sets postcodes back to empty string for users who had the default.
    """
    User = apps.get_model('authentication', 'User')
    # Revert the default postcode to empty string
    User.objects.filter(postcode='0000').update(postcode='')


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0003_user_city_user_postcode_user_street_address_and_more'),
    ]

    operations = [
        # First, populate empty postcodes with a default value
        migrations.RunPython(set_default_postcode, reverse_default_postcode),

        # Then, make the postcode field non-blank
        migrations.AlterField(
            model_name='user',
            name='postcode',
            field=models.CharField(blank=False, help_text='Postcode', max_length=10),
        ),
    ]
