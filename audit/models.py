"""
Audit Log Models
"""
from django.db import models
from django.conf import settings


class AuditLog(models.Model):
    """审计日志"""

    ACTION_CHOICES = [
        ('login', '登录'),
        ('logout', '登出'),
        ('register', '注册'),
        ('password_change', '修改密码'),
        ('profile_update', '更新资料'),
        ('subscription_create', '创建订阅'),
        ('subscription_cancel', '取消订阅'),
        ('subscription_renew', '续费订阅'),
        ('refund_request', '申请退款'),
        ('invoice_request', '申请发票'),
        ('team_invite', '邀请成员'),
        ('team_accept', '接受邀请'),
        ('team_remove', '移除成员'),
        ('tenant_create', '创建租户'),
        ('tenant_update', '更新租户'),
        ('2fa_enable', '启用2FA'),
        ('2fa_disable', '禁用2FA'),
        ('account_deletion', '账户注销'),
        ('payment_callback', '支付回调'),
    ]

    # 租户
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name='租户'
    )

    # 用户
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
        verbose_name='用户'
    )

    # 操作
    action = models.CharField('操作类型', max_length=50, choices=ACTION_CHOICES, db_index=True)
    resource_type = models.CharField('资源类型', max_length=50, blank=True)
    resource_id = models.CharField('资源ID', max_length=50, blank=True)

    # 详情（JSON 格式存储）
    details = models.JSONField('详情', default=dict)

    # 请求信息
    ip_address = models.GenericIPAddressField('IP地址', null=True, blank=True)
    user_agent = models.TextField('User Agent', blank=True)

    # 时间
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'audit_log'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['user', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]

    def __str__(self):
        return f"{self.action} - {self.user} @ {self.created_at}"

    @classmethod
    def log(cls, action, user=None, tenant=None, resource_type='', resource_id='', details=None, request=None):
        """创建审计日志的便捷方法"""
        kwargs = {
            'action': action,
            'user': user,
            'tenant': tenant,
            'resource_type': resource_type,
            'resource_id': resource_id,
            'details': details or {},
        }

        if request:
            kwargs['ip_address'] = cls._get_client_ip(request)
            kwargs['user_agent'] = request.META.get('HTTP_USER_AGENT', '')[:500]

        return cls.objects.create(**kwargs)

    @staticmethod
    def _get_client_ip(request):
        """从请求中获取客户端 IP"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0].strip()
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
