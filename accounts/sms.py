"""
阿里云 SMS 短信服务封装

配置项 (.env):
- ALIYUN_SMS_ACCESS_KEY_ID
- ALIYUN_SMS_ACCESS_KEY_SECRET
- ALIYUN_SMS_SIGN_NAME
- ALIYUN_SMS_TEMPLATE_CODE_register  (注册验证码模板)
- ALIYUN_SMS_TEMPLATE_CODE_login     (登录验证码模板)
"""
import random
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 验证码位数
SMS_CODE_LENGTH = 6
# 有效期（分钟）
SMS_CODE_EXPIRE_MINUTES = 5
# 每天最大发送次数
SMS_DAILY_LIMIT = 30


def generate_code() -> str:
    """生成 6 位数字验证码"""
    return ''.join(random.choices('0123456789', k=SMS_CODE_LENGTH))


class AliyunSMS:
    """阿里云短信服务"""

    def __init__(self, config: dict):
        self.access_key_id = config.get('access_key_id', '')
        self.access_key_secret = config.get('access_key_secret', '')
        self.sign_name = config.get('sign_name', 'FIPAI')
        self.template_register = config.get('template_register', '')
        self.template_login = config.get('template_login', '')
        self.sandbox = config.get('sandbox', True)

    def _get_client(self):
        """获取阿里云 SMS 客户端"""
        try:
            from aliyunsdkcore.client import AliyunClient
            from aliyunsdkcore.profile import region_provider
            region_provider.add_endpoint('dysmsapi', 'cn-hangzhou', 'dysmsapi.aliyuncs.com')
            client = AliyunClient(
                self.access_key_id,
                self.access_key_secret,
                'cn-hangzhou'
            )
            return client
        except ImportError:
            logger.warning("阿里云 SMS SDK 未安装，使用 Mock 模式")
            return None

    def send_code(self, phone: str, purpose: str, code: str) -> dict:
        """
        发送短信验证码
        purpose: 'register' | 'login'
        """
        template_code = (
            self.template_register if purpose == 'register'
            else self.template_login
        )

        # Mock 模式（无 SDK 或沙箱）
        if not self.access_key_id or not template_code or self.sandbox:
            # 仅记录手机号前3位+后4位，保护隐私
            masked_phone = f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else phone
            logger.info(f"[Mock SMS] phone={masked_phone}, purpose={purpose}")
            return {'code': 0, 'message': 'success'}

        try:
            from aliyunsdksms.request import SendSmsRequest

            request = SendSmsRequest.SendSmsRequest()
            request.set_PhoneNumbers(phone)
            request.set_SignName(self.sign_name)
            request.set_TemplateCode(template_code)
            request.set_TemplateParam(f'{{"code":"{code}"}}')

            client = self._get_client()
            if not client:
                return {'code': 0, 'message': 'success'}

            response = client.do_action(request)
            logger.info(f"SMS sent: {response}")
            return {'code': 0, 'message': 'success'}

        except Exception as e:
            logger.error(f"SMS send failed: {e}")
            return {'code': 1, 'message': str(e)}


# 全局单例
_sms_client: Optional[AliyunSMS] = None


def get_sms_client() -> AliyunSMS:
    global _sms_client
    if _sms_client is None:
        from django.conf import settings
        config = {
            'access_key_id': getattr(settings, 'ALIYUN_SMS_ACCESS_KEY_ID', ''),
            'access_key_secret': getattr(settings, 'ALIYUN_SMS_ACCESS_KEY_SECRET', ''),
            'sign_name': getattr(settings, 'ALIYUN_SMS_SIGN_NAME', 'FIPAI'),
            'template_register': getattr(settings, 'ALIYUN_SMS_TEMPLATE_CODE_register', ''),
            'template_login': getattr(settings, 'ALIYUN_SMS_TEMPLATE_CODE_login', ''),
            'sandbox': getattr(settings, 'ALIYUN_SMS_SANDBOX', True),
        }
        _sms_client = AliyunSMS(config)
    return _sms_client
