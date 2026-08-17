"""
Email Verification Utilities
"""
import hashlib
import secrets
from datetime import timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone


def generate_verification_token(email: str) -> str:
    """生成邮箱验证 token (带摘要的 secure token)"""
    raw = f"{email}{secrets.token_hex(16)}{settings.SECRET_KEY}"
    return secrets.token_hex(32)


def hash_token(token: str) -> str:
    """对 token 做过敏处理后存储"""
    return hashlib.sha256(token.encode()).hexdigest()


def send_verification_email(user, token: str):
    """发送验证邮件"""
    verify_url = f"{getattr(settings, 'BASE_URL', 'https://account.fipai.cn')}/api/auth/verify-email/?token={token}"

    context = {
        'user': user,
        'verify_url': verify_url,
        'site_name': 'FIP.AI',
    }

    subject = '验证您的 FIP.AI 账号邮箱'
    html_message = render_to_string('accounts/email_verification.html', context) if False else f"""
    <h2>您好，{user.first_name or user.username}</h2>
    <p>感谢您注册 FIP.AI 账号，请点击以下链接验证您的邮箱：</p>
    <p><a href="{verify_url}">{verify_url}</a></p>
    <p>如果无法点击，请复制链接到浏览器打开。</p>
    <p>该链接有效期为 24 小时。</p>
    <p>— FIP.AI 团队</p>
    """

    plain_message = f"""
您好，{user.first_name or user.username}

感谢您注册 FIP.AI 账号，请访问以下链接验证您的邮箱：

{verify_url}

该链接有效期为 24 小时。

— FIP.AI 团队
    """.strip()

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.EMAIL_FROM,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception:
        return False


def verify_token(token: str) -> tuple:
    """
    校验 token，返回 (success, user_or_error_message)
    """
    from .models import EmailVerification
    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        verification = EmailVerification.objects.get(
            hashed_token=hash_token(token),
            is_used=False,
        )
    except EmailVerification.DoesNotExist:
        return False, "无效的验证码"

    if verification.is_expired():
        return False, "验证码已过期，请重新发送"

    # 获取用户
    try:
        user = User.objects.get(email=verification.email)
    except User.DoesNotExist:
        return False, "用户不存在"

    # 标记已使用
    verification.mark_used()

    # 激活用户
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=['is_active'])

    return True, user
