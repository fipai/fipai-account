import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0004_tenant_enterprise_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='tenant_uuid',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
