"""
Payments Serializers
"""
from rest_framework import serializers
from .models import PaymentTransaction, RefundRequest


class PaymentTransactionSerializer(serializers.ModelSerializer):
    gateway_display = serializers.CharField(source='get_gateway_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'user', 'subscription', 'gateway', 'gateway_display',
            'amount', 'out_trade_no', 'trade_no', 'status', 'status_display',
            'subject', 'callback_time', 'created_at', 'updated_at', 'paid_at'
        ]
        read_only_fields = ['user', 'out_trade_no', 'trade_no', 'status']


class CreatePaymentSerializer(serializers.Serializer):
    subscription_id = serializers.IntegerField()
    gateway = serializers.ChoiceField(choices=[('alipay', '支付宝'), ('wechat', '微信支付')], default='alipay')


class RefundRequestSerializer(serializers.ModelSerializer):
    """退款申请序列化器"""
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    transaction_out_trade_no = serializers.CharField(source='transaction.out_trade_no', read_only=True)

    class Meta:
        model = RefundRequest
        fields = [
            'id', 'user', 'user_email', 'transaction', 'transaction_out_trade_no',
            'subscription', 'amount', 'reason', 'status', 'status_display',
            'processed_by', 'processed_at', 'process_note',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'transaction', 'subscription', 'status', 'processed_by', 'processed_at']


class RefundRequestCreateSerializer(serializers.Serializer):
    """创建退款申请序列化器"""
    transaction_id = serializers.IntegerField()
    reason = serializers.CharField(min_length=10, max_length=500)

    def validate_transaction_id(self, value):
        from .models import PaymentTransaction
        try:
            transaction = PaymentTransaction.objects.get(id=value)
        except PaymentTransaction.DoesNotExist:
            raise serializers.ValidationError('支付交易不存在')

        # 检查是否是自己的交易
        if transaction.user_id != self.context['request'].user.id:
            raise serializers.ValidationError('无权申请此交易的退款')

        # 检查交易状态
        if transaction.status != 'paid':
            raise serializers.ValidationError('只有已支付的交易才能申请退款')

        # 检查是否有待处理的退款申请
        if RefundRequest.objects.filter(transaction=transaction, status__in=['pending', 'approved']).exists():
            raise serializers.ValidationError('该交易已有待处理或已批准的退款申请')

        return value
