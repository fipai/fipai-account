"""
SMS 生产配置验证测试

验证:
1. 配置完整性（必填字段存在）
2. Mock 模式不发起真实请求
3. 生产模式正确判断
"""
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from accounts.sms import AliyunSMS, get_sms_client


class SMSProductionConfigTest(TestCase):
    """SMS 生产配置测试"""

    def test_mock_mode_no_real_request(self):
        """Mock 模式不发起真实请求"""
        config = {
            'access_key_id': 'test_key',
            'access_key_secret': 'test_secret',
            'sign_name': 'FIPAI',
            'template_register': 'SMS_TEST',
            'template_login': 'SMS_TEST',
            'sandbox': True,
        }
        sms = AliyunSMS(config)

        with patch('accounts.sms.AliyunSMS._get_client') as mock_get_client:
            mock_get_client.return_value = MagicMock()
            result = sms.send_code('13800000000', 'register', '123456')

            # Mock 模式应该返回成功
            self.assertEqual(result['code'], 0)
            # 不应该调用真实 client
            mock_get_client.assert_not_called()

    def test_sandbox_mode_detected(self):
        """sandbox=True 时使用 Mock 模式"""
        config = {
            'access_key_id': 'test_key',
            'access_key_secret': 'test_secret',
            'sign_name': 'FIPAI',
            'template_register': 'SMS_TEST',
            'template_login': 'SMS_TEST',
            'sandbox': True,
        }
        sms = AliyunSMS(config)

        with patch('accounts.sms.logger') as mock_logger:
            result = sms.send_code('13800000000', 'register', '123456')
            self.assertEqual(result['code'], 0)
            # 应该记录日志
            mock_logger.info.assert_called()

    def test_production_mode_without_credentials(self):
        """生产模式但无凭证时使用 Mock"""
        config = {
            'access_key_id': '',
            'access_key_secret': '',
            'sign_name': 'FIPAI',
            'template_register': '',
            'template_login': '',
            'sandbox': False,
        }
        sms = AliyunSMS(config)
        result = sms.send_code('13800000000', 'register', '123456')

        # 无凭证时降级为 Mock
        self.assertEqual(result['code'], 0)

    def test_get_sms_client_from_settings(self):
        """验证 get_sms_client 从 Django settings 读取配置"""
        with self.settings(
            ALIYUN_SMS_ACCESS_KEY_ID='test_key',
            ALIYUN_SMS_ACCESS_KEY_SECRET='test_secret',
            ALIYUN_SMS_SIGN_NAME='FIPAI',
            ALIYUN_SMS_TEMPLATE_CODE_register='SMS_REGISTER',
            ALIYUN_SMS_TEMPLATE_CODE_login='SMS_LOGIN',
            ALIYUN_SMS_SANDBOX=True,
        ):
            # 清除全局单例
            import accounts.sms
            accounts.sms._sms_client = None

            client = get_sms_client()

            self.assertIsNotNone(client)
            self.assertEqual(client.access_key_id, 'test_key')
            self.assertEqual(client.sandbox, True)


class SMSCodeGenerationTest(TestCase):
    """验证码生成测试"""

    def test_code_length(self):
        """验证码为6位数字"""
        from accounts.sms import generate_code
        code = generate_code()
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())

    def test_code_randomness(self):
        """验证码具有随机性"""
        from accounts.sms import generate_code
        codes = [generate_code() for _ in range(100)]
        # 至少有一些不同的验证码
        unique_codes = set(codes)
        self.assertGreater(len(unique_codes), 90)
