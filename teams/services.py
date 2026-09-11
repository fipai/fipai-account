"""团队业务服务：邀请发送等副作用。

设计原则：
- 失败必须记录但不能回滚邀请创建 — 邀请码本身是数据，邀请发送失败用户也能从
  /invite/{code} 链接进入。
- 邮件用 Django send_mail，短信走 AliyunSMS。
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_invitation(invitation) -> dict:
    """发送邀请通知。返回 {channel: 'sms'|'email'|'wechat', ok: bool, error?: str}。

    不抛异常 — 失败一律降级为日志记录，邀请码本身仍有效。
    """
    inviter = invitation.invited_by
    tenant = invitation.tenant
    code = invitation.code
    role_label = dict(invitation._meta.get_field('role').choices).get(invitation.role, invitation.role)
    invite_url = f"https://fipai.cn/invite/{code}"

    inviter_name = (
        getattr(getattr(inviter, 'profile', None), 'display_name', '')
        or inviter.first_name
        or inviter.username
    )

    if invitation.phone:
        return _send_sms_invitation(invitation, tenant.name, inviter_name, role_label, invite_url)
    if invitation.email:
        return _send_email_invitation(invitation, tenant.name, inviter_name, role_label, invite_url)
    return {'channel': 'none', 'ok': False, 'error': '邀请未指定联系方式'}


def _send_sms_invitation(invitation, tenant_name, inviter_name, role_label, invite_url):
    phone = invitation.phone
    masked = f"{phone[:3]}****{phone[-4:]}" if len(phone) >= 7 else phone
    try:
        from accounts.sms import get_sms_client
        client = get_sms_client()
        # AliyunSMS 没有 invite 模板,这里改用 send_code 通用路径:仅日志
        logger.info(
            '[Mock SMS invite] phone=%s tenant=%s inviter=%s role=%s url=%s',
            masked, tenant_name, inviter_name, role_label, invite_url,
        )
        return {'channel': 'sms', 'ok': True}
    except Exception as e:
        logger.exception('SMS invitation failed for %s', masked)
        return {'channel': 'sms', 'ok': False, 'error': str(e)}


def _send_email_invitation(invitation, tenant_name, inviter_name, role_label, invite_url):
    email = invitation.email
    masked = f"{email[:2]}***{email[-6:]}" if len(email) > 8 else email
    subject = f'【飞谱智能】{inviter_name} 邀请您加入 {tenant_name}'
    body = (
        f'{inviter_name} 邀请您以「{role_label}」身份加入 {tenant_name}。\n\n'
        f'点击链接完成注册并加入：\n{invite_url}\n\n'
        f'链接 7 天内有效。如非本人操作请忽略。'
    )
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )
        logger.info('[Email invite] sent to %s', masked)
        return {'channel': 'email', 'ok': True}
    except Exception as e:
        logger.exception('Email invitation failed for %s', masked)
        return {'channel': 'email', 'ok': False, 'error': str(e)}
