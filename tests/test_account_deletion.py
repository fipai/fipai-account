"""
Account Deletion Tests
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import AccountDeletionRequest, TwoFactorAuth

User = get_user_model()


class AccountDeletionAPITests(TestCase):
    """账户注销 API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='13800000000',
            password='testpass123',
            email='test@example.com'
        )
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        AccountDeletionRequest.objects.filter(user=self.user).delete()
        TwoFactorAuth.objects.filter(user=self.user).delete()

    def test_request_deletion_success(self):
        """测试提交注销申请成功"""
        response = self.client.post('/api/account/request-deletion/', {
            'reason': '不再需要服务'
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data = response.json()
        self.assertTrue(data['ok'])
        self.assertIn('request_id', data)
        self.assertEqual(data['status'], 'pending')

    def test_request_deletion_duplicate(self):
        """测试重复提交注销申请被拒绝"""
        # 首次提交
        self.client.post('/api/account/request-deletion/', {
            'reason': '不再需要服务'
        })

        # 重复提交
        response = self.client.post('/api/account/request-deletion/', {
            'reason': '真的不需要了'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('已有待处理', response.json()['error'])

    def test_deletion_status_no_request(self):
        """测试无注销申请时状态查询"""
        response = self.client.get('/api/account/deletion-status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertFalse(data['has_request'])

    def test_deletion_status_with_request(self):
        """测试有注销申请时状态查询"""
        # 创建注销申请
        self.client.post('/api/account/request-deletion/', {
            'reason': '测试原因'
        })

        response = self.client.get('/api/account/deletion-status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertTrue(data['has_request'])
        self.assertEqual(data['status'], 'pending')
        self.assertEqual(data['reason'], '测试原因')

    def test_delete_confirm_success(self):
        """测试确认注销成功"""
        response = self.client.delete('/api/account/', {
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['ok'])

        # 验证用户数据已匿名化
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.username.startswith('deleted_user_'))
        self.assertTrue(self.user.email.startswith('deleted_'))

        # 验证注销申请状态
        deletion = AccountDeletionRequest.objects.filter(user=self.user).first()
        self.assertEqual(deletion.status, 'completed')
        self.assertTrue(deletion.data_anonymized)

    def test_delete_confirm_wrong_password(self):
        """测试确认注销密码错误"""
        response = self.client.delete('/api/account/', {
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('密码错误', response.json()['error'])

    def test_delete_confirm_no_password(self):
        """测试确认注销未提供密码"""
        response = self.client.delete('/api/account/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_delete_confirm_2fa_disabled(self):
        """测试确认注销时 2FA 被禁用"""
        # 先启用 2FA
        TwoFactorAuth.objects.create(
            user=self.user,
            enabled=True,
            secret='TESTSECRET123',
            backup_codes=[]
        )

        # 确认注销
        response = self.client.delete('/api/account/', {
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 验证 2FA 已被删除
        self.assertFalse(TwoFactorAuth.objects.filter(user=self.user).exists())


class AccountDeletionDataAnonymizationTests(TestCase):
    """账户注销数据匿名化测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='13800000000',
            password='testpass123',
            email='original@example.com',
            first_name='Original',
            last_name='Name'
        )

    def test_user_data_anonymized(self):
        """测试用户数据被正确匿名化"""
        self.client.force_authenticate(user=self.user)

        response = self.client.delete('/api/account/', {
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 重新获取用户（从数据库）
        self.user.refresh_from_db()

        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.username.startswith('deleted_user_'))
        self.assertTrue(self.user.email.startswith('deleted_'))
        self.assertEqual(self.user.first_name, '')
        self.assertEqual(self.user.last_name, '')

    def test_anonymization_preserves_audit_data(self):
        """测试匿名化保留审计数据（租户和订阅记录）"""
        self.client.force_authenticate(user=self.user)

        # 确认注销
        response = self.client.delete('/api/account/', {
            'password': 'testpass123'
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # 验证用户对象仍然存在于数据库（只是被匿名化）
        user_exists = User.objects.filter(id=self.user.id).exists()
        self.assertTrue(user_exists)

        # 验证注销申请记录
        deletion = AccountDeletionRequest.objects.get(user_id=self.user.id)
        self.assertTrue(deletion.data_anonymized)
        self.assertIsNotNone(deletion.anonymized_at)
