"""
Two-Factor Authentication Tests
"""
import pyotp
from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch, MagicMock
from accounts.models import TwoFactorAuth
import accounts.totp_service as totp_service

User = get_user_model()


class TwoFactorAuthServiceTests(TestCase):
    """2FA 服务测试"""

    def test_generate_totp_secret(self):
        """测试 TOTP secret 生成"""
        secret = totp_service.generate_totp_secret()
        self.assertEqual(len(secret), 32)
        # 验证是有效的 base32
        self.assertTrue(all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567' for c in secret))

    def test_generate_backup_codes(self):
        """测试备份码生成"""
        codes = totp_service.generate_backup_codes()
        self.assertEqual(len(codes), 10)
        self.assertTrue(all(len(c) == 8 for c in codes))

    def test_verify_totp_valid(self):
        """测试有效的 TOTP 验证"""
        secret = totp_service.generate_totp_secret()
        totp = pyotp.TOTP(secret)
        code = totp.now()

        self.assertTrue(totp_service.verify_totp(secret, code))

    def test_verify_totp_invalid(self):
        """测试无效的 TOTP 验证"""
        secret = totp_service.generate_totp_secret()
        self.assertFalse(totp_service.verify_totp(secret, '000000'))

    def test_verify_backup_code(self):
        """测试备份码验证"""
        code = 'ABCD1234'
        hashed = totp_service.hash_backup_code(code)

        is_valid, index = totp_service.verify_backup_code([hashed], code)
        self.assertTrue(is_valid)
        self.assertEqual(index, 0)

    def test_verify_backup_code_invalid(self):
        """测试无效备份码"""
        code = 'ABCD1234'
        hashed = totp_service.hash_backup_code(code)

        is_valid, index = totp_service.verify_backup_code([hashed], 'WRONG999')
        self.assertFalse(is_valid)
        self.assertIsNone(index)

    def test_remove_used_backup_code(self):
        """测试移除已用备份码"""
        codes = ['code1', 'code2', 'code3']
        new_codes = totp_service.remove_used_backup_code(codes, 1)
        self.assertEqual(new_codes, ['code1', 'code3'])

    def test_get_totp_provisioning_uri(self):
        """测试 TOTP provisioning URI 生成"""
        secret = totp_service.generate_totp_secret()
        uri = totp_service.get_totp_provisioning_uri(secret, 'testuser')
        self.assertIn('otpauth://totp/', uri)
        self.assertIn('testuser', uri)


class TwoFactorAuthAPITests(TestCase):
    """2FA API 测试"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='13800000000',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

    def tearDown(self):
        TwoFactorAuth.objects.filter(user=self.user).delete()

    def test_2fa_setup_not_authenticated(self):
        """测试未认证用户无法设置 2FA"""
        self.client.force_authenticate(user=None)
        response = self.client.post('/api/auth/2fa/setup/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_2fa_setup_success(self):
        """测试 2FA 设置成功"""
        response = self.client.post('/api/auth/2fa/setup/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        data = response.json()
        self.assertIn('secret', data)
        self.assertIn('provisioning_uri', data)
        self.assertIn('backup_codes', data)
        self.assertEqual(len(data['backup_codes']), 10)

    def test_2fa_setup_already_enabled(self):
        """测试已启用 2FA 无法重新设置"""
        # 首次设置
        response = self.client.post('/api/auth/2fa/setup/')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 再次设置应该失败
        response = self.client.post('/api/auth/2fa/setup/')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_2fa_status_disabled(self):
        """测试 2FA 未启用状态"""
        response = self.client.get('/api/auth/2fa/status/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        data = response.json()
        self.assertFalse(data['enabled'])
        self.assertEqual(data['backup_codes_remaining'], 0)

    def test_2fa_verify_enable_success(self):
        """测试启用 2FA 验证成功"""
        # 设置 2FA
        setup_response = self.client.post('/api/auth/2fa/setup/')
        secret = setup_response.json()['secret']

        # 验证 TOTP 代码
        totp = pyotp.TOTP(secret)
        code = totp.now()

        verify_response = self.client.post('/api/auth/2fa/verify/', {
            'code': code
        })
        self.assertEqual(verify_response.status_code, status.HTTP_200_OK)
        self.assertTrue(verify_response.json()['ok'])

        # 验证状态已启用
        status_response = self.client.get('/api/auth/2fa/status/')
        self.assertTrue(status_response.json()['enabled'])

    def test_2fa_verify_invalid_code(self):
        """测试无效验证码"""
        # 设置 2FA
        self.client.post('/api/auth/2fa/setup/')

        # 使用错误验证码
        response = self.client.post('/api/auth/2fa/verify/', {
            'code': '000000'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_2fa_disable_success(self):
        """测试禁用 2FA 成功"""
        # 设置并启用 2FA
        setup_response = self.client.post('/api/auth/2fa/setup/')
        secret = setup_response.json()['secret']
        totp = pyotp.TOTP(secret)
        self.client.post('/api/auth/2fa/verify/', {'code': totp.now()})

        # 禁用 2FA
        disable_response = self.client.post('/api/auth/2fa/disable/', {
            'password': 'testpass123'
        })
        self.assertEqual(disable_response.status_code, status.HTTP_200_OK)
        self.assertTrue(disable_response.json()['ok'])

        # 验证状态已禁用
        status_response = self.client.get('/api/auth/2fa/status/')
        self.assertFalse(status_response.json()['enabled'])

    def test_2fa_disable_wrong_password(self):
        """测试禁用 2FA 密码错误"""
        # 设置并启用 2FA
        setup_response = self.client.post('/api/auth/2fa/setup/')
        secret = setup_response.json()['secret']
        totp = pyotp.TOTP(secret)
        self.client.post('/api/auth/2fa/verify/', {'code': totp.now()})

        # 使用错误密码禁用
        response = self.client.post('/api/auth/2fa/disable/', {
            'password': 'wrongpassword'
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_2fa_login_verification(self):
        """测试登录时 2FA challenge 验证并签发 token"""
        setup_response = self.client.post('/api/auth/2fa/setup/')
        secret = setup_response.json()['secret']
        totp = pyotp.TOTP(secret)
        self.client.post('/api/auth/2fa/verify/', {'code': totp.now()})

        self.client.force_authenticate(user=None)
        login_response = self.client.post('/api/auth/login/', {
            'username': self.user.username,
            'password': 'testpass123',
        })
        self.assertEqual(login_response.status_code, status.HTTP_202_ACCEPTED)
        self.assertNotIn('access', login_response.json())

        response = self.client.post('/api/auth/2fa/verify/', {
            'challenge': login_response.json()['challenge'],
            'code': totp.now(),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['verified'])
        self.assertIn('access', response.json())
        self.assertIn('refresh', response.json())

    def test_2fa_backup_code_verification(self):
        """测试challenge备用码验证并消费备用码"""
        setup_response = self.client.post('/api/auth/2fa/setup/')
        backup_codes = setup_response.json()['backup_codes']
        secret = setup_response.json()['secret']
        totp = pyotp.TOTP(secret)
        self.client.post('/api/auth/2fa/verify/', {'code': totp.now()})

        self.client.force_authenticate(user=None)
        login_response = self.client.post('/api/auth/login/', {
            'username': self.user.username,
            'password': 'testpass123',
        })
        response = self.client.post('/api/auth/2fa/verify/', {
            'challenge': login_response.json()['challenge'],
            'code': backup_codes[0],
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.json()['verified'])
        self.assertTrue(response.json()['used_backup'])

        self.client.force_authenticate(user=self.user)
        status_response = self.client.get('/api/auth/2fa/status/')
        self.assertEqual(status_response.json()['backup_codes_remaining'], 9)
