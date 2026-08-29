from django.urls import path
from .views import (
    RegisterView, LoginView, UserView, SubscriptionView, OrderListView,
    ProfileUpdateView, PasswordChangeView,
    SendCodeView, RegisterPhoneView, LoginPhoneView,
    CookieTokenRefreshView, LogoutView, TenantListView, TenantSwitchView,
    TwoFactorAuthSetupView, TwoFactorAuthVerifyView, TwoFactorAuthDisableView, TwoFactorAuthStatusView,
    AccountDeletionRequestView, AccountDeletionStatusView, AccountDeleteConfirmView,
)

urlpatterns = [
    # 手机号注册/登录
    path('send-code/', SendCodeView.as_view(), name='auth-send-code'),
    path('register/phone/', RegisterPhoneView.as_view(), name='auth-register-phone'),
    path('login/phone/', LoginPhoneView.as_view(), name='auth-login-phone'),

    # 邮箱注册（保留）
    path('register/', RegisterView.as_view(), name='auth-register'),

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
