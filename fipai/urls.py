"""
URL configuration for FIP.AI Account System (account.fipai.cn)
"""
from django.contrib import admin
from django.urls import path, include
from accounts.discovery import jwks, openid_configuration
from fipai.health import liveness, readiness

urlpatterns = [
    path('health/live', liveness, name='health-live'),
    path('health/ready', readiness, name='health-ready'),
    path('.well-known/jwks.json', jwks, name='jwks'),
    path('.well-known/openid-configuration', openid_configuration, name='openid-configuration'),
    path('admin/', admin.site.urls),
    # 账号系统
    path('api/auth/', include('accounts.urls')),
    path('api/account/', include('accounts.urls')),  # 账户注销相关
    # SaaS 功能
    path('api/subscriptions/', include('subscriptions.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/teams/', include('teams.urls')),
    path('api/tenants/', include('tenants.urls')),
    path('api/invoices/', include('invoices.urls')),
    # 审计日志
    path('api/audit/', include('audit.urls')),
    # OAuth2 Provider URLs
    path('oauth/', include('oauth2_provider.urls', namespace='oauth2_provider')),
]
