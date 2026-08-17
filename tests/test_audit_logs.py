"""
Audit Logs Tests
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from audit.models import AuditLog
from tenants.models import Tenant
from teams.models import TeamMember

User = get_user_model()


class AuditLogModelTests(TestCase):
    """审计日志模型测试"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='13800000000',
            password='testpass123'
        )
        self.tenant = Tenant.objects.create(
            name='Test Tenant',
            slug='test-tenant'
        )

    def test_create_audit_log(self):
        """测试创建审计日志"""
        log = AuditLog.log(
            action='login',
            user=self.user,
            tenant=self.tenant,
            details={'ip': '127.0.0.1'},
            request=None
        )

        self.assertEqual(log.action, 'login')
        self.assertEqual(log.user, self.user)
        self.assertEqual(log.tenant, self.tenant)
        self.assertEqual(log.details, {'ip': '127.0.0.1'})

    def test_audit_log_str(self):
        """测试审计日志字符串表示"""
        log = AuditLog.log(action='login', user=self.user)
        self.assertIn('login', str(log))
        self.assertIn(self.user.username, str(log))


class MockRequest:
    """模拟 HTTP 请求对象"""

    def __init__(self, ip='127.0.0.1', user_agent='Test Agent'):
        self.META = {
            'REMOTE_ADDR': ip,
            'HTTP_USER_AGENT': user_agent
        }


class AuditLogAPITests(TestCase):
    """审计日志 API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='13800000000',
            password='testpass123'
        )
        self.tenant = Tenant.objects.create(
            name='Test Tenant',
            slug='test-tenant'
        )
        TeamMember.objects.create(
            user=self.user,
            tenant=self.tenant,
            role='owner',
            status='active'
        )
        self.client.force_authenticate(user=self.user)

        # 创建一些审计日志
        for i in range(5):
            AuditLog.objects.create(
                user=self.user,
                tenant=self.tenant,
                action='login',
                details={'attempt': i}
            )

    def test_list_audit_logs(self):
        """测试列出审计日志"""
        response = self.client.get('/api/audit/logs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertIn('results', data)
        self.assertIn('total', data)
        self.assertEqual(data['total'], 5)

    def test_list_audit_logs_pagination(self):
        """测试审计日志分页"""
        response = self.client.get('/api/audit/logs/?page=1&page_size=2')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(len(data['results']), 2)
        self.assertEqual(data['total'], 5)
        self.assertEqual(data['page'], 1)
        self.assertEqual(data['page_size'], 2)

    def test_list_audit_logs_filter_by_action(self):
        """测试按操作类型过滤"""
        # 创建一个不同类型的日志
        AuditLog.objects.create(
            user=self.user,
            tenant=self.tenant,
            action='logout'
        )

        response = self.client.get('/api/audit/logs/?action=logout')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['results'][0]['action'], 'logout')

    def test_list_audit_logs_filter_by_user(self):
        """测试按用户过滤"""
        other_user = User.objects.create_user(
            username='13900000000',
            password='testpass123'
        )
        AuditLog.objects.create(
            user=other_user,
            tenant=self.tenant,
            action='login'
        )

        response = self.client.get(f'/api/audit/logs/?user_id={other_user.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['results'][0]['user'], other_user.id)

    def test_get_audit_log_detail(self):
        """测试获取审计日志详情"""
        log = AuditLog.objects.create(
            user=self.user,
            tenant=self.tenant,
            action='login',
            details={'ip': '127.0.0.1'}
        )

        response = self.client.get(f'/api/audit/logs/{log.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertEqual(data['action'], 'login')
        self.assertEqual(data['username'], self.user.username)


class AuditLogTenantIsolationTests(TestCase):
    """审计日志租户隔离测试"""

    def setUp(self):
        self.client = APIClient()
        self.user1 = User.objects.create_user(
            username='13800000000',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='13900000000',
            password='testpass123'
        )
        self.tenant1 = Tenant.objects.create(
            name='Tenant 1',
            slug='tenant-1'
        )
        self.tenant2 = Tenant.objects.create(
            name='Tenant 2',
            slug='tenant-2'
        )
        TeamMember.objects.create(
            user=self.user1,
            tenant=self.tenant1,
            role='owner',
            status='active'
        )
        TeamMember.objects.create(
            user=self.user2,
            tenant=self.tenant2,
            role='owner',
            status='active'
        )

        # User1 的日志
        AuditLog.objects.create(
            user=self.user1,
            tenant=self.tenant1,
            action='login'
        )
        # User2 的日志
        AuditLog.objects.create(
            user=self.user2,
            tenant=self.tenant2,
            action='logout'
        )

    def test_user_can_only_see_own_tenant_logs(self):
        """测试用户只能看到自己租户的日志"""
        self.client.force_authenticate(user=self.user1)

        response = self.client.get('/api/audit/logs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        # 只应该看到 tenant1 的日志
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['results'][0]['tenant'], self.tenant1.id)

    def test_user_cannot_see_other_tenant_logs(self):
        """测试用户看不到其他租户的日志"""
        self.client.force_authenticate(user=self.user1)

        # 直接列出所有日志，应该只有 tenant1 的
        response = self.client.get('/api/audit/logs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        # user1 只能看到自己的日志（在 tenant1 中）
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['results'][0]['tenant'], self.tenant1.id)
        self.assertEqual(data['results'][0]['user'], self.user1.id)

        # 尝试显式查询 tenant2 的日志，因为 user1 不属于 tenant2，应该无结果
        # （这里查询的是租户隔离的日志，不是用户自己的日志）
        response = self.client.get(f'/api/audit/logs/?tenant_id={self.tenant2.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        # user1 的个人日志不属于 tenant2，所以 total=0
        self.assertEqual(data['total'], 0)
