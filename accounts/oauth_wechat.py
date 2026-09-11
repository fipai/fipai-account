"""微信开放平台网站应用 OAuth（扫码登录）。

仅依赖 requests,不引第三方 SDK;空 APPID 时 build_authorize_url 会返回 None,
前端收到 None 后展示「即将上线」降级提示。
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import quote

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

WECHAT_AUTHORIZE_URL = 'https://open.weixin.qq.com/connect/qrconnect'
WECHAT_TOKEN_URL = 'https://api.weixin.qq.com/sns/oauth2/access_token'
WECHAT_USERINFO_URL = 'https://api.weixin.qq.com/sns/userinfo'


class WeChatOAuthError(Exception):
    """微信 OAuth 流程中的可恢复错误。"""


class WeChatOAuth:
    """封装微信开放平台网站应用的 OAuth 三步流程。"""

    def __init__(self):
        self.appid: str = getattr(settings, 'WECHAT_OPEN_APPID', '')
        self.secret: str = getattr(settings, 'WECHAT_OPEN_SECRET', '')
        self.redirect_uri: str = getattr(settings, 'WECHAT_OPEN_REDIRECT_URI', '')

    @property
    def is_configured(self) -> bool:
        return bool(self.appid and self.secret and self.redirect_uri)

    def build_authorize_url(self, state: str) -> Optional[str]:
        """生成扫码页 URL;未配置时返回 None 让前端降级。"""
        if not self.is_configured:
            return None
        return (
            f"{WECHAT_AUTHORIZE_URL}?appid={self.appid}"
            f"&redirect_uri={quote(self.redirect_uri, safe='')}"
            f"&response_type=code&scope=snsapi_login"
            f"&state={state}#wechat_redirect"
        )

    def exchange_code(self, code: str) -> dict:
        """用 code 换 access_token + openid。"""
        try:
            r = requests.get(
                WECHAT_TOKEN_URL,
                params={
                    'appid': self.appid,
                    'secret': self.secret,
                    'code': code,
                    'grant_type': 'authorization_code',
                },
                timeout=5,
            ).json()
        except requests.RequestException as e:
            raise WeChatOAuthError(f'微信 token 接口请求失败: {e}') from e
        if 'openid' not in r:
            raise WeChatOAuthError(f'微信 token 换码失败: {r.get("errmsg", r)}')
        return r

    def get_userinfo(self, access_token: str, openid: str) -> dict:
        """用 access_token 拉用户公开信息。"""
        try:
            r = requests.get(
                WECHAT_USERINFO_URL,
                params={'access_token': access_token, 'openid': openid},
                timeout=5,
            ).json()
        except requests.RequestException as e:
            raise WeChatOAuthError(f'微信 userinfo 请求失败: {e}') from e
        if 'openid' not in r:
            raise WeChatOAuthError(f'微信 userinfo 失败: {r.get("errmsg", r)}')
        return r
