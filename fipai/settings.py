"""
Django settings for FIP.AI Account System (account.fipai.cn)
账号系统：用户、租户、套餐、支付、团队
"""
import os
import re
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


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized not in {'true', '1', 'yes', 'false', '0', 'no'}:
        raise ImproperlyConfigured(f'{name} must be a boolean value.')
    return normalized in {'true', '1', 'yes'}


# Gunicorn is bound to loopback and reached only through the trusted Nginx proxy.
if _env_bool('DJANGO_TRUST_X_FORWARDED_PROTO', not DEBUG):
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = _env_bool('DJANGO_SECURE_SSL_REDIRECT', not DEBUG)
SESSION_COOKIE_SECURE = _env_bool('DJANGO_SESSION_COOKIE_SECURE', not DEBUG)
CSRF_COOKIE_SECURE = _env_bool('DJANGO_CSRF_COOKIE_SECURE', not DEBUG)

try:
    SECURE_HSTS_SECONDS = int(
        os.environ.get('DJANGO_SECURE_HSTS_SECONDS', '3600' if not DEBUG else '0')
    )
except ValueError as exc:
    raise ImproperlyConfigured('DJANGO_SECURE_HSTS_SECONDS must be an integer.') from exc
if SECURE_HSTS_SECONDS < 0:
    raise ImproperlyConfigured('DJANGO_SECURE_HSTS_SECONDS must not be negative.')
SECURE_HSTS_INCLUDE_SUBDOMAINS = _env_bool('DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', False)
SECURE_HSTS_PRELOAD = _env_bool('DJANGO_SECURE_HSTS_PRELOAD', False)

_csrf_trusted_origins = [
    origin.strip()
    for origin in os.environ.get('DJANGO_CSRF_TRUSTED_ORIGINS', '').split(',')
    if origin.strip()
]
if _csrf_trusted_origins:
    CSRF_TRUSTED_ORIGINS = _csrf_trusted_origins
elif not DEBUG:
    CSRF_TRUSTED_ORIGINS = [
        f'https://{host}' for host in ALLOWED_HOSTS
        if host not in {'localhost', '127.0.0.1', '[::1]'} and '*' not in host
    ]

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
    'content',        # 官网内容管理
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
# Previously this defaulted to seven localhost dev ports + fipai.cn / home.fipai.cn.
# Combined with CORS_ALLOW_CREDENTIALS=True, that meant any dev port was treated
# as trusted for cookie-bearing requests. A production deploy that forgot to set
# DJANGO_CORS_ALLOWED_ORIGINS would still happily accept cross-site cookies.
#
# Now: env override required. The empty default fails closed in production
# rather than open by accident.
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('DJANGO_CORS_ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
]
if not CORS_ALLOWED_ORIGINS and DEBUG:
    # Dev: localhost variants are convenient. Logged loudly so it can't be
    # confused with a production default.
    CORS_ALLOWED_ORIGINS = [
        'http://localhost:5173',
        'http://localhost:5174',
        'http://127.0.0.1:5173',
    ]
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept', 'accept-encoding', 'authorization', 'content-type',
    'dnt', 'origin', 'user-agent', 'x-csrftoken', 'x-requested-with', 'x-tenant-id',
]

# =============================================================================
# JWT signing contract
# =============================================================================
JWT_ISSUER = 'https://account.fipai.cn'
JWT_AUDIENCE = 'fip-api'
JWT_ALGORITHM = os.environ.get('JWT_ALGORITHM', 'HS256' if DEBUG else '').strip().upper()
JWT_KEY_ID = os.environ.get('JWT_KEY_ID', 'fip-account-dev' if DEBUG else '').strip()
JWT_SIGNING_KEY = os.environ.get('JWT_SIGNING_KEY', '').replace('\\n', '\n').strip()
JWT_VERIFYING_KEY = os.environ.get('JWT_VERIFYING_KEY', '').replace('\\n', '\n').strip()

_insecure_jwt_values = {
    '', 'default', 'changeme', 'change-me', 'your-key-id',
    'your-signing-key', 'your-verifying-key',
}
if JWT_ALGORITHM not in {'HS256', 'RS256'}:
    raise ImproperlyConfigured('JWT_ALGORITHM must be HS256 (DEBUG only) or RS256.')
if not DEBUG and JWT_ALGORITHM != 'RS256':
    raise ImproperlyConfigured('JWT_ALGORITHM must be RS256 when DEBUG=false.')
