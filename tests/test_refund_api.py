"""
退款 API 测试

验证:
1. 退款申请成功创建
2. 重复退款申请被拒绝
3. 未支付的交易不能申请退款
4. 只有交易所有者可以申请退款
5. 退款状态查询
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.jwt import issue_token_pair

from payments.models import PaymentTransaction, RefundRequest
from subscriptions.models import Subscription, SubscriptionPlan


class RefundAPITestBase(TestCase):
    """Base class for refund API tests"""

    def setUp(self):
        self.client = APIClient()
        self.client.raise_request_exception = False
        self.user_model = get_user_model()

        # 创建测试用户
        self.user = self.user_model.objects.create_user(
            username='test_user_refund',
            email='refund@test.com',
            password='testpass123'
        )

        self.other_user = self.user_model.objects.create_user(
            username='other_user_refund',
            email='other@test.com',
            password='testpass123'
        )

        # 创建测试套餐
        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='DataCognis Pro',
            period='monthly',
            price=Decimal('99.00'),
        )

        # 创建待支付订阅
        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            status='active',
        )

        # 创建已支付订单
        self.payment = PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.subscription,
            gateway='alipay',
            amount=Decimal('99.00'),
            out_trade_no='FIP_REFUND_TEST_123',
            subject='DataCognis Pro Monthly',
            status='paid',
            paid_at=timezone.now(),
        )

        # 生成 JWT token
        self.access_token, _ = issue_token_pair(self.user)

    def _auth_headers(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.access_token}'}


class RefundRequestCreateTest(RefundAPITestBase):
    """退款申请创建测试"""

    def test_create_refund_success(self):
        """退款申请成功创建"""
        resp = self.client.post(
            '/api/payments/refunds/',
            {
                'transaction_id': self.payment.id,
                'reason': '服务不满意，需要退款处理，请尽快审批。'
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['status'], 'pending')
        self.assertEqual(resp.data['amount'], '99.00')

    def test_create_refund_unauthenticated(self):
        """未认证用户不能申请退款"""
        resp = self.client.post(
            '/api/payments/refunds/',
            {
                'transaction_id': self.payment.id,
                'reason': '测试退款原因，很长很长的退款原因说明。'
            },
            format='json'
        )

        self.assertEqual(resp.status_code, 401)

    def test_create_refund_not_owner(self):
        """非交易所有者不能申请退款"""
        # 为其他用户创建支付订单
        other_payment = PaymentTransaction.objects.create(
            user=self.other_user,
            subscription=self.subscription,
            gateway='alipay',
            amount=Decimal('99.00'),
            out_trade_no='FIP_REFUND_OTHER_456',
            subject='DataCognis Pro Monthly',
            status='paid',
            paid_at=timezone.now(),
        )

        resp = self.client.post(
            '/api/payments/refunds/',
            {
                'transaction_id': other_payment.id,
                'reason': '不是我的交易，退款申请应该被拒绝。'
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 400)

    def test_create_refund_unpaid_transaction(self):
        """未支付的交易不能申请退款"""
        # 创建一个待支付的订单
        pending_payment = PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.subscription,
            gateway='alipay',
            amount=Decimal('99.00'),
            out_trade_no='FIP_REFUND_PENDING_789',
            subject='DataCognis Pro Monthly',
            status='pending',
        )

        resp = self.client.post(
            '/api/payments/refunds/',
            {
                'transaction_id': pending_payment.id,
                'reason': '未支付订单申请退款理由说明。'
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 400)

    def test_create_refund_short_reason(self):
        """退款原因太短会被拒绝"""
        resp = self.client.post(
            '/api/payments/refunds/',
            {
                'transaction_id': self.payment.id,
                'reason': '太短'  # 少于10个字符
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 400)


class RefundRequestDuplicateTest(RefundAPITestBase):
    """重复退款申请测试"""

    def test_duplicate_refund_rejected(self):
        """重复退款申请被拒绝"""
        # 创建第一个退款申请
        RefundRequest.objects.create(
            user=self.user,
            transaction=self.payment,
            subscription=self.subscription,
            amount=Decimal('99.00'),
            reason='第一次退款申请理由说明。',
            status='pending'
        )

        # 尝试创建第二个退款申请
        resp = self.client.post(
            '/api/payments/refunds/',
            {
                'transaction_id': self.payment.id,
                'reason': '第二次退款申请理由说明。'
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 400)


class RefundRequestQueryTest(RefundAPITestBase):
    """退款查询测试"""

    def test_list_refunds(self):
        """用户可以查询自己的退款列表"""
        # 创建退款申请
        RefundRequest.objects.create(
            user=self.user,
            transaction=self.payment,
            subscription=self.subscription,
            amount=Decimal('99.00'),
            reason='测试退款申请原因说明。',
            status='pending'
        )

        resp = self.client.get(
            '/api/payments/refunds/',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_query_refund_status(self):
        """用户可以查询单个退款状态"""
        refund = RefundRequest.objects.create(
            user=self.user,
            transaction=self.payment,
            subscription=self.subscription,
            amount=Decimal('99.00'),
            reason='状态查询测试退款原因。',
            status='pending'
        )

        resp = self.client.get(
            f'/api/payments/refunds/{refund.id}/status/',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'pending')

    def test_cannot_query_other_user_refund(self):
        """用户不能查询其他用户的退款"""
        # 创建属于其他用户的退款
        other_refund = RefundRequest.objects.create(
            user=self.other_user,
            transaction=self.payment,
            subscription=self.subscription,
            amount=Decimal('99.00'),
            reason='其他用户的退款申请说明。',
            status='pending'
        )

        resp = self.client.get(
            f'/api/payments/refunds/{other_refund.id}/',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 404)


class RefundStateTransitionTest(TestCase):
    """退款状态机测试"""

    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username='test_user_state',
            email='state@test.com',
            password='testpass123'
        )

        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='DataCognis Pro',
            period='monthly',
            price=Decimal('99.00'),
        )

        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            status='active',
        )

        self.payment = PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.subscription,
            gateway='alipay',
            amount=Decimal('99.00'),
            out_trade_no='FIP_STATE_TEST_123',
            subject='DataCognis Pro Monthly',
            status='paid',
            paid_at=timezone.now(),
        )

    def test_refund_approve_marks_transaction_refunded(self):
        """批准退款后交易也被标记为已退款"""
        refund = RefundRequest.objects.create(
            user=self.user,
            transaction=self.payment,
            subscription=self.subscription,
            amount=Decimal('99.00'),
            reason='审批测试退款原因说明。',
            status='pending'
        )

        refund.approve(processed_by=self.user, note='审批通过')

        refund.refresh_from_db()
        self.assertEqual(refund.status, 'approved')

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'refunded')

    def test_refund_reject_preserves_transaction(self):
        """拒绝退款后交易状态保持不变"""
        refund = RefundRequest.objects.create(
            user=self.user,
            transaction=self.payment,
            subscription=self.subscription,
            amount=Decimal('99.00'),
            reason='拒绝测试退款原因说明。',
            status='pending'
        )

        refund.reject(processed_by=self.user, note='材料不全')

        refund.refresh_from_db()
        self.assertEqual(refund.status, 'rejected')

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')  # 保持不变
