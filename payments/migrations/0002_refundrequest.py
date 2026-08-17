"""
Migration: Create RefundRequest model
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('payments', '0001_initial'),
        ('subscriptions', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='RefundRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='退款金额')),
                ('reason', models.TextField(verbose_name='退款原因')),
                ('status', models.CharField(choices=[('pending', '待处理'), ('approved', '已批准'), ('rejected', '已拒绝'), ('refunded', '已退款')], db_index=True, default='pending', max_length=20, verbose_name='状态')),
                ('processed_at', models.DateTimeField(blank=True, null=True, verbose_name='处理时间')),
                ('process_note', models.TextField(blank=True, verbose_name='处理备注')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('processed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='processed_refunds', to=settings.AUTH_USER_MODEL, verbose_name='处理人')),
                ('subscription', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='refund_requests', to='subscriptions.subscription', verbose_name='订阅')),
                ('transaction', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='refund_requests', to='payments.paymenttransaction', verbose_name='支付交易')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='refund_requests', to=settings.AUTH_USER_MODEL, verbose_name='用户')),
            ],
            options={
                'db_table': 'payments_refund_request',
                'ordering': ['-created_at'],
            },
        ),
    ]
