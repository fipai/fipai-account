from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0003_tenant_current_plan_tenant_description_tenant_logo_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='tenant',
            name='type',
            field=models.CharField(
                choices=[('personal', '个人租户'), ('enterprise', '企业租户')],
                default='enterprise',
                max_length=16,
                verbose_name='租户类型',
            ),
        ),
        migrations.AddField(
            model_name='tenant',
            name='uscc',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=32,
                verbose_name='统一社会信用代码',
            ),
        ),
        migrations.AddField(
            model_name='tenant',
            name='scale',
            field=models.CharField(
                blank=True,
                choices=[
                    ('1-50', '1-50 人'),
                    ('51-200', '51-200 人'),
                    ('201-500', '201-500 人'),
                    ('501-1000', '501-1000 人'),
                    ('1000+', '1000+ 人'),
                ],
                max_length=16,
                verbose_name='企业规模',
            ),
        ),
        migrations.AddField(
            model_name='tenant',
            name='industry',
            field=models.CharField(blank=True, max_length=64, verbose_name='所属行业'),
        ),
        migrations.AddField(
            model_name='tenant',
            name='legal_representative',
            field=models.CharField(blank=True, max_length=64, verbose_name='法定代表人'),
        ),
        migrations.AddField(
            model_name='tenant',
            name='verified_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='认证时间'),
        ),
    ]
