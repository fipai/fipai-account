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
    ALIPAY_SDK_AVAILABLE = False


class AlipayGateway:
    """支付宝支付网关"""

    def __init__(self, config: dict):
        self.config = config
        self.app_id = config.get('app_id', '')
        self.private_key = config.get('private_key', '')
        self.public_key = config.get('public_key', '')
        self.sandbox = config.get('sandbox', True)

        if ALIPAY_SDK_AVAILABLE and self.app_id:
            self.alipay = AliPay(
                appid=self.app_id,
                app_notify_url=None,
                app_private_key_string=self.private_key,
                alipay_public_key_string=self.public_key,
                sign_type="RSA2",
                debug=self.sandbox
            )
        else:
            self.alipay = None
            logger.warning("Alipay SDK not available or app_id not configured")

    def create_order(
        self,
        out_trade_no: str,
        amount: Decimal,
        subject: str,
        notify_url: str,
        return_url: Optional[str] = None
    ) -> dict:
        """创建支付宝订单"""
        if not self.alipay:
            # Mock response for development
            return {
                'code': 0,
                'message': 'success',
                'data': {
                    'trade_no': f'ALipay_{out_trade_no}',
                    'pay_url': f'https://openapi-sandbox.dl.alipaydev.com/gateway.do?out_trade_no={out_trade_no}',
                    'qr_code': f'https://qr.alipay.com/{out_trade_no}',
                    'mock': True
                }
            }

        try:
            # 构建支付请求
            if self.sandbox:
                # 沙箱环境
                pay_url = "https://openapi-sandbox.dl.alipaydev.com/gateway.do"
            else:
                pay_url = "https://openapi.alipay.com/gateway.do"

            order_string = self.alipay.api_alipay_trade_page_pay(
                out_trade_no=out_trade_no,
                total_amount=str(amount),
                subject=subject,
                return_url=return_url,
                notify_url=notify_url
            )

            pay_url = f"{pay_url}?{order_string}"

            return {
                'code': 0,
                'message': 'success',
                'data': {
                    'trade_no': out_trade_no,
                    'pay_url': pay_url,
                    'qr_code': None,
                }
            }
        except Exception as e:
            logger.error(f"Alipay create_order failed: {e}")
            return {
                'code': 1,
                'message': str(e),
                'data': None
            }

    def query_order(self, out_trade_no: str) -> dict:
        """查询订单状态"""
        if not self.alipay:
            return {
                'code': 0,
                'message': 'success',
                'data': {'status': 'pending'}
            }

        try:
            result = self.alipay.api_alipay_trade_query(out_trade_no=out_trade_no)
            trade_status = result.get('trade_status', 'WAIT_BUYER_PAY')

            status_map = {
                'WAIT_BUYER_PAY': 'pending',
                'TRADE_CLOSED': 'closed',
                'TRADE_SUCCESS': 'paid',
                'TRADE_FINISHED': 'paid',
            }

            return {
                'code': 0,
                'message': 'success',
                'data': {
                    'status': status_map.get(trade_status, 'pending'),
                    'trade_no': result.get('trade_no'),
                    'amount': result.get('total_amount'),
                }
            }
        except Exception as e:
            logger.error(f"Alipay query_order failed: {e}")
            return {'code': 1, 'message': str(e), 'data': None}

    def refund(self, out_trade_no: str, amount: Decimal, reason: str = None) -> dict:
        """退款"""
        if not self.alipay:
            return {'code': 0, 'message': 'success', 'data': {'refund_amount': str(amount)}}

        try:
            result = self.alipay.api_alipay_trade_refund(
                out_trade_no=out_trade_no,
                refund_amount=str(amount),
                refund_reason=reason or '用户退款'
            )
            return {
                'code': 0,
                'message': 'success',
                'data': {'refund_amount': result.get('refund_fee')}
            }
        except Exception as e:
            logger.error(f"Alipay refund failed: {e}")
            return {'code': 1, 'message': str(e), 'data': None}

    def verify_callback(self, data: dict) -> bool:
        """验证回调签名"""
        if not self.alipay:
            return True  # Mock mode

        try:
            signature = data.pop('sign', None)
            return self.alipay.verify(data, signature)
        except Exception:
            return False

    def get_trade_status(self, data: dict) -> tuple:
        """从回调数据获取交易状态"""
        out_trade_no = data.get('out_trade_no', '')
        trade_status = data.get('trade_status', '')
        amount = Decimal(data.get('total_amount', '0'))

        status_map = {
            'TRADE_SUCCESS': 'paid',
            'TRADE_FINISHED': 'paid',
            'TRADE_CLOSED': 'closed',
        }

        return out_trade_no, status_map.get(trade_status, 'pending'), amount
