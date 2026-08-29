"""
支付回调测试

验证:
1. 支付宝回调签名验证
2. 微信支付回调签名验证
3. 支付状态更新
4. 重复回调幂等性
"""
from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
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

    @override_settings(DEBUG=True)
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

    @override_settings(DEBUG=True)
    def test_wechat_callback_verify_mock(self):
        """Mock 模式下微信支付回调验证通过"""
        from payments.gateways.wechat import WechatGateway

        gateway = WechatGateway({'sandbox': True})

        # Mock 模式下应返回 True
        result = gateway.verify_callback({}, {}, b'{}')
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


class GatewayVerificationSecurityTest(TestCase):
    """网关配置、签名或商户绑定不可信时必须 fail-closed。"""

    @staticmethod
    def _alipay_gateway():
        from payments.gateways.alipay import AlipayGateway

        gateway = AlipayGateway.__new__(AlipayGateway)
        gateway.alipay = Mock()
        gateway.app_id = 'configured-app'
        gateway.seller_id = 'configured-seller'
        gateway.mock_enabled = False
        return gateway

    @staticmethod
    def _wechat_gateway():
        from payments.gateways.wechat import WechatGateway

        gateway = WechatGateway.__new__(WechatGateway)
        gateway.wxpay = Mock()
        gateway.mchid = 'configured-mchid'
        gateway.appid = 'configured-appid'
        gateway.mock_enabled = False
        return gateway

    @override_settings(DEBUG=False)
    @patch('payments.gateways.alipay.ALIPAY_SDK_AVAILABLE', False)
    @patch('payments.gateways.wechat.WECHAT_SDK_AVAILABLE', False)
    def test_production_missing_sdks_reject_callbacks(self):
        from payments.gateways.alipay import AlipayGateway
        from payments.gateways.wechat import WechatGateway

        self.assertIsNone(AlipayGateway({'sandbox': True}).parse_callback({}))
        self.assertIsNone(
            WechatGateway({'sandbox': True}).parse_callback({}, {}, b'{}')
        )

    @override_settings(DEBUG=False)
    @patch('payments.gateways.alipay.AliPay')
    @patch('payments.gateways.alipay.ALIPAY_SDK_AVAILABLE', True)
    def test_alipay_production_credentials_require_seller_id(self, alipay_class):
        from payments.gateways.alipay import AlipayGateway

        gateway = AlipayGateway({
            'app_id': 'app',
            'private_key': 'private',
            'public_key': 'public',
            'sandbox': False,
        })

        alipay_class.assert_not_called()
        self.assertIsNone(gateway.parse_callback({'sign': 'signature'}))

    @override_settings(DEBUG=True)
    @patch('payments.gateways.alipay.ALIPAY_SDK_AVAILABLE', False)
    @patch('payments.gateways.wechat.WECHAT_SDK_AVAILABLE', False)
    def test_development_mock_requires_explicit_sandbox(self):
        from payments.gateways.alipay import AlipayGateway
        from payments.gateways.wechat import WechatGateway

        self.assertIsNone(AlipayGateway({}).parse_callback({}))
        self.assertIsNone(WechatGateway({}).parse_callback({}, {}, b'{}'))
        self.assertIsNotNone(
            AlipayGateway({'sandbox': True}).parse_callback({'mock': True})
        )
        self.assertIsNotNone(
            WechatGateway({'sandbox': True}).parse_callback({'mock': True}, {}, b'{}')
        )

    def test_alipay_fake_sdk_accepts_only_configured_app_and_seller(self):
        gateway = self._alipay_gateway()
        gateway.alipay.verify.return_value = True
        payload = {
            'app_id': 'configured-app',
            'seller_id': 'configured-seller',
            'out_trade_no': 'ORDER',
            'sign': 'signature',
        }

        trusted = gateway.parse_callback(payload)

        self.assertEqual(trusted['out_trade_no'], 'ORDER')
        self.assertNotIn('sign', trusted)
        self.assertEqual(payload['sign'], 'signature')
        gateway.alipay.verify.assert_called_once_with(
            {
                'app_id': 'configured-app',
                'seller_id': 'configured-seller',
                'out_trade_no': 'ORDER',
            },
            'signature',
        )

        for field, wrong_value in (
            ('app_id', 'other-app'),
            ('seller_id', 'other-seller'),
        ):
            with self.subTest(field=field):
                rejected = dict(payload)
                rejected[field] = wrong_value
                self.assertIsNone(gateway.parse_callback(rejected))

    def test_alipay_missing_and_invalid_signatures_are_rejected(self):
        gateway = self._alipay_gateway()

        self.assertIsNone(gateway.parse_callback({'out_trade_no': 'ORDER'}))
        gateway.alipay.verify.return_value = False
        self.assertIsNone(gateway.parse_callback({
            'app_id': gateway.app_id,
            'seller_id': gateway.seller_id,
            'out_trade_no': 'ORDER',
            'sign': 'invalid',
        }))

    def test_wechat_fake_sdk_callback_returns_trusted_decrypted_resource(self):
        gateway = self._wechat_gateway()
        resource = {
            'mchid': gateway.mchid,
            'appid': gateway.appid,
            'out_trade_no': 'ORDER',
            'transaction_id': 'WX-TRADE',
            'trade_state': 'SUCCESS',
            'amount': {'total': 9900, 'currency': 'CNY'},
        }
        gateway.wxpay.callback.return_value = {
            'id': 'notification-id',
            'event_type': 'TRANSACTION.SUCCESS',
            'resource': resource,
        }
        raw_body = b'{"id":"notification-id","resource":{"ciphertext":"encrypted"}}'
        headers = {'Wechatpay-Signature': 'signature'}

        trusted = gateway.parse_callback(
            {'resource': {'ciphertext': 'must-not-be-read'}}, headers, raw_body
        )

        self.assertEqual(trusted, resource)
        gateway.wxpay.callback.assert_called_once_with(headers, raw_body)

    def test_wechat_rejects_wrong_mchid_appid_and_currency(self):
        gateway = self._wechat_gateway()
        valid_resource = {
            'mchid': gateway.mchid,
            'appid': gateway.appid,
            'out_trade_no': 'ORDER',
            'trade_state': 'SUCCESS',
            'amount': {'total': 9900, 'currency': 'CNY'},
        }

        cases = (
            ('mchid', 'other-mchid'),
            ('appid', 'other-appid'),
            ('currency', 'USD'),
        )
        for field, wrong_value in cases:
            with self.subTest(field=field):
                resource = {
                    **valid_resource,
                    'amount': dict(valid_resource['amount']),
                }
                if field == 'currency':
                    resource['amount']['currency'] = wrong_value
                else:
                    resource[field] = wrong_value
                gateway.wxpay.callback.return_value = {'resource': resource}
                self.assertIsNone(gateway.parse_callback({}, {'header': 'value'}, b'{}'))

    def test_wechat_outer_encrypted_resource_is_never_parsed_as_business_data(self):
        gateway = self._wechat_gateway()
        encrypted_outer = {
            'id': 'notification-id',
            'resource': {
                'algorithm': 'AEAD_AES_256_GCM',
                'ciphertext': 'encrypted',
                'nonce': 'nonce',
            },
        }
        gateway.wxpay.callback.return_value = encrypted_outer

        self.assertIsNone(
            gateway.parse_callback(encrypted_outer, {'header': 'value'}, b'raw')
        )

    def test_wechat_verify_compatibility_calls_sdk_callback_once(self):
        gateway = self._wechat_gateway()
        gateway.wxpay.callback.return_value = {
            'resource': {
                'mchid': gateway.mchid,
                'appid': gateway.appid,
                'amount': {'total': 1, 'currency': 'CNY'},
            }
        }

        self.assertTrue(gateway.verify_callback({}, {'header': 'value'}, b'raw'))
        gateway.wxpay.callback.assert_called_once_with({'header': 'value'}, b'raw')


