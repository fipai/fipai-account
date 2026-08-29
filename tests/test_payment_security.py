from decimal import Decimal
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from payments.models import PaymentConflictError, PaymentTransaction
from subscriptions.models import Subscription, SubscriptionPlan


class StubQueryGateway:
    def __init__(self, response):
        self.response = response
        self.queries = []

    def query_order(self, out_trade_no):
        self.queries.append(out_trade_no)
        return self.response


class StubPaidCallbackGateway:
    def __init__(self, out_trade_no, amount, trade_no):
        self.data = {
            'out_trade_no': out_trade_no,
            'trade_status': 'paid',
            'amount': Decimal(amount),
            'trade_no': trade_no,
        }

    def parse_callback(self, data, headers, raw_body):
        return dict(self.data)

    def get_trade_status(self, data):
        return data['out_trade_no'], data['trade_status'], data['amount']


class PaymentSecurityTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            username='payment_query_security',
            password='testpass123',
        )
        self.client.force_authenticate(self.user)
        self.low_plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='starter',
            name='Low Price Plan',
            period='monthly',
            price=Decimal('1.00'),
        )
        self.high_plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='High Price Plan',
            period='monthly',
            price=Decimal('999.00'),
        )
        self.low_subscription = Subscription.objects.create(
            user=self.user,
            plan=self.low_plan,
            status='active',
        )
        self.high_subscription = Subscription.objects.create(
            user=self.user,
            plan=self.high_plan,
            status='pending',
        )
        self.low_payment = PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.low_subscription,
            gateway='alipay',
            amount=Decimal('1.00'),
            out_trade_no='LOW-PAID-ORDER',
            trade_no='LOW-GATEWAY-TRADE',
            status='paid',
            subject='Low Price Plan',
        )
        self.high_payment = PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.high_subscription,
            gateway='alipay',
            amount=Decimal('999.00'),
            out_trade_no='HIGH-PENDING-ORDER',
            subject='High Price Plan',
        )
        self.query_url = reverse('payments-query')

    def _paid_query_data(self, **changes):
        data = {
            'status': 'paid',
            'out_trade_no': self.high_payment.out_trade_no,
            'amount': Decimal('999.00'),
            'currency': 'CNY',
            'trade_no': 'HIGH-GATEWAY-TRADE',
        }
        data.update(changes)
        return {'code': 0, 'message': 'success', 'data': data}

    def assert_high_payment_pending(self):
        self.high_payment.refresh_from_db()
        self.high_subscription.refresh_from_db()
        self.assertEqual(self.high_payment.status, 'pending')
        self.assertEqual(self.high_subscription.status, 'pending')

    def test_payment_id_cannot_be_combined_with_another_paid_order_number(self):
        gateway = StubQueryGateway(self._paid_query_data())
        with patch('payments.views.get_gateway', return_value=gateway):
            response = self.client.get(self.query_url, {
                'payment_id': self.high_payment.pk,
                'out_trade_no': self.low_payment.out_trade_no,
            })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(gateway.queries, [])
        self.assert_high_payment_pending()

    def test_query_uses_only_locked_local_order_number(self):
        gateway = StubQueryGateway(self._paid_query_data())
        with patch('payments.views.get_gateway', return_value=gateway):
            response = self.client.get(
                self.query_url,
                {'payment_id': self.high_payment.pk},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(gateway.queries, [self.high_payment.out_trade_no])
        self.high_payment.refresh_from_db()
        self.assertEqual(self.high_payment.status, 'paid')
        self.assertEqual(self.high_payment.trade_no, 'HIGH-GATEWAY-TRADE')

    def test_paid_query_rejects_wrong_or_missing_identity_fields(self):
        cases = {
            'wrong_order': {'out_trade_no': self.low_payment.out_trade_no},
            'missing_order': {'out_trade_no': None},
            'wrong_amount': {'amount': Decimal('1.00')},
            'missing_amount': {'amount': None},
            'wrong_currency': {'currency': 'USD'},
            'missing_currency': {'currency': None},
            'empty_trade_no': {'trade_no': '   '},
            'missing_trade_no': {'trade_no': None},
        }
        for case_name, changes in cases.items():
            with self.subTest(case=case_name):
                gateway = StubQueryGateway(self._paid_query_data(**changes))
                with patch('payments.views.get_gateway', return_value=gateway):
                    response = self.client.get(
                        self.query_url,
                        {'payment_id': self.high_payment.pk},
                    )
                self.assertEqual(response.status_code, 400)
                self.assert_high_payment_pending()

    def test_query_rejects_trade_number_bound_to_another_payment(self):
        gateway = StubQueryGateway(self._paid_query_data(
            trade_no=self.low_payment.trade_no,
        ))
        with patch('payments.views.get_gateway', return_value=gateway):
            response = self.client.get(
                self.query_url,
                {'payment_id': self.high_payment.pk},
            )

        self.assertEqual(response.status_code, 400)
        self.assert_high_payment_pending()

    def test_callback_rejects_empty_or_cross_order_trade_number(self):
        for trade_no in ('', self.low_payment.trade_no):
            with self.subTest(trade_no=trade_no):
                gateway = StubPaidCallbackGateway(
                    self.high_payment.out_trade_no,
                    self.high_payment.amount,
                    trade_no,
                )
                with patch('payments.views.get_gateway', return_value=gateway):
                    response = self.client.post(
                        '/api/payments/callback/alipay/',
                        {'untrusted': 'outer-data'},
                        format='json',
                    )
                self.assertEqual(response.status_code, 400)
                self.assert_high_payment_pending()

    def test_mark_paid_rechecks_cross_order_conflict_under_lock(self):
        with self.assertRaises(PaymentConflictError):
            self.high_payment.mark_paid(self.low_payment.trade_no)
        self.assert_high_payment_pending()

    def test_model_constraint_rejects_same_gateway_nonempty_trade_number(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            PaymentTransaction.objects.create(
                user=self.user,
                subscription=self.high_subscription,
                gateway=self.low_payment.gateway,
                amount=Decimal('999.00'),
                out_trade_no='CONSTRAINT-DUPLICATE-ORDER',
                trade_no=self.low_payment.trade_no,
                status='paid',
                subject='Duplicate gateway transaction',
            )

    def test_model_constraint_allows_empty_or_different_gateway_trade_number(self):
        PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.high_subscription,
            gateway='alipay',
            amount=Decimal('999.00'),
            out_trade_no='EMPTY-TRADE-ORDER',
            trade_no='',
            subject='Empty trade number',
        )
        PaymentTransaction.objects.create(
            user=self.user,
            subscription=self.high_subscription,
            gateway='wechat',
            amount=Decimal('999.00'),
            out_trade_no='OTHER-GATEWAY-ORDER',
            trade_no=self.low_payment.trade_no,
            status='paid',
            subject='Same trade number on another gateway',
        )


class GatewayQueryNormalizationTest(TestCase):
    def test_alipay_query_normalizes_identity_amount_and_cny(self):
        from payments.gateways.alipay import AlipayGateway

        gateway = AlipayGateway.__new__(AlipayGateway)
        gateway.mock_enabled = False
        gateway.alipay = Mock()
        gateway.alipay.api_alipay_trade_query.return_value = {
            'trade_status': 'TRADE_SUCCESS',
            'out_trade_no': 'ALI-ORDER',
            'trade_no': 'ALI-TRADE',
            'total_amount': '10.25',
        }

        result = gateway.query_order('ALI-ORDER')

        self.assertEqual(result['data'], {
            'status': 'paid',
            'out_trade_no': 'ALI-ORDER',
            'trade_no': 'ALI-TRADE',
            'amount': Decimal('10.25'),
            'currency': 'CNY',
        })

    def test_wechat_query_uses_response_amount_and_currency(self):
        from payments.gateways.wechat import WechatGateway

        gateway = WechatGateway.__new__(WechatGateway)
        gateway.mock_enabled = False
        gateway.wxpay = Mock()
        gateway.wxpay.query.return_value = (0, {
            'trade_state': 'SUCCESS',
            'out_trade_no': 'WX-ORDER',
            'transaction_id': 'WX-TRADE',
            'amount': {'total': 1025, 'currency': 'CNY'},
        })

        result = gateway.query_order('WX-ORDER')

        self.assertEqual(result['data'], {
            'status': 'paid',
            'out_trade_no': 'WX-ORDER',
            'trade_no': 'WX-TRADE',
            'amount': Decimal('10.25'),
            'currency': 'CNY',
        })

    def test_query_sdk_exception_is_not_exposed(self):
        from payments.gateways.alipay import AlipayGateway

        gateway = AlipayGateway.__new__(AlipayGateway)
        gateway.mock_enabled = False
        gateway.alipay = Mock()
        gateway.alipay.api_alipay_trade_query.side_effect = RuntimeError(
            'sdk-secret-detail'
        )

        result = gateway.query_order('ALI-ORDER')

        self.assertEqual(result, {
            'code': 1,
            'message': 'query failed',
            'data': None,
        })
        self.assertNotIn('sdk-secret-detail', str(result))
