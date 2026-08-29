"""
Payment Gateway Base Class
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional


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
        """创建支付订单。"""
        raise NotImplementedError

    @abstractmethod
    def query_order(self, out_trade_no: str) -> dict:
        """查询订单状态。"""
        raise NotImplementedError

    @abstractmethod
    def refund(self, out_trade_no: str, amount: Decimal, reason: str = None) -> dict:
        """发起退款。"""
        raise NotImplementedError

    @abstractmethod
    def parse_callback(
        self,
        data: dict,
        headers=None,
        raw_body: bytes = b'',
    ) -> Optional[dict]:
        """一次完成回调验签/解密，返回可信业务字典，失败返回 None。"""
        raise NotImplementedError

    def verify_callback(self, data: dict, headers=None, raw_body: bytes = b'') -> bool:
        """兼容旧调用方；验签仅由 parse_callback 执行一次。"""
        return self.parse_callback(data, headers, raw_body) is not None

    def handle_callback(self, data: dict) -> tuple:
        """处理回调，返回 (out_trade_no, status, amount)。"""
        raise NotImplementedError


class PaymentError(Exception):
    """支付异常"""
    pass
