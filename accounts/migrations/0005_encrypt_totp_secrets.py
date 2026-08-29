from cryptography.fernet import Fernet
from django.conf import settings
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


PREFIX = "enc:v1:"


def encrypt_existing_totp_secrets(apps, schema_editor):
    TwoFactorAuth = apps.get_model("accounts", "TwoFactorAuth")
    key_id = settings.TOTP_ENCRYPTION_KEY_ID
    key = settings.TOTP_ENCRYPTION_KEYRING.get(key_id)
    if not key:
        raise RuntimeError("The active TOTP encryption key is unavailable.")
    cipher = Fernet(key.encode("ascii"))

    records = TwoFactorAuth.objects.exclude(secret="").iterator(chunk_size=500)
    for record in records:
        if record.secret.startswith(PREFIX):
            continue
        token = cipher.encrypt(record.secret.encode("utf-8")).decode("ascii")
        record.secret = f"{PREFIX}{key_id}:{token}"
        record.save(update_fields=["secret"])


def refuse_plaintext_rollback(apps, schema_editor):
    raise IrreversibleError(
        "TOTP seed encryption cannot be reversed to plaintext storage."
    )


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_authsession_loginchallenge"),
    ]

    operations = [
        migrations.AlterField(
            model_name="twofactorauth",
            name="secret",
            field=models.CharField(
                blank=True,
                max_length=512,
                verbose_name="TOTP密钥（加密）",
            ),
        ),
        migrations.RunPython(
            encrypt_existing_totp_secrets,
            reverse_code=refuse_plaintext_rollback,
        ),
    ]
