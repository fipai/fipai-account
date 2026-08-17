"""
Payments App - 支付系统
"""
from django.db import models
from django.conf import settings


class PaymentTransaction(models.Model):
    """支付交易记录"""

    GATEWAY_CHOICES = [
        ('alipay', '支付宝'),
        ('wechat', '微信支付'),
    ]

    STATUS_CHOICES = [
        ('pending', '待支付'),
        ('paid', '已支付'),
        ('refunded', '已退款'),
        ('closed', '已关闭'),
    ]

    # 用户
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='payment_transactions',
        verbose_name='用户'
    )

    # 关联订阅
    subscription = models.ForeignKey(
        'subscriptions.Subscription',
        on_delete=models.CASCADE,
        related_name='payment_transactions',
        verbose_name='订阅'
    )

    # 支付网关
    gateway = models.CharField('支付渠道', max_length=20, choices=GATEWAY_CHOICES, default='alipay')

    # 金额
    amount = models.DecimalField('支付金额', max_digits=10, decimal_places=2)

    # 交易号
    out_trade_no = models.CharField('商户订单号', max_length=64, unique=True, db_index=True)
    trade_no = models.CharField('渠道交易号', max_length=64, blank=True, db_index=True)

    # 状态
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)

    # 商品描述
    subject = models.CharField('商品描述', max_length=200)

    # 回调信息
    callback_data = models.JSONField('回调数据', default=dict, blank=True)
    callback_time = models.DateTimeField('回调时间', null=True, blank=True)

    # 时间
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField('支付时间', null=True, blank=True)

    class Meta:
        db_table = 'payments_transaction'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.out_trade_no} - {self.amount} ({self.status})"

    def mark_paid(self, trade_no: str, callback_data: dict = None):
        """标记为已支付（幂等性：只有 pending 状态才能更新为 paid）"""
        from django.utils import timezone

        # 幂等性：只有 pending 状态才能更新为 paid
        if self.status != 'pending':
            return

        self.status = 'paid'
        self.trade_no = trade_no
        self.paid_at = timezone.now()
        if callback_data:
            self.callback_data = callback_data
        self.save()

        # 激活订阅
        self.subscription.activate()

    def mark_refunded(self):
        """标记为已退款"""
        self.status = 'refunded'
        self.save()

        # 取消订阅
        if self.subscription.status == 'active':
            self.subscription.cancel()


class RefundRequest(models.Model):
    """退款申请记录"""

    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
        ('refunded', '已退款'),
    ]

    # 用户
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='refund_requests',
        verbose_name='用户'
    )

    # 关联支付交易
    transaction = models.ForeignKey(
        PaymentTransaction,
        on_delete=models.CASCADE,
        related_name='refund_requests',
        verbose_name='支付交易'
    )

    # 关联订阅
    subscription = models.ForeignKey(
        'subscriptions.Subscription',
        on_delete=models.CASCADE,
        related_name='refund_requests',
        verbose_name='订阅'
    )

    # 金额
    amount = models.DecimalField('退款金额', max_digits=10, decimal_places=2)

    # 退款原因
    reason = models.TextField('退款原因')

    # 状态
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)

    # 处理信息
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_refunds',
        verbose_name='处理人'
    )
    processed_at = models.DateTimeField('处理时间', null=True, blank=True)
    process_note = models.TextField('处理备注', blank=True)

    # 时间
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'payments_refund_request'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.amount} ({self.status})"

    def approve(self, processed_by=None, note=''):
        """批准退款"""
        from django.utils import timezone
        self.status = 'approved'
        self.processed_by = processed_by
        self.processed_at = timezone.now()
        self.process_note = note
        self.save()

        # 标记交易为已退款
        self.transaction.mark_refunded()

    def reject(self, processed_by=None, note=''):
        """拒绝退款"""
        from django.utils import timezone
        self.status = 'rejected'
        self.processed_by = processed_by
        self.processed_at = timezone.now()
        self.process_note = note
        self.save()

    def complete_refund(self):
        """完成退款"""
        self.status = 'refunded'
        self.save()
