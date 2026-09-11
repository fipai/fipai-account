from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_encrypt_totp_secrets'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AccountProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('account_type', models.CharField(choices=[('personal', '个人'), ('enterprise', '企业')], default='personal', max_length=16, verbose_name='账户类型')),
                ('display_name', models.CharField(blank=True, max_length=64, verbose_name='显示名')),
                ('wechat_unionid', models.CharField(blank=True, db_index=True, max_length=64, verbose_name='微信 unionid')),
                ('wechat_openid', models.CharField(blank=True, db_index=True, max_length=64, verbose_name='微信 openid')),
                ('avatar_url', models.URLField(blank=True)),
                ('region', models.CharField(blank=True, max_length=32)),
                ('tos_accepted_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL, verbose_name='用户')),
            ],
            options={
                'db_table': 'accounts_profile',
            },
        ),
        migrations.AddIndex(
            model_name='accountprofile',
            index=models.Index(fields=['wechat_unionid'], name='accounts_pro_wechat__idx'),
        ),
        migrations.AddIndex(
            model_name='accountprofile',
            index=models.Index(fields=['wechat_openid'], name='accounts_pro_wechat_2_idx'),
        ),
    ]
