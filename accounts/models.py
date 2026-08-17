"""
Accounts App Models
"""
from django.db import models
from django.conf import settings
from django.utils import timezone
import hashlib
import json


class TwoFactorAuth(models.Model):
    """二次认证配置"""

    METHOD_CHOICES = [
        ('totp', 'TOTP authenticator'),
        ('sms', 'SMS code'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='two_factor_auth',
        verbose_name='用户'
    )
    enabled = models.BooleanField('是否启用', default=False)
    method = models.CharField('认证方式', max_length=10, choices=METHOD_CHOICES, default='totp')
    secret = models.CharField('TOTP密钥', max_length=64, blank=True)
    backup_codes = models.JSONField('备用码哈希列表', default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'accounts_two_factor_auth'

    def __str__(self):
        return f"2FA for {self.user.username} - {'enabled' if self.enabled else 'disabled'}"

    def get_backup_codes_plain(self) -> list:
        """获取明文备份码（仅在新设置时调用）"""
        # backup_codes 存储的是哈希后的值，这里用于初始设置时返回明文
        return []

    @staticmethod
    def hash_code(code: str) -> str:
        """哈希备份码"""
        return hashlib.sha256(code.encode()).hexdigest()


class AccountDeletionRequest(models.Model):
    """账户注销申请"""

    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
        ('completed', '已完成'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='deletion_requests',
        verbose_name='用户'
    )
    reason = models.TextField('注销原因', blank=True)
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_at = models.DateTimeField('申请时间', auto_now_add=True)
    processed_at = models.DateTimeField('处理时间', null=True, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_deletions',
        verbose_name='处理人'
    )
    # 数据匿名化标记
    data_anonymized = models.BooleanField('数据已匿名化', default=False)
    anonymized_at = models.DateTimeField('匿名化时间', null=True, blank=True)

    class Meta:
        db_table = 'accounts_deletion_request'
        ordering = ['-requested_at']

    def __str__(self):
        return f"Deletion request for {self.user.username} - {self.status}"


class SMSCode(models.Model):
    """短信验证码记录"""

    PURPOSE_CHOICES = [
        ('register', '注册'),
        ('login', '登录'),
    ]

    phone = models.CharField('手机号', max_length=20, db_index=True)
    code = models.CharField('验证码', max_length=6)
    purpose = models.CharField('用途', max_length=20, choices=PURPOSE_CHOICES)
    is_used = models.BooleanField('已使用', default=False)
    expires_at = models.DateTimeField('过期时间')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_sms_code'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.phone} - {self.purpose}"

    def is_expired(self):
        return timezone.now() > self.expires_at


class EmailVerification(models.Model):
    """邮箱验证码记录（保留用于公司邮箱验证）"""

    email = models.EmailField('邮箱', db_index=True)
    hashed_token = models.CharField('Token哈希', max_length=64, unique=True, db_index=True)
    token_type = models.CharField('类型', max_length=20, default='register')
    is_used = models.BooleanField('已使用', default=False)
    expires_at = models.DateTimeField('过期时间')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_email_verification'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.email} - {self.token_type}"

    def is_expired(self):
        return timezone.now() > self.expires_at

    def mark_used(self):
        self.is_used = True
        self.save(update_fields=['is_used'])

    @classmethod
    def create_verification(cls, email: str, token: str, token_type: str = 'register') -> 'EmailVerification':
        """创建验证码记录"""
        from .verification import hash_token
        return cls.objects.create(
            email=email,
            hashed_token=hash_token(token),
            token_type=token_type,
            expires_at=timezone.now() + timezone.timedelta(hours=24),
        )
