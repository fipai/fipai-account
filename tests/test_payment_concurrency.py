"""PostgreSQL payment callback row-lock integration test."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier, Lock
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from rest_framework.test import APIClient

from payments.models import PaymentTransaction
from subscriptions.models import Subscription, SubscriptionPlan


class ConcurrentCallbackGateway:
    def __init__(self, trusted_data, barrier):
        self.trusted_data = trusted_data
        self.barrier = barrier

    def parse_callback(self, data, headers, raw_body):
        self.barrier.wait(timeout=10)
        return dict(self.trusted_data)

    def get_trade_status(self, data):
        return data['out_trade_no'], data['trade_status'], data['amount']


@skipUnless(
    connection.vendor == 'postgresql',
    'PostgreSQL is required to prove SELECT FOR UPDATE row-lock behavior.',
)
class PostgreSQLPaymentCallbackConcurrencyTest(TransactionTestCase):
    """Two concurrent callbacks for one order activate its subscription once."""

    reset_sequences = True

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='postgres_callback_concurrency',
            password='testpass123',
        )
        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='PostgreSQL Callback Concurrency',
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
            out_trade_no='PG-CONCURRENT-CALLBACK-ORDER',
            subject=self.plan.name,
        )

    @staticmethod
    def _post_callback():
        close_old_connections()
        try:
            response = APIClient().post(
                '/api/payments/callback/alipay/',
                {'outer': 'untrusted'},
                format='json',
            )
            return response.status_code, response.content
        finally:
            close_old_connections()

    def test_same_order_concurrent_callbacks_activate_subscription_once(self):
        gateway = ConcurrentCallbackGateway(
            {
                'out_trade_no': self.payment.out_trade_no,
                'trade_status': 'paid',
                'amount': Decimal('99.00'),
                'trade_no': 'PG-TRUSTED-TRADE',
            },
            Barrier(2),
        )
        original_activate = Subscription.activate
        activation_ids = []
        activation_lock = Lock()

        def counted_activate(subscription):
            with activation_lock:
                activation_ids.append(subscription.pk)
            return original_activate(subscription)

        with patch(
            'payments.views.get_gateway', return_value=gateway
        ), patch.object(Subscription, 'activate', new=counted_activate):
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(
                    executor.map(lambda _: self._post_callback(), range(2))
                )

        self.assertEqual(results, [(200, b'success'), (200, b'success')])
        self.assertEqual(activation_ids, [self.subscription.pk])
        self.payment.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(self.payment.trade_no, 'PG-TRUSTED-TRADE')
        self.assertEqual(self.subscription.status, 'active')