if JWT_ALGORITHM == 'HS256':
    if not DEBUG:
        raise ImproperlyConfigured('HS256 is permitted only when DEBUG=true.')
    JWT_SIGNING_KEY = JWT_SIGNING_KEY or SECRET_KEY
    JWT_VERIFYING_KEY = JWT_VERIFYING_KEY or JWT_SIGNING_KEY
    if len(JWT_SIGNING_KEY) < 32 or JWT_SIGNING_KEY.lower() in _insecure_jwt_values:
        raise ImproperlyConfigured('JWT_SIGNING_KEY must be an explicit secure development secret.')
    if JWT_VERIFYING_KEY != JWT_SIGNING_KEY:
        raise ImproperlyConfigured('HS256 JWT_VERIFYING_KEY must equal JWT_SIGNING_KEY.')
else:
    import re
    from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, load_pem_private_key, load_pem_public_key,
    )

    if not JWT_SIGNING_KEY or not JWT_VERIFYING_KEY:
        raise ImproperlyConfigured('RS256 requires JWT_SIGNING_KEY and JWT_VERIFYING_KEY.')
    try:
        _jwt_private_key = load_pem_private_key(JWT_SIGNING_KEY.encode(), password=None)
        _jwt_public_key = load_pem_public_key(JWT_VERIFYING_KEY.encode())
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured('JWT signing/verifying keys must be valid PEM keys.') from exc
    if not isinstance(_jwt_private_key, RSAPrivateKey) or not isinstance(_jwt_public_key, RSAPublicKey):
        raise ImproperlyConfigured('JWT_SIGNING_KEY/JWT_VERIFYING_KEY must be RSA keys.')
    _derived_public = _jwt_private_key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    _configured_public = _jwt_public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    if _derived_public != _configured_public:
        raise ImproperlyConfigured('JWT_SIGNING_KEY and JWT_VERIFYING_KEY do not form a key pair.')

if not JWT_KEY_ID or not re.fullmatch(r'[A-Za-z0-9._-]{1,128}', JWT_KEY_ID):
    raise ImproperlyConfigured('JWT_KEY_ID is missing or invalid.')
if not DEBUG and JWT_KEY_ID.lower() in _insecure_jwt_values | {'fip-account-dev'}:
    raise ImproperlyConfigured('JWT_KEY_ID must be an explicit non-default production key id.')

# =============================================================================
# TOTP seed encryption
# =============================================================================
# The active Fernet key must be injected by the deployment secret manager. The
# optional JSON keyring keeps old keys available for decrypt-only rotation.
# Stored values include the key id but never the key itself.
import base64
import hashlib
import json
from cryptography.fernet import Fernet

TOTP_ENCRYPTION_KEY_ID = os.environ.get('TOTP_ENCRYPTION_KEY_ID', '').strip()
TOTP_ENCRYPTION_KEY = os.environ.get('TOTP_ENCRYPTION_KEY', '').strip()
_raw_totp_previous_keys = os.environ.get('TOTP_PREVIOUS_ENCRYPTION_KEYS', '').strip()

if not TOTP_ENCRYPTION_KEY_ID or not TOTP_ENCRYPTION_KEY:
    if DEBUG:
        TOTP_ENCRYPTION_KEY_ID = 'dev-derived-v1'
        TOTP_ENCRYPTION_KEY = base64.urlsafe_b64encode(
            hashlib.sha256(f'fip-totp-dev:{SECRET_KEY}'.encode('utf-8')).digest()
        ).decode('ascii')
    else:
        raise ImproperlyConfigured(
            'TOTP_ENCRYPTION_KEY_ID and TOTP_ENCRYPTION_KEY must be injected in production.'
        )

if not re.fullmatch(r'[A-Za-z0-9._-]{1,128}', TOTP_ENCRYPTION_KEY_ID):
    raise ImproperlyConfigured('TOTP_ENCRYPTION_KEY_ID is invalid.')

try:
    Fernet(TOTP_ENCRYPTION_KEY.encode('ascii'))
except (TypeError, ValueError) as exc:
    raise ImproperlyConfigured(
        'TOTP_ENCRYPTION_KEY must be a valid Fernet key.'
    ) from exc

if _raw_totp_previous_keys:
    try:
        TOTP_PREVIOUS_ENCRYPTION_KEYS = json.loads(_raw_totp_previous_keys)
    except json.JSONDecodeError as exc:
        raise ImproperlyConfigured(
            'TOTP_PREVIOUS_ENCRYPTION_KEYS must be a JSON object.'
        ) from exc
    if not isinstance(TOTP_PREVIOUS_ENCRYPTION_KEYS, dict):
        raise ImproperlyConfigured(
            'TOTP_PREVIOUS_ENCRYPTION_KEYS must be a JSON object.'
        )
