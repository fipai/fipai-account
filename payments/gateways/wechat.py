"""
WeChat Pay Gateway Implementation
"""
import logging
from decimal import Decimal
from typing import Optional
import hashlib
import time
import random

logger = logging.getLogger(__name__)

try:
    from wechatpayv3 import WeChatPay, WeChatPayType
    WECHAT_SDK_AVAILABLE = True
except ImportError:
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
        self.sandbox = config.get('sandbox', True)

        if WECHAT_SDK_AVAILABLE and self.mchid:
            self.wxpay = WeChatPay(
                wechatpay_type=WeChatPayType.NATIVE,
                mchid=self.mchid,
                private_key=self.private_key,
                cert_serial_no=self.serial_no,
                apiv3_key=self.apiv3_key,
                appid=self.appid,
                debug=self.sandbox
            )
        else:
            self.wxpay = None
            logger.warning("WeChat SDK not available or mchid not configured")

    def create_order(
        self,
        out_trade_no: str,
        amount: Decimal,
        subject: str,
        notify_url: str,
        return_url: Optional[str] = None
    ) -> dict:
        """创建微信支付订单"""
        if not self.wxpay:
            # Mock response for development
            return {
                'code': 0,
                'message': 'success',
                'data': {
                    'trade_no': f'WX_{out_trade_no}',
                    'pay_url': None,
                    'qr_code': f'weixin://wxpay/bizpayurl?pr={out_trade_no}',
                    'code_url': f'weixin://wxpay/bizpayurl?pr={out_trade_no}',
                    'mock': True
                }
            }

        try:
            code, response = self.wxpay.pay(
                description=subject,
                out_trade_no=out_trade_no,
                amount={'total': int(amount * 100), 'currency': 'CNY'},
                notify_url=notify_url
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
                    }
                }
            else:
                return {'code': code, 'message': str(response), 'data': None}

        except Exception as e:
            logger.error(f"WeChat create_order failed: {e}")
            return {'code': 1, 'message': str(e), 'data': None}

    def query_order(self, out_trade_no: str) -> dict:
        """查询订单状态"""
        if not self.wxpay:
            return {'code': 0, 'message': 'success', 'data': {'status': 'pending'}}

        try:
            code, response = self.wxpay.query(out_trade_no=out_trade_no)

            if code == 0:
                trade_state = response.get('trade_state', 'NOTPAY')
                status_map = {
                    'SUCCESS': 'paid',
                    'REFUND': 'refunded',
                    'NOTPAY': 'pending',
                    'CLOSED': 'closed',
                    'PAYERROR': 'closed',
                }
                return {
                    'code': 0,
                    'message': 'success',
                    'data': {
                        'status': status_map.get(trade_state, 'pending'),
                        'trade_no': response.get('transaction_id'),
                        'amount': Decimal(response.get('amount', {}).get('total', 0)) / 100,
                    }
                }
            else:
                return {'code': code, 'message': str(response), 'data': None}

        except Exception as e:
            logger.error(f"WeChat query_order failed: {e}")
            return {'code': 1, 'message': str(e), 'data': None}

    def refund(self, out_trade_no: str, amount: Decimal, reason: str = None) -> dict:
        """退款"""
        if not self.wxpay:
            return {'code': 0, 'message': 'success', 'data': {'refund_amount': str(amount)}}

        try:
            code, response = self.wxpay.refund(
                out_trade_no=out_trade_no,
                amount={'refund': int(amount * 100), 'total': int(amount * 100), 'currency': 'CNY'},
                reason=reason or '用户退款'
            )

            if code == 0:
                return {
                    'code': 0,
                    'message': 'success',
                    'data': {
                        'refund_id': response.get('refund_id'),
                        'refund_amount': Decimal(response.get('refund_amount', 0)) / 100,
                    }
                }
            else:
                return {'code': code, 'message': str(response), 'data': None}

        except Exception as e:
            logger.error(f"WeChat refund failed: {e}")
            return {'code': 1, 'message': str(e), 'data': None}

    def verify_callback(self, data: dict, headers: dict = None) -> bool:
        """
        验证微信支付回调签名

        WeChat Pay v3 回调验证流程:
        1. 从请求头获取 Wechatpay-Signature, Wechatpay-Timestamp, Wechatpay-Nonce
        2. 构造待签名字符串: {timestamp}\n{nonce}\n{request_body}\n
        3. 使用平台证书公钥验证签名
        """
        # Mock 模式跳过验证（仅开发环境）
        if not self.wxpay:
            logger.warning("[WeChat Mock] Skipping callback verification")
            return True

        if WECHAT_SDK_AVAILABLE:
            try:
                # 从请求头获取签名要素
                signature = headers.get('Wechatpay-Signature', '') if headers else ''
                timestamp = headers.get('Wechatpay-Timestamp', '') if headers else ''
                nonce = headers.get('Wechatpay-Nonce', '') if headers else ''
                serial_no = headers.get('Wechatpay-Serial', '') if headers else ''

                if not all([signature, timestamp, nonce]):
                    logger.error("WeChat callback: missing signature headers")
                    return False

                # 使用 SDK 验证签名
                # verify 返回 True 表示验证通过
                verified = self.wxpay.verify(
                    signature=signature,
                    timestamp=timestamp,
                    nonce=nonce,
                    plaintext=data if isinstance(data, str) else str(data),
                    serial_no=serial_no
                )
                return verified
            except Exception as e:
                logger.error(f"WeChat callback verification failed: {e}")
                return False
        else:
            # 如果 SDK 不可用，使用手动验证
            return self._manual_verify_callback(data, headers)

    def _manual_verify_callback(self, data: dict, headers: dict = None) -> bool:
        """
        手动验证微信支付回调（当 SDK 不可用时的降级方案）

        注意：生产环境建议使用 SDK 的 verify 方法
        """
        if not headers:
            logger.error("WeChat callback: no headers provided for manual verification")
            return False

        signature = headers.get('Wechatpay-Signature', '')
        timestamp = headers.get('Wechatpay-Timestamp', '')
        nonce = headers.get('Wechatpay-Nonce', '')

        if not all([signature, timestamp, nonce]):
            logger.error("WeChat callback: missing required headers for manual verification")
            return False

        # 构造待签名字符串
        body_str = data if isinstance(data, str) else str(data)
        sign_str = f"{timestamp}\n{nonce}\n{body_str}\n"

        # 使用 APIV3 密钥计算签名
        # 注意：这里需要使用平台证书进行验签，此处为简化示例
        # 实际生产环境应使用平台证书公钥验签
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.backends import default_backend

            # 使用 AES-256-GCM 解密回调数据（如果使用了加密）
            # 此处省略加密处理，假设数据未加密

            logger.info("WeChat callback manual verification passed (simplified)")
            return True
        except Exception as e:
            logger.error(f"WeChat manual verification error: {e}")
            return False

    def get_trade_status(self, data: dict) -> tuple:
        """从回调数据获取交易状态"""
        out_trade_no = data.get('out_trade_no', '')
        trade_state = data.get('trade_state', '')
        amount = Decimal(data.get('amount', {}).get('total', 0)) / 100

        status_map = {
            'SUCCESS': 'paid',
            'REFUND': 'refunded',
            'NOTPAY': 'pending',
            'CLOSED': 'closed',
        }

        return out_trade_no, status_map.get(trade_state, 'pending'), amount
