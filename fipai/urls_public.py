"""
公开路由 URL 配置（不需要租户上下文）
用于公共页面、登录、注册等
"""
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Grappelli 必须
    path('grappelli/', include('grappelli.urls')),
    # Django Admin
    path('admin/', admin.site.urls),
    # 公开的 API
    path('api/auth/', include('accounts.urls')),
    path('api/contact/pricing/', include('contact.urls')),
    # Wagtail 公开页面
    path('cms/', include('wagtail.admin.urls')),
    path('documents/', include('wagtail.documents.urls')),
    # 静态页面
    path('', include('pages.urls')),
]
