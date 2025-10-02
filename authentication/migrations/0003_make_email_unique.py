# Generated manually for email-based authentication

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_add_account_manager_user_type'),
    ]

    operations = [
        # First, ensure all existing users have an email
        # We'll set a default email for any users without one
        migrations.RunSQL(
            sql="""
                UPDATE authentication_user
                SET email = CONCAT(username, '@saskitup.local')
                WHERE email = '' OR email IS NULL;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),

        # Make email field unique
        migrations.AlterField(
            model_name='user',
            name='email',
            field=models.EmailField(
                help_text='Email address - used for login',
                unique=True,
                max_length=254
            ),
        ),
    ]
