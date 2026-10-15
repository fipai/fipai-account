from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0006_account_profile'),
    ]

    operations = [
        migrations.AddField(
            model_name='smscode',
            name='email',
            field=models.EmailField(blank=True, db_index=True, max_length=254, verbose_name='邮箱'),
        ),
        migrations.AlterField(
            model_name='smscode',
            name='phone',
            field=models.CharField(blank=True, max_length=20, verbose_name='手机号'),
        ),
        migrations.AddIndex(
            model_name='smscode',
            index=models.Index(
                fields=['phone', 'purpose', 'is_used'],
                name='acct_sms_phone_purpose_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='smscode',
            index=models.Index(
                fields=['email', 'purpose', 'is_used'],
                name='acct_sms_email_purpose_idx',
            ),
        ),
    ]
