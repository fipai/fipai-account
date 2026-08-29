from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from payments.models import PaymentTransaction
from subscriptions.models import Subscription, SubscriptionPlan


class PaymentTradeNumberMigrationTest(TransactionTestCase):
    migrate_from = ('payments', '0002_refundrequest')
    migrate_to = ('payments', '0003_unique_gateway_trade_no')

    def setUp(self):
        super().setUp()
        MigrationExecutor(connection).migrate([self.migrate_from])

        self.user = get_user_model().objects.create_user(
            username='payment_migration_duplicate',
            password='testpass123',
        )
        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='Payment migration plan',
            period='monthly',
            price=Decimal('10.00'),
        )
        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            status='pending',
        )

    def tearDown(self):
        PaymentTransaction.objects.all().delete()
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_migration_rejects_existing_nonempty_gateway_trade_duplicates(self):
        common = {
            'user': self.user,
            'subscription': self.subscription,
            'gateway': 'alipay',
            'amount': Decimal('10.00'),
            'trade_no': 'EXISTING-DUPLICATE-TRADE',
            'status': 'paid',
            'subject': 'Duplicate migration fixture',
        }
        PaymentTransaction.objects.create(
            out_trade_no='MIGRATION-DUPLICATE-ONE',
            **common,
        )
        PaymentTransaction.objects.create(
            out_trade_no='MIGRATION-DUPLICATE-TWO',
            **common,
        )

        with self.assertRaises(RuntimeError) as raised:
            MigrationExecutor(connection).migrate([self.migrate_to])

        message = str(raised.exception)
        self.assertIn('existing non-empty duplicates must be resolved first', message)
        self.assertIn('alipay:EXISTING-DUPLICATE-TRADE (2 rows)', message)
