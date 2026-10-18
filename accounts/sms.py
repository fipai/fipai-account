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
        """获取阿里云 SMS 客户端(Tea SDK)"""
        try:
            from alibabacloud_dysmsapi20170525.client import Client as DysmsapiClient
            from alibabacloud_tea_openapi import models as open_api_models

            config = open_api_models.Config(
                access_key_id=self.access_key_id,
                access_key_secret=self.access_key_secret,
                region_id='cn-hangzhou',
                endpoint='dysmsapi.aliyuncs.com',
            )
            return DysmsapiClient(config)
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
            from alibabacloud_dysmsapi20170525 import models as dysmsapi_models

            client = self._get_client()
            if not client:
                return {'code': 0, 'message': 'success'}

            req = dysmsapi_models.SendSmsRequest(
                phone_numbers=phone,
                sign_name=self.sign_name,
                template_code=template_code,
                template_param=f'{{"code":"{code}"}}',
            )
            resp = client.send_sms(req)
            status_code = getattr(resp.body, 'code', None)
            if status_code and status_code != 'OK':
                logger.error(f"SMS send failed: body={resp.body}")
                return {'code': 1, 'message': f"alicloud: {status_code} {getattr(resp.body, 'message', '')}"}
            logger.info(f"SMS sent: req_id={getattr(resp.body, 'request_id', '')}, phone={phone[:3]}****")
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
