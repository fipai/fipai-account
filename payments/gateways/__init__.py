"""
Payment Gateway Factory
"""
from django.conf import settings
from .base import PaymentGateway, PaymentError
from .alipay import AlipayGateway
from .wechat import WechatGateway


def get_gateway(gateway_name: str) -> PaymentGateway:
    """获取支付网关实例"""
    config = getattr(settings, 'PAYMENT_CONFIG', {}).get(gateway_name, {})

    if gateway_name == 'alipay':
        return AlipayGateway(config)
    elif gateway_name == 'wechat':
        return WechatGateway(config)
    else:
        raise PaymentError(f"Unknown gateway: {gateway_name}")


def get_available_gateways():
    """获取可用的支付网关列表"""
    gateways = []
    config = getattr(settings, 'PAYMENT_CONFIG', {})

    if config.get('alipay', {}).get('app_id'):
        gateways.append({'name': 'alipay', 'name_display': '支付宝'})

    if config.get('wechat', {}).get('mchid'):
        gateways.append({'name': 'wechat', 'name_display': '微信支付'})

    return gateways
