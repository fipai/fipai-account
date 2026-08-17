"""
Django settings for FIP.AI Account System (account.fipai.cn)
账号系统：用户、租户、套餐、支付、团队
"""
import os
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get('DJANGO_DEBUG', 'False').lower() in ('true', '1', 'yes')
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        import warnings
        warnings.warn("⚠️ DJANGO_SECRET_KEY 环境变量未设置，当前仅允许在 DEBUG 模式下使用临时密钥。")
        SECRET_KEY = 'django-insecure-dev-only-do-not-use-in-production'
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY 环境变量未设置，生产环境禁止使用默认密钥。")

_allowed_hosts = [host.strip() for host in os.environ.get('DJANGO_ALLOWED_HOSTS', '').split(',') if host.strip()]
if _allowed_hosts:
    ALLOWED_HOSTS = _allowed_hosts
elif DEBUG:
    ALLOWED_HOSTS = ['localhost', '127.0.0.1', '[::1]']
else:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS 环境变量未设置，生产环境必须配置允许的主机列表。")

# =============================================================================
# 中间件
# =============================================================================
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

# =============================================================================
# 应用 - 账号系统
# =============================================================================
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt',
    'corsheaders',
    'oauth2_provider',  # OAuth2 认证
    # 账号系统
    'accounts',       # 用户认证
    'tenants',        # 租户管理
    'subscriptions',  # 套餐订阅
    'payments',       # 支付系统
    'teams',          # 团队管理
    'invoices',       # 发票管理
    'audit',          # 审计日志
]

# 登录 URL
LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/admin/'
LOGOUT_REDIRECT_URL = '/'

# =============================================================================
# 数据库配置
# =============================================================================
USE_POSTGRES = os.environ.get('USE_POSTGRES', 'false').lower() in ('true', '1', 'yes')

if USE_POSTGRES:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': os.environ.get('DB_NAME', 'fipai_account'),
            'USER': os.environ.get('DB_USER', 'postgres'),
            'PASSWORD': os.environ.get('DB_PASSWORD', ''),
            'HOST': os.environ.get('DB_HOST', 'localhost'),
            'PORT': os.environ.get('DB_PORT', '5432'),
            'OPTIONS': {'connect_timeout': 10},
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# =============================================================================
# Templates
# =============================================================================
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

ROOT_URLCONF = 'fipai.urls'
WSGI_APPLICATION = 'fipai.wsgi.application'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# =============================================================================
# CORS
# =============================================================================
CORS_ALLOWED_ORIGINS = [
    'https://fipai.cn',
    'https://home.fipai.cn',
    'http://localhost:5173',
    'http://localhost:5174',
    'http://localhost:5175',
    'http://localhost:5176',
    'http://localhost:5177',
    'http://localhost:5178',
    'http://localhost:5179',
]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with', 'x-tenant-id',
]

# =============================================================================
# Django REST Framework
# =============================================================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'EXCEPTION_HANDLER': 'fipai.exceptions.custom_exception_handler',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=60),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': False,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'TOKEN_OBTAIN_SERIALIZER': 'accounts.jwt.CustomTokenObtainPairSerializer',
}

# =============================================================================
# OAuth2 Provider
# =============================================================================
OAUTH2_PROVIDER = {
    'SCOPES': {
        'read': 'Read scope',
        'write': 'Write scope',
    },
    'ACCESS_TOKEN_EXPIRE_SECONDS': 36000,
    'REFRESH_TOKEN_EXPIRE_SECONDS': 86400,
    'ROTATE_REFRESH_TOKEN': True,
}

AUTHENTICATION_BACKENDS = [
    'oauth2_provider.backends.OAuth2Backend',
    'django.contrib.auth.backends.ModelBackend',
]

# =============================================================================
# 支付网关配置
# =============================================================================
def _get_bool(val, default=False):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ('true', '1', 'yes')
    return default

ALIPAY_CONFIG = {
    'app_id': os.environ.get('ALIPAY_APP_ID', ''),
    'private_key': os.environ.get('ALIPAY_PRIVATE_KEY', ''),
    'public_key': os.environ.get('ALIPAY_PUBLIC_KEY', ''),
    'sandbox': _get_bool(os.environ.get('ALIPAY_SANDBOX', 'true')),
}

WECHAT_CONFIG = {
    'mchid': os.environ.get('WECHAT_MCHID', ''),
    'apikey': os.environ.get('WECHAT_APIKEY', ''),
    'appid': os.environ.get('WECHAT_APPID', ''),
    'sandbox': _get_bool(os.environ.get('WECHAT_SANDBOX', 'true')),
}

PAYMENT_CONFIG = {
    'alipay': ALIPAY_CONFIG,
    'wechat': WECHAT_CONFIG,
}

# =============================================================================
# 阿里云 SMS 配置
# =============================================================================
ALIYUN_SMS_ACCESS_KEY_ID = os.environ.get('ALIYUN_SMS_ACCESS_KEY_ID', '')
ALIYUN_SMS_ACCESS_KEY_SECRET = os.environ.get('ALIYUN_SMS_ACCESS_KEY_SECRET', '')
ALIYUN_SMS_SIGN_NAME = os.environ.get('ALIYUN_SMS_SIGN_NAME', 'FIPAI')
ALIYUN_SMS_TEMPLATE_CODE_register = os.environ.get('ALIYUN_SMS_TEMPLATE_CODE_register', '')
ALIYUN_SMS_TEMPLATE_CODE_login = os.environ.get('ALIYUN_SMS_TEMPLATE_CODE_login', '')
ALIYUN_SMS_SANDBOX = _get_bool(os.environ.get('ALIYUN_SMS_SANDBOX', 'true'))

# 基础 URL
BASE_URL = os.environ.get('BASE_URL', 'https://account.fipai.cn')

# =============================================================================
# 邮件配置
# =============================================================================
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'true').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'no-reply@fipai.cn')

# =============================================================================
# Django Admin 自定义样式
# =============================================================================
ADMIN_SITE_HEADER = "飞谱AI账号系统"
ADMIN_SITE_TITLE = "飞谱AI账号系统管理后台"
ADMIN_INDEX_TITLE = "欢迎来到飞谱AI账号系统"
