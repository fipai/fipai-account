# Generated manually for server-side authentication state.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0003_twofactorauth_accountdeletionrequest'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuthSession',
            fields=[
                ('sid', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('current_refresh_jti', models.CharField(max_length=255)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('revoked_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('revoked_reason', models.CharField(blank=True, max_length=64)),
                ('reuse_detected_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='auth_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'accounts_auth_session',
            },
        ),
        migrations.CreateModel(
            name='LoginChallenge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('challenge_hash', models.CharField(db_index=True, max_length=64, unique=True)),
                ('expires_at', models.DateTimeField(db_index=True)),
                ('used_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='login_challenges', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'accounts_login_challenge',
            },
        ),
        migrations.AddIndex(
            model_name='authsession',
            index=models.Index(fields=['user', 'revoked_at'], name='acct_session_user_rev_idx'),
        ),
        migrations.AddIndex(
            model_name='loginchallenge',
            index=models.Index(fields=['user', 'used_at'], name='acct_challenge_user_idx'),
        ),
    ]
