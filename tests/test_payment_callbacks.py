"""
支付回调测试

验证:
1. 支付宝回调签名验证
2. 微信支付回调签名验证
3. 支付状态更新
4. 重复回调幂等性
"""
from django.test import TestCase
from django.utils import timezone
from payments.models import PaymentTransaction
from subscriptions.models import Subscription, SubscriptionPlan


class AlipayCallbackTest(TestCase):
    """支付宝回调测试"""

    def setUp(self):
        """创建测试数据"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='test_user',
            password='testpass123'
        )

        # 创建测试套餐
        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='DataCognis Pro',
            period='monthly',
            price=99.00,
        )

        # 创建待支付订阅
        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            status='pending',
        )

        # 创建待支付订单
        self.payment = PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.subscription,
            gateway='alipay',
            amount=99.00,
            out_trade_no='FIPALIPAY20231010120000ABC123',
            subject='DataCognis Pro Monthly',
        )

    def test_alipay_callback_verify_mock(self):
        """Mock 模式下支付宝回调验证通过"""
        from payments.gateways.alipay import AlipayGateway

        gateway = AlipayGateway({'sandbox': True})

        # Mock 模式下应返回 True
        result = gateway.verify_callback({'trade_status': 'TRADE_SUCCESS'})
        self.assertTrue(result)

    def test_alipay_callback_trade_status(self):
        """支付宝回调正确解析交易状态"""
        from payments.gateways.alipay import AlipayGateway

        gateway = AlipayGateway({})

        # 测试各种交易状态
        test_cases = [
            ('TRADE_SUCCESS', 'paid'),
            ('TRADE_FINISHED', 'paid'),
            ('TRADE_CLOSED', 'closed'),
            ('WAIT_BUYER_PAY', 'pending'),
        ]

        for alipay_status, expected_status in test_cases:
            out_trade_no, status, amount = gateway.get_trade_status({
                'out_trade_no': 'TEST123',
                'trade_status': alipay_status,
                'total_amount': '99.00',
            })
            self.assertEqual(status, expected_status)


class WechatPayCallbackTest(TestCase):
    """微信支付回调测试"""

    def setUp(self):
        """创建测试数据"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='test_user_wechat',
            password='testpass123'
        )

        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='DataCognis Pro',
            period='monthly',
            price=99.00,
        )

        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            status='pending',
        )

        self.payment = PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.subscription,
            gateway='wechat',
            amount=99.00,
            out_trade_no='FIPWECHAT20231010120000XYZ789',
            subject='DataCognis Pro Monthly',
        )

    def test_wechat_callback_verify_mock(self):
        """Mock 模式下微信支付回调验证通过"""
        from payments.gateways.wechat import WechatGateway

        gateway = WechatGateway({'sandbox': True})

        # Mock 模式下应返回 True
        result = gateway.verify_callback({}, {})
        self.assertTrue(result)

    def test_wechat_callback_trade_status(self):
        """微信支付回调正确解析交易状态"""
        from payments.gateways.wechat import WechatGateway

        gateway = WechatGateway({})

        test_cases = [
            ('SUCCESS', 'paid'),
            ('REFUND', 'refunded'),
            ('NOTPAY', 'pending'),
            ('CLOSED', 'closed'),
        ]

        for wechat_status, expected_status in test_cases:
            out_trade_no, status, amount = gateway.get_trade_status({
                'out_trade_no': 'TEST123',
                'trade_state': wechat_status,
                'amount': {'total': 9900},
            })
            self.assertEqual(status, expected_status)


class PaymentStateUpdateTest(TestCase):
    """支付状态更新测试"""

    def setUp(self):
        """创建测试数据"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='test_user_payment',
            password='testpass123'
        )

        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='DataCognis Pro',
            period='monthly',
            price=99.00,
        )

        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            status='pending',
        )

        self.payment = PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.subscription,
            gateway='alipay',
            amount=99.00,
            out_trade_no='FIPALIPAY20231010120000PAY123',
            subject='DataCognis Pro Monthly',
        )

    def test_mark_paid_updates_status(self):
        """标记支付后订单状态变为 paid"""
        self.payment.mark_paid('ALIPAY_TRADE_123')

        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.trade_no, 'ALIPAY_TRADE_123')
        self.assertIsNotNone(self.payment.paid_at)

    def test_mark_paid_activates_subscription(self):
        """支付成功后订阅被激活"""
        self.payment.mark_paid('ALIPAY_TRADE_123')

        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.status, 'active')

    def test_mark_paid_idempotent(self):
        """重复支付是幂等的（不会重复激活）"""
        self.payment.mark_paid('ALIPAY_TRADE_123')
        paid_at_first = self.payment.paid_at

        # 等待一小段时间
        timezone.now()

        # 再次标记支付（模拟重复回调）
        self.payment.mark_paid('ALIPAY_TRADE_456')

        self.payment.refresh_from_db()
        # 订单号不应被覆盖（幂等性）
        self.assertEqual(self.payment.trade_no, 'ALIPAY_TRADE_123')

    def test_pending_payment_only_paid_once(self):
        """只有 pending 状态的订单才能被标记为 paid"""
        # 先关闭订单
        self.payment.status = 'closed'
        self.payment.save()

        # 尝试标记为已支付
        self.payment.mark_paid('ALIPAY_TRADE_123')

        self.payment.refresh_from_db()
        # 状态不应改变
        self.assertEqual(self.payment.status, 'closed')


class PaymentIdempotencyTest(TestCase):
    """支付幂等性测试"""

    def setUp(self):
        """创建测试数据"""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.user = User.objects.create_user(
            username='test_user_idempotent',
            password='testpass123'
        )

        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='DataCognis Pro',
            period='monthly',
            price=99.00,
        )

        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            status='pending',
        )

    def test_duplicate_callback_same_trade_no(self):
        """相同交易号的重复回调应该被忽略"""
        payment = PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.subscription,
            gateway='alipay',
            amount=99.00,
            out_trade_no='FIP_IDEMPOTENT_123',
            subject='Test',
        )

        # 第一次支付成功
        payment.mark_paid('TRADE_123')

        # 模拟重复回调（同一订单号）
        payment.refresh_from_db()
        original_paid_at = payment.paid_at

        # 再次调用 mark_paid
        payment.mark_paid('TRADE_456')

        # 交易号不应被覆盖
        self.assertEqual(payment.trade_no, 'TRADE_123')
        # 支付时间不应被更新
        self.assertEqual(payment.paid_at, original_paid_at)
