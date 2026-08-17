"""
Teams App - 团队成员管理
"""
from django.db import models
from django.conf import settings


class TeamMember(models.Model):
    """团队成员"""

    ROLE_CHOICES = [
        ('owner', '所有者'),
        ('admin', '管理员'),
        ('member', '成员'),
        ('viewer', '访客'),
    ]

    STATUS_CHOICES = [
        ('active', '活跃'),
        ('disabled', '已禁用'),
    ]

    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='members',
        verbose_name='租户'
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='team_memberships',
        verbose_name='用户'
    )

    role = models.CharField('角色', max_length=20, choices=ROLE_CHOICES, default='member')
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='active')

    # 产品权限
    product_permissions = models.JSONField('产品权限', default=dict, blank=True)
    """
    {
        "datacognis": {"access": true, "role": "admin"},
        "agenticorcha": {"access": true, "role": "member"},
        "decisionops": {"access": false}
    }
    """

    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invited_members',
        verbose_name='邀请人'
    )

    joined_at = models.DateTimeField('加入时间', auto_now_add=True)

    class Meta:
        db_table = 'teams_member'
        unique_together = ['tenant', 'user']
        ordering = ['-joined_at']

    def __str__(self):
        return f"{self.user.email} - {self.tenant.name} ({self.role})"

    @property
    def is_admin(self):
        return self.role in ('owner', 'admin')

    def has_product_access(self, product: str) -> bool:
        """检查用户是否有某产品的访问权限"""
        perms = self.product_permissions.get(product, {})
        return perms.get('access', False)

    def set_product_permission(self, product: str, access: bool, role: str = 'member'):
        """设置产品权限"""
        if 'product_permissions' not in self.product_permissions:
            self.product_permissions = {}
        self.product_permissions[product] = {'access': access, 'role': role}
        self.save(update_fields=['product_permissions'])


class Invitation(models.Model):
    """邀请记录"""

    STATUS_CHOICES = [
        ('pending', '待接受'),
        ('accepted', '已接受'),
        ('rejected', '已拒绝'),
        ('expired', '已过期'),
    ]

    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.CASCADE,
        related_name='invitations',
        verbose_name='租户'
    )

    email = models.EmailField('被邀请邮箱', blank=True, null=True)
    phone = models.CharField('被邀请手机号', max_length=20, blank=True, null=True, db_index=True)
    role = models.CharField('角色', max_length=20, choices=TeamMember.ROLE_CHOICES, default='member')

    # 邀请人
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sent_invitations',
        verbose_name='邀请人'
    )

    # 邀请码
    code = models.CharField('邀请码', max_length=64, unique=True, db_index=True)

    # 状态
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending')

    # 过期时间
    expires_at = models.DateTimeField('过期时间')

    # 产品权限
    product_permissions = models.JSONField('产品权限', default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField('接受时间', null=True, blank=True)

    class Meta:
        db_table = 'teams_invitation'
        ordering = ['-created_at']

    def __str__(self):
        return f"邀请 {self.email or self.phone} 加入 {self.tenant.name}"

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at
