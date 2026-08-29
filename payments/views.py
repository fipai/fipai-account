"""
Payments API Views
"""
import uuid
import logging
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny

from .models import PaymentConflictError, PaymentTransaction, RefundRequest
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
        """锁定本地订单，并仅以本地订单号查询和核验网关状态。"""
        requested_out_trade_no = request.query_params.get('out_trade_no')
        payment_id = request.query_params.get('payment_id')

        if not requested_out_trade_no and not payment_id:
            return Response(
                {'error': 'out_trade_no or payment_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                locked_payments = PaymentTransaction.objects.select_for_update().filter(
                    user=request.user
                )
                if payment_id:
                    payment = locked_payments.get(id=payment_id)
                else:
                    payment = locked_payments.get(
                        out_trade_no=requested_out_trade_no
                    )

                if (
                    payment_id
                    and requested_out_trade_no
                    and requested_out_trade_no != payment.out_trade_no
                ):
                    return Response(
                        {'error': 'payment identifiers do not match'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if payment.status != 'pending':
                    return Response({
                        'code': 0,
                        'data': {
                            'status': payment.status,
                            'paid_at': payment.paid_at,
                        },
                    })

                gateway = get_gateway(payment.gateway)
                result = gateway.query_order(payment.out_trade_no)
                if not isinstance(result, dict) or result.get('code') != 0:
                    logger.warning(
                        'payment_query_rejected',
                        extra={
                            'gateway': payment.gateway,
                            'error_code': 'gateway_query_failed',
                        },
                    )
                    return Response(
                        {'error': '支付状态验证失败'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                query_data = result.get('data')
                if not isinstance(query_data, dict):
                    return Response(
                        {'error': '支付状态验证失败'},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if query_data.get('status') == 'paid':
                    queried_trade_no = query_data.get('trade_no')
                    try:
                        queried_amount = Decimal(query_data.get('amount'))
                    except (TypeError, ValueError, ArithmeticError):
                        queried_amount = None

                    paid_response_valid = all([
                        query_data.get('out_trade_no') == payment.out_trade_no,
                        queried_amount == payment.amount,
                        query_data.get('currency') == 'CNY',
                        isinstance(queried_trade_no, str),
                        bool(queried_trade_no.strip()) if isinstance(queried_trade_no, str) else False,
                    ])
                    if not paid_response_valid:
                        return Response(
                            {'error': '支付状态验证失败'},
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                    payment.mark_paid(queried_trade_no.strip())

                return Response({
                    'code': 0,
                    'data': {
                        'status': payment.status,
                        'paid_at': payment.paid_at,
                    },
                })

        except PaymentTransaction.DoesNotExist:
            return Response(
                {'error': '订单不存在'},
                status=status.HTTP_404_NOT_FOUND,
            )
        except PaymentConflictError:
            return Response(
                {'error': '支付状态验证失败'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.warning(
                'payment_query_rejected',
                extra={'gateway': 'unknown', 'error_code': 'processing_exception'},
            )
            return Response(
                {'error': '支付状态验证失败'},
                status=status.HTTP_400_BAD_REQUEST,
            )

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
    """支付网关服务端回调。"""
    permission_classes = [AllowAny]

    @staticmethod
    def _response(gateway_name, success):
        """返回网关可识别且不泄露内部错误的稳定响应。"""
        if gateway_name == 'alipay':
            return HttpResponse(
                'success' if success else 'failure',
                status=200 if success else 400,
                content_type='text/plain',
            )
        if gateway_name == 'wechat':
            return Response(
                {
                    'code': 'SUCCESS' if success else 'FAIL',
                    'message': '成功' if success else '回调处理失败',
                },
                status=status.HTTP_200_OK if success else status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {'code': 'FAIL', 'message': '回调处理失败'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @staticmethod
    def _reject(gateway_name, error_code):
        """回调边界只记录固定事件、网关和内部错误码。"""
        logger.warning(
            'payment_callback_rejected',
            extra={'gateway': gateway_name, 'error_code': error_code},
        )

    @staticmethod
    def _trade_no(data):
        return data.get('trade_no') or data.get('transaction_id') or ''

    @staticmethod
    def _safe_callback_data(gateway_name, data, trade_status, amount):
        """仅持久化状态核对所需字段，不保存完整回调或签名。"""
        return {
            'gateway': gateway_name,
            'trade_no': PaymentCallbackView._trade_no(data),
            'trade_status': trade_status,
            'amount': str(amount),
        }

    def post(self, request, gateway_name):
        """一次验签/解密后，在行锁事务内执行订单状态转换。"""
        try:
            # 微信 SDK 必须接收未经 DRF 重编码的原始请求体。
            raw_body = request.body
            gateway = get_gateway(gateway_name)
            trusted_data = gateway.parse_callback(
                data=request.data,
                headers=request.headers,
                raw_body=raw_body,
            )
            if trusted_data is None:
                self._reject(gateway_name, 'untrusted_callback')
                return self._response(gateway_name, False)

            out_trade_no, trade_status, amount = gateway.get_trade_status(trusted_data)
            if not out_trade_no:
                self._reject(gateway_name, 'missing_order_number')
                return self._response(gateway_name, False)

            amount = Decimal(amount)
            with transaction.atomic():
                payment = (
                    PaymentTransaction.objects.select_for_update()
                    .get(out_trade_no=out_trade_no)
                )
                if payment.gateway != gateway_name:
                    self._reject(gateway_name, 'gateway_mismatch')
                    return self._response(gateway_name, False)
                if amount != payment.amount:
                    self._reject(gateway_name, 'amount_mismatch')
                    return self._response(gateway_name, False)

                if trade_status == 'paid':
                    incoming_trade_no = self._trade_no(trusted_data)
                    if not isinstance(incoming_trade_no, str) or not incoming_trade_no.strip():
                        self._reject(gateway_name, 'missing_transaction_number')
                        return self._response(gateway_name, False)
                    incoming_trade_no = incoming_trade_no.strip()

                    if (
                        payment.status == 'paid'
                        and payment.trade_no
                        and payment.trade_no != incoming_trade_no
                    ):
                        self._reject(gateway_name, 'transaction_mismatch')
                        return self._response(gateway_name, False)

                    trade_number_in_use = (
                        PaymentTransaction.objects.select_for_update()
                        .filter(
                            gateway=gateway_name,
                            trade_no=incoming_trade_no,
                        )
                        .exclude(pk=payment.pk)
                        .exists()
                    )
                    if trade_number_in_use:
                        self._reject(gateway_name, 'transaction_already_bound')
                        return self._response(gateway_name, False)

                    payment.mark_paid(
                        trade_no=incoming_trade_no,
                        callback_data=self._safe_callback_data(
                            gateway_name, trusted_data, trade_status, amount
                        ),
                    )

            return self._response(gateway_name, True)

        except PaymentTransaction.DoesNotExist:
            self._reject(gateway_name, 'order_not_found')
            return self._response(gateway_name, False)
        except PaymentConflictError:
            self._reject(gateway_name, 'transaction_already_bound')
            return self._response(gateway_name, False)
        except Exception:
            self._reject(gateway_name, 'processing_exception')
            return self._response(gateway_name, False)
