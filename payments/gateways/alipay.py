"""
Alipay Gateway Implementation
"""
import logging
from decimal import Decimal
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from alipay import AliPay
    ALIPAY_SDK_AVAILABLE = True
except ImportError:
    AliPay = None
    ALIPAY_SDK_AVAILABLE = False


class AlipayGateway:
    """支付宝支付网关"""

    def __init__(self, config: dict):
        self.config = config
        self.app_id = config.get('app_id', '')
        self.seller_id = config.get('seller_id', '')
        self.private_key = config.get('private_key', '')
        self.public_key = config.get('public_key', '')
        self.sandbox = config.get('sandbox') is True
        self.mock_enabled = bool(settings.DEBUG and self.sandbox)
        self.alipay = None

        credentials_complete = all([
            self.app_id,
            self.seller_id,
            self.private_key,
            self.public_key,
        ])
        if ALIPAY_SDK_AVAILABLE and credentials_complete:
            try:
                self.alipay = AliPay(
                    appid=self.app_id,
                    app_notify_url=None,
                    app_private_key_string=self.private_key,
                    alipay_public_key_string=self.public_key,
                    sign_type="RSA2",
                    debug=self.sandbox,
                )
            except Exception:
                logger.error(
                    "payment_gateway_initialization_failed",
                    extra={'gateway': 'alipay', 'error_code': 'sdk_init_exception'},
                )
        elif not self.mock_enabled:
            logger.error(
                "payment_gateway_initialization_failed",
                extra={'gateway': 'alipay', 'error_code': 'sdk_or_credentials_missing'},
            )

    def create_order(
        self,
        out_trade_no: str,
        amount: Decimal,
        subject: str,
        notify_url: str,
        return_url: Optional[str] = None,
    ) -> dict:
        """创建支付宝订单"""
        if not self.alipay and self.mock_enabled:
            return {
                'code': 0,
                'message': 'success',
                'data': {
                    'trade_no': f'ALipay_{out_trade_no}',
                    'pay_url': f'https://openapi-sandbox.dl.alipaydev.com/gateway.do?out_trade_no={out_trade_no}',
                    'qr_code': f'https://qr.alipay.com/{out_trade_no}',
                    'mock': True,
                },
            }

        try:
            pay_url = (
                "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
                if self.sandbox
                else "https://openapi.alipay.com/gateway.do"
            )
            order_string = self.alipay.api_alipay_trade_page_pay(
                out_trade_no=out_trade_no,
                total_amount=str(amount),
                subject=subject,
                return_url=return_url,
                notify_url=notify_url,
            )
            return {
                'code': 0,
                'message': 'success',
                'data': {
                    'trade_no': out_trade_no,
                    'pay_url': f"{pay_url}?{order_string}",
                    'qr_code': None,
                },
            }
        except Exception as exc:
            logger.error("Alipay create_order failed: %s", exc)
            return {'code': 1, 'message': str(exc), 'data': None}

    def query_order(self, out_trade_no: str) -> dict:
        """查询订单并返回统一、可核对的订单字段。"""
        if not self.alipay and self.mock_enabled:
            return {'code': 0, 'message': 'success', 'data': {'status': 'pending'}}

        try:
            result = self.alipay.api_alipay_trade_query(out_trade_no=out_trade_no)
            status_map = {
                'WAIT_BUYER_PAY': 'pending',
                'TRADE_CLOSED': 'closed',
                'TRADE_SUCCESS': 'paid',
                'TRADE_FINISHED': 'paid',
            }
            total_amount = result.get('total_amount')
            return {
                'code': 0,
                'message': 'success',
                'data': {
                    'status': status_map.get(result.get('trade_status'), 'pending'),
                    'out_trade_no': result.get('out_trade_no'),
                    'trade_no': result.get('trade_no'),
                    'amount': Decimal(total_amount) if total_amount is not None else None,
                    'currency': 'CNY',
                },
            }
        except Exception:
            logger.error(
                "payment_query_failed",
                extra={'gateway': 'alipay', 'error_code': 'sdk_query_exception'},
            )
            return {'code': 1, 'message': 'query failed', 'data': None}

    def refund(self, out_trade_no: str, amount: Decimal, reason: str = None) -> dict:
        """退款"""
        if not self.alipay and self.mock_enabled:
            return {'code': 0, 'message': 'success', 'data': {'refund_amount': str(amount)}}

        try:
            result = self.alipay.api_alipay_trade_refund(
                out_trade_no=out_trade_no,
                refund_amount=str(amount),
                refund_reason=reason or '用户退款',
            )
            return {
                'code': 0,
                'message': 'success',
                'data': {'refund_amount': result.get('refund_fee')},
            }
        except Exception as exc:
            logger.error("Alipay refund failed: %s", exc)
            return {'code': 1, 'message': str(exc), 'data': None}

    def parse_callback(self, data: dict, headers=None, raw_body: bytes = b'') -> Optional[dict]:
        """验签后严格绑定配置的支付宝应用与收款账号。"""
        payload = data.dict() if hasattr(data, 'dict') else dict(data)
        if not self.alipay:
            return payload if self.mock_enabled else None

        signature = payload.pop('sign', None)
        if not signature:
            return None
        try:
            if not self.alipay.verify(payload, signature):
                return None
        except Exception:
            logger.warning(
                "payment_callback_rejected",
                extra={'gateway': 'alipay', 'error_code': 'sdk_verify_exception'},
            )
            return None

        if payload.get('app_id') != self.app_id:
            return None
        if payload.get('seller_id') != self.seller_id:
            return None
        return payload

    def verify_callback(self, data: dict, headers=None, raw_body: bytes = b'') -> bool:
        """兼容布尔验签接口，不执行第二次验签。"""
        return self.parse_callback(data, headers, raw_body) is not None

    def get_trade_status(self, data: dict) -> tuple:
        """从已验签回调数据获取交易状态"""
        status_map = {
            'TRADE_SUCCESS': 'paid',
            'TRADE_FINISHED': 'paid',
            'TRADE_CLOSED': 'closed',
        }
        return (
            data.get('out_trade_no', ''),
            status_map.get(data.get('trade_status', ''), 'pending'),
            Decimal(data.get('total_amount', '0')),
        )