else:
    TOTP_PREVIOUS_ENCRYPTION_KEYS = {}

TOTP_ENCRYPTION_KEYRING = dict(TOTP_PREVIOUS_ENCRYPTION_KEYS)
if TOTP_ENCRYPTION_KEY_ID in TOTP_ENCRYPTION_KEYRING:
    raise ImproperlyConfigured(
        'The active TOTP key id must not be duplicated in previous keys.'
    )
TOTP_ENCRYPTION_KEYRING[TOTP_ENCRYPTION_KEY_ID] = TOTP_ENCRYPTION_KEY
for _totp_key_id, _totp_key in TOTP_ENCRYPTION_KEYRING.items():
    if not isinstance(_totp_key_id, str) or not re.fullmatch(
        r'[A-Za-z0-9._-]{1,128}', _totp_key_id
    ):
        raise ImproperlyConfigured('TOTP encryption keyring contains an invalid key id.')
    if not isinstance(_totp_key, str):
        raise ImproperlyConfigured('TOTP encryption keyring values must be strings.')
    try:
        Fernet(_totp_key.encode('ascii'))
    except (TypeError, ValueError) as exc:
        raise ImproperlyConfigured(
            f'TOTP encryption key {_totp_key_id!r} is invalid.'
        ) from exc

# =============================================================================
# Django REST Framework
# =============================================================================
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'accounts.authentication.SessionJWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'EXCEPTION_HANDLER': 'fipai.exceptions.custom_exception_handler',
}

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'ALGORITHM': JWT_ALGORITHM,
    'SIGNING_KEY': JWT_SIGNING_KEY,
    'VERIFYING_KEY': JWT_VERIFYING_KEY,
    'ISSUER': JWT_ISSUER,
    'AUDIENCE': JWT_AUDIENCE,
    'AUTH_TOKEN_CLASSES': ('accounts.jwt.FIPAccessToken',),
    'TOKEN_OBTAIN_SERIALIZER': 'accounts.jwt.CustomTokenObtainPairSerializer',
    'TOKEN_REFRESH_SERIALIZER': 'accounts.jwt.FIPTokenRefreshSerializer',
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
    'seller_id': os.environ.get('ALIPAY_SELLER_ID', ''),
    'private_key': os.environ.get('ALIPAY_PRIVATE_KEY', ''),
    'public_key': os.environ.get('ALIPAY_PUBLIC_KEY', ''),
    # Mock 仅在 DEBUG=true 且显式开启 sandbox 时可用。
    'sandbox': _get_bool(os.environ.get('ALIPAY_SANDBOX', 'false')),
}

WECHAT_CONFIG = {
    'mchid': os.environ.get('WECHAT_MCHID', ''),
    'serial_no': os.environ.get('WECHAT_SERIAL_NO', ''),
    'private_key': os.environ.get('WECHAT_PRIVATE_KEY', ''),
    'apiv3_key': os.environ.get('WECHAT_APIV3_KEY', ''),
    'appid': os.environ.get('WECHAT_APPID', ''),
    # Mock 仅在 DEBUG=true 且显式开启 sandbox 时可用。
    'sandbox': _get_bool(os.environ.get('WECHAT_SANDBOX', 'false')),
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
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', EMAIL_FROM)

# =============================================================================
# 微信开放平台网站应用 OAuth（扫码登录）
# Phase 9 — 申请后填入；空时按钮 graceful 降级
# =============================================================================
WECHAT_OPEN_APPID = os.environ.get('WECHAT_OPEN_APPID', '')
WECHAT_OPEN_SECRET = os.environ.get('WECHAT_OPEN_SECRET', '')
WECHAT_OPEN_REDIRECT_URI = os.environ.get(
    'WECHAT_OPEN_REDIRECT_URI',
    'https://account.fipai.cn/api/auth/oauth/wechat/callback/',
)

# 邮件验证码限速（同一邮箱每小时最多发送次数）
EMAIL_CODE_HOURLY_LIMIT = int(os.environ.get('EMAIL_CODE_HOURLY_LIMIT', '5'))

# =============================================================================
# Django Admin 自定义样式
# =============================================================================
ADMIN_SITE_HEADER = "飞谱AI账号系统"
ADMIN_SITE_TITLE = "飞谱AI账号系统管理后台"
ADMIN_INDEX_TITLE = "欢迎来到飞谱AI账号系统"
