from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Tenant',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='租户名称')),
                ('slug', models.SlugField(unique=True)),
                ('domain', models.CharField(blank=True, max_length=100)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'tenants_tenant',
            },
        ),
        migrations.CreateModel(
            name='IndustryPackage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='包名称')),
                ('version', models.CharField(default='1.0.0', max_length=20)),
                ('description', models.TextField(blank=True)),
                ('category', models.CharField(default='通用', max_length=50, verbose_name='行业分类')),
                ('agents', models.JSONField(default=list, verbose_name='智能体配置')),
                ('thumbnail', models.URLField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'tenants_industrypackage',
                'ordering': ['-created_at'],
            },
        ),
    ]
