"""
发票 API 测试

验证:
1. 发票申请成功创建
2. 必填字段校验
3. 发票列表查询
4. 发票状态查询
"""
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from invoices.models import InvoiceRequest
from subscriptions.models import Subscription, SubscriptionPlan
from tenants.models import Tenant
from teams.models import TeamMember


class InvoiceAPITestBase(TestCase):
    """Base class for invoice API tests"""

    def setUp(self):
        self.client = APIClient()
        self.client.raise_request_exception = False
        self.user_model = get_user_model()

        # 创建测试用户
        self.user = self.user_model.objects.create_user(
            username='test_user_invoice',
            email='invoice@test.com',
            password='testpass123'
        )

        self.other_user = self.user_model.objects.create_user(
            username='other_user_invoice',
            email='other_invoice@test.com',
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

        # 创建订阅
        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            status='active',
        )

        # 创建租户并设置用户为 owner
        self.tenant = Tenant.objects.create(
            name='Test Invoice Tenant',
            slug='test-invoice-tenant',
        )
        TeamMember.objects.create(
            tenant=self.tenant,
            user=self.user,
            role='owner',
            status='active'
        )

        # 生成 JWT token
        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)

    def _auth_headers(self):
        return {'HTTP_AUTHORIZATION': f'Bearer {self.access_token}'}


class InvoiceRequestCreateTest(InvoiceAPITestBase):
    """发票申请创建测试"""

    def test_create_invoice_success(self):
        """发票申请成功创建"""
        resp = self.client.post(
            '/api/invoices/',
            {
                'invoice_type': 'normal',
                'title': '北京某某科技有限公司',
                'tax_id': '91110000XXXXXXXX',
                'amount': '99.00',
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['status'], 'pending')
        self.assertEqual(resp.data['title'], '北京某某科技有限公司')

    def test_create_invoice_vat_type(self):
        """增值税专用发票申请"""
        resp = self.client.post(
            '/api/invoices/',
            {
                'invoice_type': 'vat',
                'title': '上海某某企业有限公司',
                'tax_id': '91310000XXXXXXXX',
                'amount': '299.00',
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data['invoice_type'], 'vat')

    def test_create_invoice_unauthenticated(self):
        """未认证用户不能申请发票"""
        resp = self.client.post(
            '/api/invoices/',
            {
                'invoice_type': 'normal',
                'title': '测试公司',
                'amount': '99.00',
            },
            format='json'
        )

        self.assertEqual(resp.status_code, 401)

    def test_create_invoice_missing_title(self):
        """发票抬头为必填字段"""
        resp = self.client.post(
            '/api/invoices/',
            {
                'invoice_type': 'normal',
                'amount': '99.00',
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 400)

    def test_create_invoice_title_too_short(self):
        """发票抬头太短会被拒绝"""
        resp = self.client.post(
            '/api/invoices/',
            {
                'invoice_type': 'normal',
                'title': 'a',  # 少于2个字符
                'amount': '99.00',
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 400)

    def test_create_invoice_amount_zero(self):
        """发票金额为零会被拒绝"""
        resp = self.client.post(
            '/api/invoices/',
            {
                'invoice_type': 'normal',
                'title': '测试公司名称',
                'amount': '0',
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 400)

    def test_create_invoice_without_subscription(self):
        """不关联订阅也可以申请发票"""
        resp = self.client.post(
            '/api/invoices/',
            {
                'invoice_type': 'normal',
                'title': '无订阅测试公司',
                'amount': '50.00',
            },
            format='json',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 201)


class InvoiceRequestQueryTest(InvoiceAPITestBase):
    """发票查询测试"""

    def test_list_invoices(self):
        """用户可以查询自己的发票列表"""
        InvoiceRequest.objects.create(
            user=self.user,
            tenant=self.tenant,
            invoice_type='normal',
            title='测试公司A',
            amount=Decimal('99.00'),
            status='pending'
        )

        resp = self.client.get(
            '/api/invoices/',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_query_invoice_status(self):
        """用户可以查询单个发票状态"""
        invoice = InvoiceRequest.objects.create(
            user=self.user,
            tenant=self.tenant,
            invoice_type='normal',
            title='状态查询测试公司',
            amount=Decimal('99.00'),
            status='pending'
        )

        resp = self.client.get(
            f'/api/invoices/{invoice.id}/status',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['status'], 'pending')
        self.assertEqual(resp.data['title'], '状态查询测试公司')

    def test_cannot_query_other_user_invoice(self):
        """用户不能查询其他用户的发票"""
        other_invoice = InvoiceRequest.objects.create(
            user=self.other_user,
            invoice_type='normal',
            title='其他用户公司',
            amount=Decimal('99.00'),
            status='pending'
        )

        resp = self.client.get(
            f'/api/invoices/{other_invoice.id}',
            **self._auth_headers()
        )

        self.assertEqual(resp.status_code, 404)


class InvoiceStateTransitionTest(TestCase):
    """发票状态机测试"""

    def setUp(self):
        self.user_model = get_user_model()
        self.user = self.user_model.objects.create_user(
            username='test_user_invoice_state',
            email='invoice_state@test.com',
            password='testpass123'
        )

        self.tenant = Tenant.objects.create(
            name='Invoice State Test Tenant',
            slug='invoice-state-tenant',
        )

        TeamMember.objects.create(
            tenant=self.tenant,
            user=self.user,
            role='owner',
            status='active'
        )

    def test_invoice_approve(self):
        """批准发票申请"""
        invoice = InvoiceRequest.objects.create(
            user=self.user,
            tenant=self.tenant,
            invoice_type='normal',
            title='审批测试公司',
            amount=Decimal('99.00'),
            status='pending'
        )

        invoice.approve(processed_by=self.user, note='发票已批准')

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'approved')
        self.assertEqual(invoice.process_note, '发票已批准')

    def test_invoice_reject(self):
        """拒绝发票申请"""
        invoice = InvoiceRequest.objects.create(
            user=self.user,
            tenant=self.tenant,
            invoice_type='normal',
            title='拒绝测试公司',
            amount=Decimal('99.00'),
            status='pending'
        )

        invoice.reject(processed_by=self.user, note='信息不完整')

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'rejected')

    def test_invoice_issue(self):
        """开具发票"""
        invoice = InvoiceRequest.objects.create(
            user=self.user,
            tenant=self.tenant,
            invoice_type='normal',
            title='开票测试公司',
            amount=Decimal('99.00'),
            status='approved'
        )

        invoice.issue(invoice_no='FP12345678')

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'issued')
        self.assertEqual(invoice.invoice_no, 'FP12345678')
