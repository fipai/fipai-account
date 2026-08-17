"""
Subscriptions App - 套餐订阅系统
"""
from django.db import models
from django.conf import settings
from django.utils import timezone


class SubscriptionPlan(models.Model):
    """套餐定义"""

    PRODUCT_CHOICES = [
        ('datacognis', 'DataCognis 数据认知平台'),
        ('agenticorcha', 'AgenticOrcha 智能体编排平台'),
        ('decisionops', 'DecisionOps 智策运营平台'),
    ]

    TIER_CHOICES = [
        ('basic', '基础版'),
        ('professional', '专业版'),
        ('enterprise', '企业版'),
    ]

    PERIOD_CHOICES = [
        ('monthly', '月付'),
        ('yearly', '年付'),
    ]

    product = models.CharField('产品', max_length=50, choices=PRODUCT_CHOICES, db_index=True)
    tier = models.CharField('版本', max_length=20, choices=TIER_CHOICES)
    period = models.CharField('周期', max_length=20, choices=PERIOD_CHOICES, default='monthly')

    name = models.CharField('套餐名称', max_length=100)
    description = models.TextField('套餐描述', blank=True)

    # 价格 (单位: 元)
    price = models.DecimalField('价格', max_digits=10, decimal_places=2)

    # 功能限制
    max_users = models.IntegerField('最大用户数', default=5)
    max_api_calls = models.IntegerField('月 API 调用次数', default=10000)
    max_storage_gb = models.IntegerField('存储空间 (GB)', default=10)
    features = models.JSONField('功能列表', default=list, blank=True)

    is_active = models.BooleanField('是否上架', default=True)
    sort_order = models.IntegerField('排序', default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions_plan'
        unique_together = ['product', 'tier', 'period']
        ordering = ['product', 'sort_order']

    def __str__(self):
        return f"{self.get_product_display()} {self.get_tier_display()} {self.get_period_display()}"

    @property
    def yearly_price(self):
        """年付价格 (享折扣)"""
        return self.price * 10  # 年付 8.3 折


class Subscription(models.Model):
    """用户订阅记录"""

    STATUS_CHOICES = [
        ('active', '生效中'),
        ('pending', '待支付'),
        ('expired', '已过期'),
        ('cancelled', '已取消'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='subscriptions',
        verbose_name='用户'
    )

    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT,
        related_name='subscriptions',
        verbose_name='套餐'
    )

    # 订阅状态
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)

    # 订阅时间
    start_date = models.DateTimeField('开始时间', null=True, blank=True)
    end_date = models.DateTimeField('结束时间', null=True, blank=True)

    # 自动续费
    auto_renew = models.BooleanField('自动续费', default=True)

    # 关联的租户 (如果用户创建了企业)
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subscriptions'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'subscriptions_subscription'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.plan.name} ({self.status})"

    @property
    def is_active(self):
        return self.status == 'active' and self.end_date and self.end_date > timezone.now()

    def activate(self):
        """激活订阅"""
        from django.utils import timezone
        self.status = 'active'
        self.start_date = timezone.now()
        if self.plan.period == 'monthly':
            self.end_date = timezone.now() + timezone.timedelta(days=30)
        else:
            self.end_date = timezone.now() + timezone.timedelta(days=365)
        self.save()

    def cancel(self):
        """取消订阅"""
        self.status = 'cancelled'
        self.auto_renew = False
        self.save()
