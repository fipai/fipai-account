from django.urls import path
from .views import (
    RegisterView, LoginView, UserView, SubscriptionView, OrderListView,
    ProfileUpdateView, PasswordChangeView,
    SendCodeView, RegisterPhoneView, LoginPhoneView,
    CookieTokenRefreshView, LogoutView, TenantListView, TenantSwitchView,
    TwoFactorAuthSetupView, TwoFactorAuthVerifyView, TwoFactorAuthDisableView, TwoFactorAuthStatusView,
    AccountDeletionRequestView, AccountDeletionStatusView, AccountDeleteConfirmView,
    RegisterPersonalView, RegisterEnterpriseView,
    LoginEmailView, SendEmailCodeView,
    WeChatLoginView, WeChatOAuthCallbackView,
)

urlpatterns = [
    # 手机号注册/登录
    path('send-code/', SendCodeView.as_view(), name='auth-send-code'),
    path('register/phone/', RegisterPhoneView.as_view(), name='auth-register-phone'),
    path('login/phone/', LoginPhoneView.as_view(), name='auth-login-phone'),

    # 邮箱注册（保留）
    path('register/', RegisterView.as_view(), name='auth-register'),

    # Phase 9 — 个人 / 企业注册 + 邮箱登录 + 邮箱验证码
    path('register/personal/', RegisterPersonalView.as_view(), name='auth-register-personal'),
    path('register/enterprise/', RegisterEnterpriseView.as_view(), name='auth-register-enterprise'),
    path('login/email/', LoginEmailView.as_view(), name='auth-login-email'),
    path('send-email-code/', SendEmailCodeView.as_view(), name='auth-send-email-code'),

    # Phase 9 — 微信开放平台 OAuth 扫码登录
    path('oauth/wechat/', WeChatLoginView.as_view(), name='auth-oauth-wechat'),
    path('oauth/wechat/callback/', WeChatOAuthCallbackView.as_view(), name='auth-oauth-wechat-callback'),

    # 登录（密码）
    path('login/', LoginView.as_view(), name='auth-login'),
    path('me/', UserView.as_view(), name='auth-me'),
    path('profile/', ProfileUpdateView.as_view(), name='auth-profile'),
    path('password/', PasswordChangeView.as_view(), name='auth-password'),
    path('subscription/', SubscriptionView.as_view(), name='auth-subscription'),
    path('orders/', OrderListView.as_view(), name='auth-orders'),
    path('token/refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('tenants/', TenantListView.as_view(), name='auth-tenants'),
    path('tenant/switch/', TenantSwitchView.as_view(), name='auth-tenant-switch'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),

    # 2FA
    path('2fa/setup/', TwoFactorAuthSetupView.as_view(), name='auth-2fa-setup'),
    path('2fa/verify/', TwoFactorAuthVerifyView.as_view(), name='auth-2fa-verify'),
    path('2fa/disable/', TwoFactorAuthDisableView.as_view(), name='auth-2fa-disable'),
    path('2fa/status/', TwoFactorAuthStatusView.as_view(), name='auth-2fa-status'),

    # 账户注销
    path('request-deletion/', AccountDeletionRequestView.as_view(), name='account-request-deletion'),
    path('deletion-status/', AccountDeletionStatusView.as_view(), name='account-deletion-status'),
    path('', AccountDeleteConfirmView.as_view(), name='account-delete'),
]
