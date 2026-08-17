"""
Payments API Views
"""
import uuid
import logging
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny

from .models import PaymentTransaction, RefundRequest
from .gateways import get_gateway, get_available_gateways
from .serializers import PaymentTransactionSerializer, RefundRequestSerializer, RefundRequestCreateSerializer
from subscriptions.models import Subscription
from subscriptions.serializers import SubscriptionSerializer

logger = logging.getLogger(__name__)


class PaymentViewSet(viewsets.ModelViewSet):
    """支付管理"""
    queryset = PaymentTransaction.objects.all()
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentTransaction.objects.filter(user=self.request.user)

    @action(detail=False, methods=['post'])
    def create_order(self, request):
        """创建支付订单"""
        subscription_id = request.data.get('subscription_id')
        gateway_name = request.data.get('gateway', 'alipay')

        if not subscription_id:
            return Response({'error': 'subscription_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            subscription = Subscription.objects.get(id=subscription_id, user=request.user)
        except Subscription.DoesNotExist:
            return Response({'error': '订阅不存在'}, status=status.HTTP_404_NOT_FOUND)

        if subscription.status != 'pending':
            return Response({'error': '订阅状态不是待支付'}, status=status.HTTP_400_BAD_REQUEST)

        # 生成订单号 - 格式: FIP{gateway}{timestamp}{random}
        # 支付宝/微信订单号长度限制内，确保唯一性
        out_trade_no = f"FIP{gateway.upper()}{timezone.now().strftime('%Y%m%d%H%M%S')}{uuid.uuid4().hex[:6].upper()}"

        # 计算金额
        amount = subscription.plan.price
        if subscription.plan.period == 'yearly':
            amount = subscription.plan.yearly_price

        # 构建回调URL
        base_url = getattr(settings, 'BASE_URL', 'https://account.fipai.cn')
        notify_url = f"{base_url}/api/payments/callback/{gateway_name}/"

        # 创建支付订单
        payment = PaymentTransaction.objects.create(
            user=request.user,
            subscription=subscription,
            gateway=gateway_name,
            amount=amount,
            out_trade_no=out_trade_no,
            subject=f"{subscription.plan.get_product_display()} {subscription.plan.get_tier_display()}",
        )

        # 调用支付网关
        try:
            gateway = get_gateway(gateway_name)
            result = gateway.create_order(
                out_trade_no=out_trade_no,
                amount=amount,
                subject=payment.subject,
                notify_url=notify_url,
                return_url=f"{base_url}/subscriptions"
            )

            if result['code'] == 0:
                return Response({
                    'code': 0,
                    'message': 'success',
                    'data': {
                        'payment_id': payment.id,
                        'out_trade_no': out_trade_no,
                        'trade_no': result['data'].get('trade_no'),
                        'pay_url': result['data'].get('pay_url'),
                        'qr_code': result['data'].get('qr_code') or result['data'].get('code_url'),
                        'amount': str(amount),
                        'subject': payment.subject,
                    }
                })
            else:
                payment.status = 'closed'
                payment.save()
                return Response({'error': result['message']}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(f"Create payment order failed: {e}")
            payment.status = 'closed'
            payment.save()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'])
    def query(self, request):
        """查询订单状态"""
        out_trade_no = request.query_params.get('out_trade_no')
        payment_id = request.query_params.get('payment_id')

        if not out_trade_no and not payment_id:
            return Response({'error': 'out_trade_no or payment_id is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if payment_id:
                payment = PaymentTransaction.objects.get(id=payment_id, user=request.user)
            else:
                payment = PaymentTransaction.objects.get(out_trade_no=out_trade_no, user=request.user)

            if payment.status != 'pending':
                return Response({
                    'code': 0,
                    'data': {
                        'status': payment.status,
                        'paid_at': payment.paid_at,
                    }
                })

            # 查询支付网关
            gateway = get_gateway(payment.gateway)
            result = gateway.query_order(out_trade_no)

            if result['code'] == 0 and result['data'].get('status') == 'paid':
                payment.mark_paid(result['data'].get('trade_no', ''))

            return Response({
                'code': 0,
                'data': {
                    'status': payment.status,
                    'paid_at': payment.paid_at,
                }
            })

        except PaymentTransaction.DoesNotExist:
            return Response({'error': '订单不存在'}, status=status.HTTP_404_NOT_FOUND)

    @action(detail=False, methods=['get'])
    def available_gateways(self, request):
        """获取可用的支付渠道"""
        gateways = get_available_gateways()
        return Response({'code': 0, 'data': gateways})


class RefundRequestViewSet(viewsets.ModelViewSet):
    """退款申请管理"""
    queryset = RefundRequest.objects.all()
    permission_classes = [IsAuthenticated]
    serializer_class = RefundRequestSerializer

    def get_queryset(self):
        """只返回当前用户的退款申请"""
        return RefundRequest.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        """用户提交退款申请"""
        serializer = RefundRequestCreateSerializer(data=request.data, context={'request': request})
        if not serializer.is_valid():
            return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

        transaction_id = serializer.validated_data['transaction_id']
        reason = serializer.validated_data['reason']

        transaction = PaymentTransaction.objects.get(id=transaction_id)

        # 创建退款申请
        refund = RefundRequest.objects.create(
            user=request.user,
            transaction=transaction,
            subscription=transaction.subscription,
            amount=transaction.amount,
            reason=reason,
            status='pending'
        )

        return Response(
            RefundRequestSerializer(refund).data,
            status=status.HTTP_201_CREATED
        )

    @action(detail=True, methods=['get'])
    def status(self, request, pk=None):
        """查询退款状态"""
        refund = self.get_object()
        return Response({
            'id': refund.id,
            'status': refund.status,
            'status_display': refund.get_status_display(),
            'amount': str(refund.amount),
            'reason': refund.reason,
            'processed_at': refund.processed_at,
            'process_note': refund.process_note,
            'created_at': refund.created_at,
        })


class PaymentCallbackView(APIView):
    """支付回调"""
    permission_classes = [AllowAny]

    def post(self, request, gateway_name):
        """处理支付回调"""
        try:
            gateway = get_gateway(gateway_name)

            # 验证签名
            if not gateway.verify_callback(request.data):
                logger.warning(f"Payment callback verify failed: {request.data}")
                return Response({'code': 1, 'message': 'verify failed'})

            # 获取交易状态
            out_trade_no, trade_status, amount = gateway.get_trade_status(request.data)

            # 更新订单
            try:
                payment = PaymentTransaction.objects.get(out_trade_no=out_trade_no)

                if trade_status == 'paid' and payment.status == 'pending':
                    payment.mark_paid(
                        trade_no=request.data.get('trade_no', ''),
                        callback_data=request.data
                    )
                    logger.info(f"Payment completed: {out_trade_no}")

                return Response({'code': 0, 'message': 'success'})

            except PaymentTransaction.DoesNotExist:
                logger.error(f"Payment not found: {out_trade_no}")
                return Response({'code': 1, 'message': 'order not found'})

        except Exception as e:
            logger.error(f"Payment callback error: {e}")
            return Response({'code': 1, 'message': str(e)})
