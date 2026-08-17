"""
Payment Gateway Base Class
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class PaymentGateway(ABC):
    """支付网关抽象基类"""

    def __init__(self, config: dict):
        self.config = config
        self.sandbox = config.get('sandbox', True)

    @abstractmethod
    def create_order(
        self,
        out_trade_no: str,
        amount: Decimal,
        subject: str,
        notify_url: str,
        return_url: Optional[str] = None
    ) -> dict:
        """
        创建支付订单
        返回: {
            'code': 0,  # 0=成功
            'message': 'success',
            'data': {
                'trade_no': 'xxx',  # 渠道订单号
                'pay_url': 'https://xxx',  # 支付链接
                'qr_code': 'xxx',  # 二维码
            }
        }
        """
        pass

    @abstractmethod
    def query_order(self, out_trade_no: str) -> dict:
        """
        查询订单状态
        """
        pass

    @abstractmethod
    def refund(self, out_trade_no: str, amount: Decimal, reason: str = None) -> dict:
        """
        退款
        """
        pass

    @abstractmethod
    def verify_callback(self, data: dict) -> bool:
        """
        验证回调签名
        """
        pass

    def handle_callback(self, data: dict) -> tuple:
        """
        处理回调，返回 (out_trade_no, status, amount)
        """
        raise NotImplementedError


class PaymentError(Exception):
    """支付异常"""
    pass
