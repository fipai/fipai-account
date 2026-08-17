from django.db import models
from django.conf import settings


class Tenant(models.Model):
    """租户"""

    STATUS_CHOICES = [
        ('trial', '试用中'),
        ('active', '正式使用'),
        ('suspended', '已暂停'),
        ('cancelled', '已注销'),
    ]

    name = models.CharField(max_length=100, verbose_name="租户名称")
    slug = models.SlugField(unique=True)
    domain = models.CharField(max_length=100, blank=True)

    # 所有者
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_tenants',
        verbose_name='所有者',
        null=True,
        blank=True
    )

    # 状态
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='trial')
    is_active = models.BooleanField(default=True)

    # 订阅信息
    current_plan = models.CharField('当前套餐', max_length=50, blank=True, default='')

    # Logo 和描述
    logo = models.URLField(blank=True, verbose_name="Logo URL")
    description = models.TextField(blank=True, verbose_name="描述")

    # 配额
    max_users = models.IntegerField('最大用户数', default=5)
    max_api_calls = models.IntegerField('月 API 调用次数', default=10000)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenants_tenant"

    def __str__(self):
        return self.name

    @property
    def is_trial(self):
        return self.status == 'trial'

    @property
    def is_active_subscription(self):
        return self.status == 'active'


class Domain(models.Model):
    """域名绑定"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='domains')
    domain = models.CharField(max_length=100, unique=True)
    is_primary = models.BooleanField(default=False)
    
    class Meta:
        db_table = "tenants_domain"
    
    def __str__(self):
        return self.domain


class UsageRecord(models.Model):
    """用量记录"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='usage_records')
    date = models.DateField()
    api_calls = models.IntegerField(default=0)
    tokens_used = models.IntegerField(default=0)
    cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    class Meta:
        db_table = "tenants_usagerecord"
        unique_together = ['tenant', 'date']


class Bill(models.Model):
    """账单"""
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='bills')
    period_start = models.DateField()
    period_end = models.DateField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = "tenants_bill"


class IndustryPackage(models.Model):
    """行业包 - 预定义的智能体集合"""
    name = models.CharField(max_length=100, verbose_name="包名称")
    version = models.CharField(max_length=20, default="1.0.0")
    description = models.TextField(blank=True)
    category = models.CharField(max_length=50, verbose_name="行业分类", default="通用")
    agents = models.JSONField(default=list, verbose_name="智能体配置")
    thumbnail = models.URLField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = "tenants_industrypackage"
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.name} ({self.version})"
    
    def get_agent_count(self):
        return len(self.agents)
