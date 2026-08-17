"""
Invoices Serializers
"""
from rest_framework import serializers
from .models import InvoiceRequest


class InvoiceRequestSerializer(serializers.ModelSerializer):
    """发票申请序列化器"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    invoice_type_display = serializers.CharField(source='get_invoice_type_display', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    tenant_name = serializers.CharField(source='tenant.name', read_only=True, allow_null=True)

    class Meta:
        model = InvoiceRequest
        fields = [
            'id', 'user', 'user_email', 'tenant', 'tenant_name',
            'subscription', 'invoice_type', 'invoice_type_display',
            'title', 'tax_id', 'amount', 'status', 'status_display',
            'processed_by', 'processed_at', 'process_note', 'invoice_no',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'tenant', 'subscription', 'status', 'processed_by', 'processed_at', 'invoice_no']


class InvoiceRequestCreateSerializer(serializers.Serializer):
    """创建发票申请序列化器"""
    invoice_type = serializers.ChoiceField(
        choices=[('normal', '普通发票'), ('vat', '增值税专用发票')],
        default='normal'
    )
    title = serializers.CharField(min_length=2, max_length=200)
    tax_id = serializers.CharField(max_length=50, required=False, allow_blank=True)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)
    subscription_id = serializers.IntegerField(required=False)

    def validate_title(self, value):
        if len(value.strip()) < 2:
            raise serializers.ValidationError('发票抬头至少2个字符')
        return value.strip()

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError('金额必须大于0')
        return value