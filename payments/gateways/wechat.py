"""
WeChat Pay Gateway Implementation
"""
import logging
from decimal import Decimal
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from wechatpayv3 import WeChatPay, WeChatPayType
    WECHAT_SDK_AVAILABLE = True
except ImportError:
    WeChatPay = None
    WeChatPayType = None
    WECHAT_SDK_AVAILABLE = False


class WechatGateway:
    """微信支付网关"""

    def __init__(self, config: dict):
        self.config = config
        self.mchid = config.get('mchid', '')
        self.serial_no = config.get('serial_no', '')
        self.private_key = config.get('private_key', '')
        self.apiv3_key = config.get('apiv3_key', '')
        self.appid = config.get('appid', '')
        self.sandbox = config.get('sandbox') is True
        self.mock_enabled = bool(settings.DEBUG and self.sandbox)
        self.wxpay = None

        credentials_complete = all([
            self.mchid,
            self.serial_no,
            self.private_key,
            self.apiv3_key,
            self.appid,
        ])
        if WECHAT_SDK_AVAILABLE and credentials_complete:
            try:
                self.wxpay = WeChatPay(
                    wechatpay_type=WeChatPayType.NATIVE,
                    mchid=self.mchid,
                    private_key=self.private_key,
                    cert_serial_no=self.serial_no,
                    apiv3_key=self.apiv3_key,
                    appid=self.appid,
                    debug=self.sandbox,
                )
            except Exception:
                logger.error(
                    "payment_gateway_initialization_failed",
                    extra={'gateway': 'wechat', 'error_code': 'sdk_init_exception'},
                )
        elif not self.mock_enabled:
            logger.error(
                "payment_gateway_initialization_failed",
                extra={'gateway': 'wechat', 'error_code': 'sdk_or_credentials_missing'},
            )

    def create_order(
        self,
        out_trade_no: str,
        amount: Decimal,
        subject: str,
        notify_url: str,
        return_url: Optional[str] = None,
    ) -> dict:
        """创建微信支付订单"""
        if not self.wxpay and self.mock_enabled:
            return {
                'code': 0,
                'message': 'success',
                'data': {
                    'trade_no': f'WX_{out_trade_no}',
                    'pay_url': None,
                    'qr_code': f'weixin://wxpay/bizpayurl?pr={out_trade_no}',
                    'code_url': f'weixin://wxpay/bizpayurl?pr={out_trade_no}',
                    'mock': True,
                },
            }

        try:
            code, response = self.wxpay.pay(
                description=subject,
                out_trade_no=out_trade_no,
                amount={'total': int(amount * 100), 'currency': 'CNY'},
                notify_url=notify_url,
            )
            if code == 0:
                return {
                    'code': 0,
                    'message': 'success',
                    'data': {
                        'trade_no': response.get('transaction_id', out_trade_no),
                        'pay_url': None,
                        'qr_code': response.get('code_url'),
                        'code_url': response.get('code_url'),
                    },
                }
            return {'code': code, 'message': str(response), 'data': None}
        except Exception as exc:
            logger.error("WeChat create_order failed: %s", exc)
            return {'code': 1, 'message': str(exc), 'data': None}

    def query_order(self, out_trade_no: str) -> dict:
        """查询订单并从微信响应规范化订单号、金额和币种。"""
        if not self.wxpay and self.mock_enabled:
            return {'code': 0, 'message': 'success', 'data': {'status': 'pending'}}

        try:
            code, response = self.wxpay.query(out_trade_no=out_trade_no)
            if code == 0:
                status_map = {
                    'SUCCESS': 'paid',
                    'REFUND': 'refunded',
                    'NOTPAY': 'pending',
                    'CLOSED': 'closed',
                    'PAYERROR': 'closed',
                }
                response_amount = response.get('amount')
                response_amount = response_amount if isinstance(response_amount, dict) else {}
                total = response_amount.get('total')
                return {
                    'code': 0,
                    'message': 'success',
                    'data': {
                        'status': status_map.get(response.get('trade_state'), 'pending'),
                        'out_trade_no': response.get('out_trade_no'),
                        'trade_no': response.get('transaction_id'),
                        'amount': Decimal(total) / 100 if total is not None else None,
                        'currency': response_amount.get('currency'),
                    },
                }
            return {'code': code, 'message': 'query failed', 'data': None}
        except Exception:
            logger.error(
                "payment_query_failed",
                extra={'gateway': 'wechat', 'error_code': 'sdk_query_exception'},
            )
            return {'code': 1, 'message': 'query failed', 'data': None}

    def refund(self, out_trade_no: str, amount: Decimal, reason: str = None) -> dict:
        """退款"""
        if not self.wxpay and self.mock_enabled:
            return {'code': 0, 'message': 'success', 'data': {'refund_amount': str(amount)}}

        try:
            code, response = self.wxpay.refund(
                out_trade_no=out_trade_no,
                amount={
                    'refund': int(amount * 100),
                    'total': int(amount * 100),
                    'currency': 'CNY',
                },
                reason=reason or '用户退款',
            )
            if code == 0:
                return {
                    'code': 0,
                    'message': 'success',
                    'data': {
                        'refund_id': response.get('refund_id'),
                        'refund_amount': Decimal(response.get('refund_amount', 0)) / 100,
                    },
                }
            return {'code': code, 'message': str(response), 'data': None}
        except Exception as exc:
            logger.error("WeChat refund failed: %s", exc)
            return {'code': 1, 'message': str(exc), 'data': None}

    def parse_callback(self, data: dict, headers=None, raw_body: bytes = b'') -> Optional[dict]:
        """由 SDK 一次完成平台验签和 resource 解密，仅返回可信 resource。"""
        if not self.wxpay:
            return dict(data) if self.mock_enabled else None
        if not headers or not raw_body:
            return None

        try:
            notification = self.wxpay.callback(headers, raw_body)
        except Exception:
            logger.warning(
                "payment_callback_rejected",
                extra={'gateway': 'wechat', 'error_code': 'sdk_callback_exception'},
            )
            return None

        if not isinstance(notification, dict):
            return None
        resource = notification.get('resource')
        if not isinstance(resource, dict):
            return None
        amount = resource.get('amount')
        if not isinstance(amount, dict):
            return None
        if resource.get('mchid') != self.mchid:
            return None
        if resource.get('appid') != self.appid:
            return None
        if amount.get('currency') != 'CNY':
            return None
        return resource

    def verify_callback(self, data: dict, headers=None, raw_body: bytes = b'') -> bool:
        """兼容布尔验签接口；callback 仅调用一次。"""
        return self.parse_callback(data, headers, raw_body) is not None

    def get_trade_status(self, data: dict) -> tuple:
        """从 SDK 已解密并校验的 resource 获取交易状态"""
        status_map = {
            'SUCCESS': 'paid',
            'REFUND': 'refunded',
            'NOTPAY': 'pending',
            'CLOSED': 'closed',
        }
        return (
            data.get('out_trade_no', ''),
            status_map.get(data.get('trade_state', ''), 'pending'),
            Decimal(data.get('amount', {}).get('total', 0)) / 100,
        )
