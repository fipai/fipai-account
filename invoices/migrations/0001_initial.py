"""
Migration: Create InvoiceRequest model
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tenants', '0003_tenant_current_plan_tenant_description_tenant_logo_and_more'),
        ('subscriptions', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='InvoiceRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('invoice_type', models.CharField(choices=[('normal', '普通发票'), ('vat', '增值税专用发票')], default='normal', max_length=20, verbose_name='发票类型')),
                ('title', models.CharField(max_length=200, verbose_name='发票抬头')),
                ('tax_id', models.CharField(blank=True, max_length=50, verbose_name='税号')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='开票金额')),
                ('status', models.CharField(choices=[('pending', '待处理'), ('approved', '已批准'), ('rejected', '已拒绝'), ('issued', '已开票')], db_index=True, default='pending', max_length=20, verbose_name='状态')),
                ('processed_at', models.DateTimeField(blank=True, null=True, verbose_name='处理时间')),
                ('process_note', models.TextField(blank=True, verbose_name='处理备注')),
                ('invoice_no', models.CharField(blank=True, max_length=50, verbose_name='发票号')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('processed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processed_invoices', to=settings.AUTH_USER_MODEL, verbose_name='处理人')),
                ('subscription', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invoice_requests', to='subscriptions.subscription', verbose_name='订阅')),
                ('tenant', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invoice_requests', to='tenants.tenant', verbose_name='租户')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invoice_requests', to=settings.AUTH_USER_MODEL, verbose_name='用户')),
            ],
            options={
                'db_table': 'invoices_request',
                'ordering': ['-created_at'],
            },
        ),
    ]