class StubCallbackGateway:
    def __init__(self, out_trade_no, amount, verified=True, trade_no='TRADE-1'):
        self.trusted_data = {
            'out_trade_no': out_trade_no,
            'trade_status': 'paid',
            'amount': Decimal(amount),
            'trade_no': trade_no,
        }
        self.verified = verified
        self.parse_calls = []

    def parse_callback(self, data, headers, raw_body):
        self.parse_calls.append((data, headers, raw_body))
        return dict(self.trusted_data) if self.verified else None

    def get_trade_status(self, data):
        return data['out_trade_no'], data['trade_status'], data['amount']


class PaymentCallbackViewSecurityTest(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='callback_security_user',
            password='testpass123',
        )
        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='Callback Security Plan',
            period='monthly',
            price=Decimal('99.00'),
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
            amount=Decimal('99.00'),
            out_trade_no='CALLBACK-SECURITY-ORDER',
            subject='Callback Security Plan',
        )
        self.payload = {
            'out_trade_no': self.payment.out_trade_no,
            'trade_status': 'TRADE_SUCCESS',
            'total_amount': '99.00',
            'trade_no': 'OUTER-TRADE',
            'sign': 'test-signature',
        }

    def _callback(self, gateway_name, gateway):
        with patch('payments.views.get_gateway', return_value=gateway):
            return self.client.post(
                f'/api/payments/callback/{gateway_name}/',
                self.payload,
                format='json',
                HTTP_WECHATPAY_SIGNATURE='signature',
            )

    def assert_payment_unchanged(self):
        self.payment.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertEqual(self.payment.status, 'pending')
        self.assertEqual(self.subscription.status, 'pending')

    def test_invalid_signature_never_changes_state(self):
        gateway = StubCallbackGateway(
            self.payment.out_trade_no, '99.00', verified=False
        )

        response = self._callback('alipay', gateway)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content, b'failure')
        self.assert_payment_unchanged()

    def test_cross_gateway_callback_never_changes_state(self):
        gateway = StubCallbackGateway(self.payment.out_trade_no, '99.00')

        response = self._callback('wechat', gateway)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 'FAIL')
        self.assert_payment_unchanged()

    def test_amount_mismatch_never_changes_state(self):
        gateway = StubCallbackGateway(self.payment.out_trade_no, '98.99')

        response = self._callback('alipay', gateway)

        self.assertEqual(response.status_code, 400)
        self.assert_payment_unchanged()

    def test_empty_order_number_never_changes_state(self):
        gateway = StubCallbackGateway('', '99.00')

        response = self._callback('alipay', gateway)

        self.assertEqual(response.status_code, 400)
        self.assert_payment_unchanged()

    def test_view_uses_only_trusted_parsed_status_amount_and_trade_number(self):
        self.payload.update({
            'out_trade_no': 'OUTER-WRONG-ORDER',
            'trade_status': 'TRADE_CLOSED',
            'total_amount': '0.01',
            'trade_no': 'OUTER-WRONG-TRADE',
        })
        gateway = StubCallbackGateway(
            self.payment.out_trade_no, '99.00', trade_no='TRUSTED-TRADE'
        )

        response = self._callback('alipay', gateway)

        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.trade_no, 'TRUSTED-TRADE')

    def test_callback_exception_log_never_contains_exception_text_or_traceback(self):
        class RaisingGateway:
            def parse_callback(self, data, headers, raw_body):
                raise ValueError('third-party-sensitive-detail')

        with patch('payments.views.logger.warning') as warning:
            response = self._callback('alipay', RaisingGateway())

        self.assertEqual(response.status_code, 400)
        warning.assert_called_once_with(
            'payment_callback_rejected',
            extra={'gateway': 'alipay', 'error_code': 'processing_exception'},
        )

    def test_duplicate_valid_callback_is_success_and_activates_once(self):
        gateway = StubCallbackGateway(self.payment.out_trade_no, '99.00')
        original_activate = Subscription.activate
        activation_ids = []

        def counted_activate(subscription):
            activation_ids.append(subscription.pk)
            return original_activate(subscription)

        with patch.object(Subscription, 'activate', new=counted_activate):
            first = self._callback('alipay', gateway)
            second = self._callback('alipay', gateway)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.content, b'success')
        self.assertEqual(second.content, b'success')
        self.assertEqual(activation_ids, [self.subscription.pk])

        self.payment.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.trade_no, 'TRADE-1')
        self.assertEqual(self.subscription.status, 'active')
        self.assertEqual(
            set(self.payment.callback_data),
            {'gateway', 'trade_no', 'trade_status', 'amount'},
        )
        self.assertNotIn('sign', self.payment.callback_data)
        self.assertEqual(len(gateway.parse_calls), 2)
        self.assertIsInstance(gateway.parse_calls[0][2], bytes)
