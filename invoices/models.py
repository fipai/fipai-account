"""
Invoices Models
"""
from django.db import models
from django.conf import settings


class InvoiceRequest(models.Model):
    """发票申请记录"""

    INVOICE_TYPE_CHOICES = [
        ('normal', '普通发票'),
        ('vat', '增值税专用发票'),
    ]

    STATUS_CHOICES = [
        ('pending', '待处理'),
        ('approved', '已批准'),
        ('rejected', '已拒绝'),
        ('issued', '已开票'),
    ]

    # 用户
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='invoice_requests',
        verbose_name='用户'
    )

    # 关联租户
    tenant = models.ForeignKey(
        'tenants.Tenant',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice_requests',
        verbose_name='租户'
    )

    # 关联订阅
    subscription = models.ForeignKey(
        'subscriptions.Subscription',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invoice_requests',
        verbose_name='订阅'
    )

    # 发票类型
    invoice_type = models.CharField('发票类型', max_length=20, choices=INVOICE_TYPE_CHOICES, default='normal')

    # 发票抬头
    title = models.CharField('发票抬头', max_length=200)

    # 税号
    tax_id = models.CharField('税号', max_length=50, blank=True)

    # 金额
    amount = models.DecimalField('开票金额', max_digits=10, decimal_places=2)

    # 状态
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='pending', db_index=True)

    # 处理信息
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='processed_invoices',
        verbose_name='处理人'
    )
    processed_at = models.DateTimeField('处理时间', null=True, blank=True)
    process_note = models.TextField('处理备注', blank=True)

    # 发票号
    invoice_no = models.CharField('发票号', max_length=50, blank=True)

    # PDF URL
    pdf_url = models.URLField('PDF链接', max_length=500, blank=True)

    # 时间
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'invoices_request'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.amount} ({self.status})"

    def approve(self, processed_by=None, note=''):
        """批准开票"""
        from django.utils import timezone
        self.status = 'approved'
        self.processed_by = processed_by
        self.processed_at = timezone.now()
        self.process_note = note
        self.save()

    def reject(self, processed_by=None, note=''):
        """拒绝开票"""
        from django.utils import timezone
        self.status = 'rejected'
        self.processed_by = processed_by
        self.processed_at = timezone.now()
        self.process_note = note
        self.save()

    def issue(self, invoice_no):
        """开具发票"""
        self.status = 'issued'
        self.invoice_no = invoice_no
        self.save()