"""
多租户数据隔离测试

验证:
1. 租户 A 无法查询租户 B 的订阅
2. 租户 A 无法查询租户 B 的团队成员
3. 租户 A 无法查询租户 B 的邀请记录
4. 租户 A 无法查询租户 B 的退款记录
5. 租户 A 无法查询租户 B 的发票记录
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from accounts.jwt import issue_token_pair

from invoices.models import InvoiceRequest
from payments.models import PaymentTransaction, RefundRequest
from subscriptions.models import Subscription, SubscriptionPlan
from tenants.models import Tenant
from teams.models import TeamMember, Invitation


class TenantIsolationTestBase(TestCase):
    """Base class for tenant isolation tests"""

    def setUp(self):
        self.client = APIClient()
        self.client.raise_request_exception = False
        self.user_model = get_user_model()

        # 创建两个租户的用户
        self.user_a = self.user_model.objects.create_user(
            username='tenant_a_user',
            email='tenant_a@test.com',
            password='testpass123'
        )

        self.user_b = self.user_model.objects.create_user(
            username='tenant_b_user',
            email='tenant_b@test.com',
            password='testpass123'
        )

        # 创建租户 A 和 B
        self.tenant_a = Tenant.objects.create(
            name='Tenant A Company',
            slug='tenant-a-slug',
        )

        self.tenant_b = Tenant.objects.create(
            name='Tenant B Company',
            slug='tenant-b-slug',
        )

        # 设置成员关系
        TeamMember.objects.create(
            tenant=self.tenant_a,
            user=self.user_a,
            role='owner',
            status='active'
        )

        TeamMember.objects.create(
            tenant=self.tenant_b,
            user=self.user_b,
            role='owner',
            status='active'
        )

        # 创建套餐
        self.plan = SubscriptionPlan.objects.create(
            product='datacognis',
            tier='professional',
            name='DataCognis Pro',
            period='monthly',
            price=Decimal('99.00'),
        )

        # 创建订阅 - 租户 A
        self.subscription_a = Subscription.objects.create(
            user=self.user_a,
            plan=self.plan,
            tenant=self.tenant_a,
            status='active',
        )

        # 创建订阅 - 租户 B
        self.subscription_b = Subscription.objects.create(
            user=self.user_b,
            plan=self.plan,
            tenant=self.tenant_b,
            status='active',
        )

        # 创建支付交易 - 租户 A
        self.payment_a = PaymentTransaction.objects.create(
            user=self.user_a,
            subscription=self.subscription_a,
            gateway='alipay',
            amount=Decimal('99.00'),
            out_trade_no='TENANT_A_PAY_123',
            subject='Tenant A Subscription',
            status='paid',
            paid_at=timezone.now(),
        )

        # 创建支付交易 - 租户 B
        self.payment_b = PaymentTransaction.objects.create(
            user=self.user_b,
            subscription=self.subscription_b,
            gateway='alipay',
            amount=Decimal('99.00'),
            out_trade_no='TENANT_B_PAY_456',
            subject='Tenant B Subscription',
            status='paid',
            paid_at=timezone.now(),
        )

        # 创建退款 - 租户 A
        self.refund_a = RefundRequest.objects.create(
            user=self.user_a,
            transaction=self.payment_a,
            subscription=self.subscription_a,
            amount=Decimal('99.00'),
            reason='Tenant A refund reason',
            status='pending'
        )

        # 创建退款 - 租户 B
        self.refund_b = RefundRequest.objects.create(
            user=self.user_b,
            transaction=self.payment_b,
            subscription=self.subscription_b,
            amount=Decimal('99.00'),
            reason='Tenant B refund reason',
            status='pending'
        )

        # 创建发票 - 租户 A
        self.invoice_a = InvoiceRequest.objects.create(
            user=self.user_a,
            tenant=self.tenant_a,
            invoice_type='normal',
            title='Tenant A Company',
            amount=Decimal('99.00'),
            status='pending'
        )

        # 创建发票 - 租户 B
        self.invoice_b = InvoiceRequest.objects.create(
            user=self.user_b,
            tenant=self.tenant_b,
            invoice_type='normal',
            title='Tenant B Company',
            amount=Decimal('99.00'),
            status='pending'
        )

        # 创建邀请 - 租户 A
        self.invitation_a = Invitation.objects.create(
            tenant=self.tenant_a,
            email='invite_a@test.com',
            role='member',
            invited_by=self.user_a,
            code='TENANT_A_INVITE_CODE',
            expires_at=timezone.now() + timezone.timedelta(days=7)
        )

        # 创建邀请 - 租户 B
        self.invitation_b = Invitation.objects.create(
            tenant=self.tenant_b,
            email='invite_b@test.com',
            role='member',
            invited_by=self.user_b,
            code='TENANT_B_INVITE_CODE',
            expires_at=timezone.now() + timezone.timedelta(days=7)
        )

        # 生成 JWT tokens
        self.access_token_a, _ = issue_token_pair(self.user_a)
        self.access_token_b, _ = issue_token_pair(self.user_b)

    def _auth_headers_a(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.access_token_a}'}

    def _auth_headers_b(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.access_token_b}'}


class SubscriptionIsolationTest(TenantIsolationTestBase):
    """订阅隔离测试"""

    def test_tenant_a_cannot_query_tenant_b_subscription(self):
        """租户 A 无法查询租户 B 的订阅"""
        resp = self.client.get(
            f'/api/subscriptions/{self.subscription_b.id}/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)

    def test_tenant_a_cannot_list_tenant_b_subscriptions(self):
        """租户 A 无法列出租户 B 的订阅列表"""
        resp = self.client.get(
            '/api/subscriptions/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 200)
        # 应该只包含租户 A 的订阅
        subscription_ids = [s['id'] for s in resp.data]
        self.assertNotIn(self.subscription_b.id, subscription_ids)


class PaymentIsolationTest(TenantIsolationTestBase):
    """支付隔离测试"""

    def test_tenant_a_cannot_query_tenant_b_payment(self):
        """租户 A 无法查询租户 B 的支付交易"""
        resp = self.client.get(
            f'/api/payments/{self.payment_b.id}/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)

    def test_tenant_a_cannot_list_tenant_b_payments(self):
        """租户 A 无法列出租户 B 的支付列表"""
        resp = self.client.get(
            '/api/payments/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 200)
        payment_ids = [p['id'] for p in resp.data]
        self.assertNotIn(self.payment_b.id, payment_ids)


class RefundIsolationTest(TenantIsolationTestBase):
    """退款隔离测试"""

    def test_tenant_a_cannot_query_tenant_b_refund(self):
        """租户 A 无法查询租户 B 的退款记录"""
        resp = self.client.get(
            f'/api/payments/refunds/{self.refund_b.id}/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)

    def test_tenant_a_cannot_list_tenant_b_refunds(self):
        """租户 A 无法列出租户 B 的退款列表"""
        resp = self.client.get(
            '/api/payments/refunds/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 200)
        refund_ids = [r['id'] for r in resp.data]
        self.assertNotIn(self.refund_b.id, refund_ids)


class InvoiceIsolationTest(TenantIsolationTestBase):
    """发票隔离测试"""

    def test_tenant_a_cannot_query_tenant_b_invoice(self):
        """租户 A 无法查询租户 B 的发票"""
        resp = self.client.get(
            f'/api/invoices/{self.invoice_b.id}/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)

    def test_tenant_a_cannot_list_tenant_b_invoices(self):
        """租户 A 无法列出租户 B 的发票列表"""
        resp = self.client.get(
            '/api/invoices/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 200)
        invoice_ids = [i['id'] for i in resp.data]
        self.assertNotIn(self.invoice_b.id, invoice_ids)


class TeamIsolationTest(TenantIsolationTestBase):
    """团队隔离测试"""

    def test_tenant_a_cannot_list_tenant_b_members(self):
        """租户 A 无法列出租户 B 的成员列表"""
        resp = self.client.get(
            f'/api/tenants/{self.tenant_b.id}/members/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)

    def test_tenant_a_cannot_invite_to_tenant_b(self):
        """租户 A 无法向租户 B 发送邀请"""
        resp = self.client.post(
            f'/api/tenants/{self.tenant_b.id}/invite/',
            {
                'email': 'hacker@evil.com',
                'role': 'admin'
            },
            format='json',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)


class InvitationIsolationTest(TenantIsolationTestBase):
    """邀请隔离测试"""

    def test_tenant_a_cannot_accept_tenant_b_invitation(self):
        """租户 A 无法接受租户 B 的邀请"""
        resp = self.client.post(
            '/api/teams/invitations/accept/',
            {
                'code': self.invitation_b.code
            },
            format='json',
            **self._auth_headers_a()
        )

        # 邀请不属于租户 A，所以应该失败（返回 403 表示认证成功但无权限）
        self.assertIn(resp.status_code, [400, 403, 404])

    def test_tenant_a_cannot_query_tenant_b_invitation(self):
        """租户 A 无法查询租户 B 的邀请详情"""
        resp = self.client.get(
            f'/api/teams/invitations/{self.invitation_b.id}/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)


class TenantAccessTest(TenantIsolationTestBase):
    """租户访问权限测试"""

    def test_tenant_a_cannot_access_tenant_b_detail(self):
        """租户 A 无法访问租户 B 的详情"""
        resp = self.client.get(
            f'/api/tenants/{self.tenant_b.id}/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)

    def test_tenant_a_cannot_update_tenant_b(self):
        """租户 A 无法更新租户 B"""
        resp = self.client.patch(
            f'/api/tenants/{self.tenant_b.id}/',
            {
                'name': 'Hacked Company Name'
            },
            format='json',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)

    def test_tenant_a_cannot_delete_tenant_b(self):
        """租户 A 无法删除租户 B"""
        resp = self.client.delete(
            f'/api/tenants/{self.tenant_b.id}/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 404)

    def test_owner_can_access_own_tenant(self):
        """owner 可以访问自己的租户"""
        resp = self.client.get(
            f'/api/tenants/{self.tenant_a.id}/',
            **self._auth_headers_a()
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['name'], 'Tenant A Company')
