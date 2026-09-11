from typing import Optional
from urllib.parse import urlencode

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenRefreshView
from django.conf import settings
from django.contrib.auth import get_user_model, authenticate
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone

from .serializers import (
    RegisterSerializer, UserSerializer,
    SendCodeSerializer, RegisterPhoneSerializer, LoginPhoneSerializer,
    TenantSwitchSerializer,
    RegisterPersonalSerializer, RegisterEnterpriseSerializer,
    LoginEmailSerializer, SendEmailCodeSerializer,
)
from .models import (
    SMSCode, TwoFactorAuth, AccountDeletionRequest, LoginChallenge,
    AccountProfile,
)
from .sms import generate_code, get_sms_client, SMS_CODE_EXPIRE_MINUTES, SMS_DAILY_LIMIT
from .authentication import CookieOrHeaderJWTAuthentication
from .oauth_wechat import WeChatOAuth, WeChatOAuthError
import accounts.totp_service as totp_service
from subscriptions.models import Subscription
from payments.models import PaymentTransaction
from teams.models import TeamMember
from tenants.models import Tenant
from django.contrib.auth.hashers import check_password

User = get_user_model()

SSO_ACCESS_COOKIE_NAME = "fip_access_token"
LOGIN_CHALLENGE_LIFETIME = timezone.timedelta(minutes=5)


def _requires_two_factor(user) -> bool:
    try:
        return bool(user.two_factor_auth.enabled)
    except TwoFactorAuth.DoesNotExist:
        return False


def _login_challenge_response(user) -> Response:
    _, bearer = LoginChallenge.create_for_user(
        user, lifetime=LOGIN_CHALLENGE_LIFETIME
    )
    return Response(
        {
            "requires_2fa": True,
            "challenge": bearer,
            "expires_in": int(LOGIN_CHALLENGE_LIFETIME.total_seconds()),
        },
        status=status.HTTP_202_ACCEPTED,
    )


SSO_REFRESH_COOKIE_NAME = "fip_refresh_token"


def _sso_cookie_domain(request) -> Optional[str]:
    """
    Use a shared cookie for all *.fipai.cn hosts in prod, but avoid setting an
    invalid Domain in local/dev environments.
    """
    try:
        host = request.get_host()  # Django HttpRequest
    except Exception:
        host = getattr(getattr(request, "_request", None), "get_host", lambda: "")()
    host = (host or "").split(":")[0].lower()
    if host.endswith("fipai.cn"):
        return ".fipai.cn"
    return None


def _cookie_secure(request) -> bool:
    try:
        return bool(request.is_secure())
    except Exception:
        req = getattr(request, "_request", None)
        return bool(getattr(req, "is_secure", lambda: False)())


def _forwarded_https(request) -> bool:
    try:
        xf_proto = request.META.get("HTTP_X_FORWARDED_PROTO", "")
        if isinstance(xf_proto, str) and xf_proto.lower().startswith("https"):
            return True
        xf_ssl = request.META.get("HTTP_X_FORWARDED_SSL", "")
        if isinstance(xf_ssl, str) and xf_ssl.lower() == "on":
            return True
    except Exception:
        pass
    return False


def _set_sso_cookies(request, response: Response, access: Optional[str], refresh: Optional[str]) -> None:
    if not access and not refresh:
        return

    domain = _sso_cookie_domain(request)
    secure = _cookie_secure(request) or _forwarded_https(request)
    samesite = "Lax"

    access_lifetime = settings.SIMPLE_JWT.get("ACCESS_TOKEN_LIFETIME")
    refresh_lifetime = settings.SIMPLE_JWT.get("REFRESH_TOKEN_LIFETIME")
    access_max_age = int(access_lifetime.total_seconds()) if access_lifetime else 3600
    refresh_max_age = int(refresh_lifetime.total_seconds()) if refresh_lifetime else 7 * 86400

    if access:
        response.set_cookie(
            SSO_ACCESS_COOKIE_NAME,
            access,
            max_age=access_max_age,
            httponly=True,
            secure=secure,
            samesite=samesite,
            domain=domain,
            path="/",
        )
    if refresh:
        response.set_cookie(
            SSO_REFRESH_COOKIE_NAME,
            refresh,
            max_age=refresh_max_age,
            httponly=True,
            secure=secure,
            samesite=samesite,
            domain=domain,
            path="/",
        )


def _clear_sso_cookies(request, response: Response) -> None:
    domain = _sso_cookie_domain(request)
    response.delete_cookie(SSO_ACCESS_COOKIE_NAME, domain=domain, path="/")
    response.delete_cookie(SSO_REFRESH_COOKIE_NAME, domain=domain, path="/")


def add_custom_token_claims(refresh_token, user, tenant_id=None):
    """Backward-compatible entry point backed by centralized JWT helpers."""
    from .jwt import add_custom_token_claims as apply_claims

    return apply_claims(refresh_token, user, tenant_id=tenant_id)


# =============================================================================
# 手机号注册/登录
# =============================================================================

class SendCodeView(generics.GenericAPIView):
    """
    发送短信验证码: POST /api/auth/send-code/
    Body: { "phone": "13800000000", "purpose": "register|login" }
    """
    permission_classes = [AllowAny]
    serializer_class = SendCodeSerializer

    def post(self, request):
        serializer = SendCodeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        purpose = serializer.validated_data['purpose']

        # 检查每天发送次数限制
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = SMSCode.objects.filter(
            phone=phone,
            created_at__gte=today_start,
        ).count()

        if today_count >= SMS_DAILY_LIMIT:
            return Response(
                {'error': f'该手机号今天发送次数已用完（{SMS_DAILY_LIMIT}次）'},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        # 生成验证码
        code = generate_code()

        # 保存验证码记录
        sms_code = SMSCode.objects.create(
            phone=phone,
            code=code,
            purpose=purpose,
            expires_at=timezone.now() + timezone.timedelta(minutes=SMS_CODE_EXPIRE_MINUTES),
        )

        # 发送短信
        sms_client = get_sms_client()
        result = sms_client.send_code(phone, purpose, code)

        if result.get('code') == 0:
            return Response({'ok': True})
        else:
            return Response(
                {'error': f'短信发送失败: {result.get("message")}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RegisterPhoneView(generics.GenericAPIView):
    """
    手机号注册: POST /api/auth/register/phone/
    Body: { "phone": "13800000000", "code": "123456", "password": "xxx" }
    """
    permission_classes = [AllowAny]
    serializer_class = RegisterPhoneSerializer

    def post(self, request):
        serializer = RegisterPhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        code = serializer.validated_data['code']
        password = serializer.validated_data['password']

        # 验证验证码
        valid_code = SMSCode.objects.filter(
            phone=phone,
            code=code,
            purpose='register',
            is_used=False,
            expires_at__gt=timezone.now(),
        ).order_by('-created_at').first()

        if not valid_code:
            return Response({'error': '验证码无效或已过期'}, status=status.HTTP_400_BAD_REQUEST)

        # 检查手机号是否已注册
        if User.objects.filter(username=phone).exists():
            return Response({'error': '该手机号已注册'}, status=status.HTTP_400_BAD_REQUEST)

        # 创建用户
        user = User.objects.create_user(
            username=phone,  # 用手机号作为 username
            password=password,
        )

        # 标记验证码已使用
        valid_code.is_used = True
        valid_code.save()

        # 生成 JWT
        from .jwt import issue_token_pair

        access, refresh = issue_token_pair(user)
        response = Response({
            'access': access,
            'refresh': refresh,
        }, status=status.HTTP_201_CREATED)
        _set_sso_cookies(request, response, access, refresh)
        return response


class LoginPhoneView(generics.GenericAPIView):
    """手机号第一因子登录；启用 2FA 时只返回一次性 challenge。"""
    permission_classes = [AllowAny]
    serializer_class = LoginPhoneSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        phone = serializer.validated_data['phone']
        code = serializer.validated_data['code']

        access = refresh = None
        challenge_response = None
        with transaction.atomic():
            valid_code = (
                SMSCode.objects.select_for_update()
                .filter(
                    phone=phone,
                    code=code,
                    purpose='login',
                    is_used=False,
                    expires_at__gt=timezone.now(),
                )
                .order_by('-created_at')
                .first()
            )
            if valid_code is None:
                return Response(
                    {'error': '登录凭据无效'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # A valid one-time SMS is consumed even if the account is unavailable.
            valid_code.is_used = True
            valid_code.save(update_fields=['is_used'])
            user = User.objects.filter(username=phone, is_active=True).first()
            if user is None:
                return Response(
                    {'error': '登录凭据无效'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if _requires_two_factor(user):
                challenge_response = _login_challenge_response(user)
            else:
                from .jwt import issue_token_pair
                access, refresh = issue_token_pair(user)

        if challenge_response is not None:
            return challenge_response
        response = Response({'access': access, 'refresh': refresh})
        _set_sso_cookies(request, response, access, refresh)
        return response


# =============================================================================
# 原有邮箱注册视图（保留但暂时禁用）
# =============================================================================

class RegisterView(generics.CreateAPIView):
    """
    注册（邮箱）: POST /api/auth/register/
    注意: 手机号注册请使用 /api/auth/register/phone/
    """
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            {'message': '注册成功', 'user_id': user.pk},
            status=status.HTTP_201_CREATED,
        )


# =============================================================================
# 登录（密码）
# =============================================================================

@method_decorator(csrf_exempt, name='dispatch')
class LoginView(generics.GenericAPIView):
    """密码第一因子登录；任何 JWT 都只在完整认证后签发。"""
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        identifier = request.data.get('username')
        password = request.data.get('password')
        user = None
        if identifier and password:
            user = authenticate(request=request, username=identifier, password=password)
            if user is None:
                # Preserve the documented email-login behavior without changing errors.
                email_user = User.objects.filter(email=identifier).only('username').first()
                if email_user is not None:
                    user = authenticate(
                        request=request,
                        username=email_user.username,
                        password=password,
                    )
        if user is None or not user.is_active:
            return Response(
                {'error': '登录凭据无效'},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if _requires_two_factor(user):
            return _login_challenge_response(user)

        from .jwt import issue_token_pair
        access, refresh = issue_token_pair(user)
        response = Response({'access': access, 'refresh': refresh})
        _set_sso_cookies(request, response, access, refresh)
        return response


# =============================================================================
# 用户信息
# =============================================================================

class TenantListView(generics.GenericAPIView):
    """List every tenant for which the current user has an active membership."""
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def get(self, request):
        from .jwt import build_tenant_summary, get_active_tenant_memberships

        memberships = get_active_tenant_memberships(request.user)
        return Response([build_tenant_summary(membership) for membership in memberships])


class TenantSwitchView(generics.GenericAPIView):
    """Issue a fresh token pair scoped to an authorized tenant membership."""
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]
    serializer_class = TenantSwitchSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant_id = serializer.validated_data["tenant_id"]

        from .jwt import (
            build_tenant_claims,
            get_active_tenant_membership,
            issue_token_pair,
        )

        membership = get_active_tenant_membership(request.user, tenant_id=tenant_id)
        if membership is None:
            # Deliberately identical for missing and unauthorized tenant IDs.
            return Response(
                {"error": "租户不存在或无权访问"},
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            from .models import AuthSession

            source_session = (
                AuthSession.objects.select_for_update()
                .filter(
                    sid=request.auth.get("sid"),
                    user=request.user,
                    revoked_at__isnull=True,
                    expires_at__gt=timezone.now(),
                )
                .first()
            )
            if source_session is None:
                raise AuthenticationFailed("Token is invalid or expired.")

            source_session.revoked_at = timezone.now()
            source_session.revoked_reason = "tenant_switched"
            source_session.save(
                update_fields=["revoked_at", "revoked_reason", "updated_at"]
            )
            access, refresh = issue_token_pair(
                request.user, tenant_id=membership.tenant_id
            )

        claims = build_tenant_claims(request.user, tenant_id=membership.tenant_id)
        response = Response({"access": access, "refresh": refresh, **claims})
        _set_sso_cookies(request, response, access, refresh)
        return response


class UserView(generics.RetrieveAPIView):
    """获取当前用户信息：GET /api/auth/me/（需 JWT）"""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def get_object(self):
        return self.request.user


class CookieTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        data = {}
        try:
            if getattr(request, "data", None):
                data = dict(request.data)
        except Exception:
            data = {}

        # Allow cookie-only refresh: if client didn't provide refresh token in body,
        # try reading it from HttpOnly cookie.
        if not data.get("refresh"):
            cookie_refresh = request.COOKIES.get(SSO_REFRESH_COOKIE_NAME)
            if cookie_refresh:
                data["refresh"] = cookie_refresh

        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            return Response(
                {'error': 'Token is invalid or expired'},
                status=status.HTTP_401_UNAUTHORIZED
            )

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        access = serializer.validated_data.get("access")
        refresh = serializer.validated_data.get("refresh")  # usually absent unless rotate enabled
        _set_sso_cookies(request, response, access, refresh)

        return response


class LogoutView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = request.data if getattr(request, "data", None) else {}
        refresh_candidates = [
            data.get("refresh"),
            request.COOKIES.get(SSO_REFRESH_COOKIE_NAME),
        ]

        authorization = request.META.get("HTTP_AUTHORIZATION", "")
        parts = authorization.split()
        header_access = (
            parts[1]
            if len(parts) == 2 and parts[0].lower() == "bearer"
            else None
        )
        access_candidates = [
            data.get("access"),
            header_access,
            request.COOKIES.get(SSO_ACCESS_COOKIE_NAME),
        ]

        # Try every distinct credential. A malformed/stale cookie must not
        # prevent a valid body/header token from revoking its server-side family.
        from .jwt import (
            revoke_auth_session_from_access_token,
            revoke_auth_session_from_token,
        )

        for raw_refresh in dict.fromkeys(filter(None, refresh_candidates)):
            revoke_auth_session_from_token(raw_refresh, reason="logout")
        for raw_access in dict.fromkeys(filter(None, access_candidates)):
            revoke_auth_session_from_access_token(raw_access, reason="logout")

        response = Response({"ok": True})
        _clear_sso_cookies(request, response)
        return response


class SubscriptionView(generics.RetrieveAPIView):
    """获取当前用户订阅信息：GET /api/auth/subscription/（需 JWT）"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def retrieve(self, request, *args, **kwargs):
        latest_sub = Subscription.objects.filter(
            user=request.user,
            status='active'
        ).select_related('plan').order_by('-end_date').first()

        if not latest_sub:
            return Response({
                'plan_name': '免费版',
                'plan_slug': 'free',
                'billing_cycle': '',
                'amount': '0',
                'status': 'inactive',
                'current_period_end': None,
            })

        return Response({
            'plan_name': latest_sub.plan.name,
            'plan_slug': latest_sub.plan.tier,
            'billing_cycle': latest_sub.plan.period,
            'amount': str(latest_sub.plan.price),
            'status': 'active',
            'current_period_end': latest_sub.end_date.isoformat() if latest_sub.end_date else None,
        })


class OrderListView(generics.ListAPIView):
    """获取用户订单列表：GET /api/auth/orders/（需 JWT）"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def list(self, request, *args, **kwargs):
        payments = PaymentTransaction.objects.filter(
            user=request.user
        ).select_related('subscription__plan').order_by('-created_at')

        orders = [{
            'id': p.id,
            'order_no': p.out_trade_no,
            'plan_name': p.subscription.plan.name if p.subscription else '',
            'amount': str(p.amount),
            'payment_method': p.gateway,
            'status': p.status,
            'created_at': p.created_at.isoformat(),
        } for p in payments]

        return Response(orders)


class ProfileUpdateView(generics.UpdateAPIView):
    """更新个人资料：PATCH /api/auth/profile/（需 JWT）"""
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def get_object(self):
        return self.request.user

    def update(self, request, *args, **kwargs):
        user = self.request.user
        # Handle email separately since UserSerializer has it as read_only
        email = request.data.get('email')
        if email is not None:
            user.email = email
            user.save(update_fields=['email'])
        # Handle first_name via serializer
        serializer = self.get_serializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if 'first_name' in serializer.validated_data:
            user.first_name = serializer.validated_data['first_name']
            user.save(update_fields=['first_name'])
        return Response(UserSerializer(user).data)


class PasswordChangeView(generics.CreateAPIView):
    """修改密码：POST /api/auth/password/（需 JWT）"""
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def create(self, request, *args, **kwargs):
        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')

        if not old_password or not new_password:
            return Response(
                {'detail': '请提供旧密码和新密码'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = request.user
        if not user.check_password(old_password):
            return Response(
                {'detail': '旧密码不正确'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()

        from .jwt import revoke_all_auth_sessions
        revoke_all_auth_sessions(user, reason='password_changed')
        response = Response({'detail': '密码修改成功'})
        _clear_sso_cookies(request, response)
        return response


# =============================================================================
# Two-Factor Authentication (2FA)
# =============================================================================

class TwoFactorAuthSetupView(generics.GenericAPIView):
    """
    启用 2FA: POST /api/auth/2fa/setup/
    返回 TOTP secret 和 provisioning URI 用于生成 QR 码
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def post(self, request):
        user = request.user

        # 检查是否已设置过 2FA（secret 存在表示已经配置过）
        tfa = TwoFactorAuth.objects.filter(user=user, secret__isnull=False).exclude(secret='').first()

        if tfa and tfa.enabled:
            return Response(
                {'error': '2FA 已经启用，如需重新设置请先禁用'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if tfa and tfa.secret and not tfa.enabled:
            return Response(
                {'error': '2FA 正在等待验证，如需重新设置请先取消'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 创建或获取 2FA 配置
        tfa, created = TwoFactorAuth.objects.get_or_create(user=user)

        # 生成新的 TOTP secret
        secret = totp_service.generate_totp_secret()
        backup_codes = totp_service.generate_backup_codes()

        # Encrypt the TOTP seed with the active secret-managed key. Backup
        # codes remain one-way SHA-256 hashes because they never need recovery.
        tfa.set_totp_secret(secret)
        tfa.backup_codes = [totp_service.hash_backup_code(code) for code in backup_codes]
        tfa.enabled = False  # 初始设置为未启用，等待验证第一个代码
        tfa.method = 'totp'
        tfa.save()

        # 生成 QR code URI
        provisioning_uri = totp_service.get_totp_provisioning_uri(secret, user.username)

        return Response({
            'secret': secret,
            'provisioning_uri': provisioning_uri,
            'backup_codes': backup_codes,  # 仅在此刻返回明文，之后不再返回
        }, status=status.HTTP_201_CREATED)


class TwoFactorAuthVerifyView(generics.GenericAPIView):
    """Verify enrollment for an authenticated user or a one-time login challenge."""
    permission_classes = [AllowAny]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    @staticmethod
    def _invalid_response():
        return Response(
            {'error': '验证失败'}, status=status.HTTP_400_BAD_REQUEST
        )

    def post(self, request):
        code = request.data.get('code')
        if not isinstance(code, str) or not code:
            return self._invalid_response()

        bearer = request.data.get('challenge')
        if request.user.is_authenticated and not bearer:
            with transaction.atomic():
                tfa = (
                    TwoFactorAuth.objects.select_for_update()
                    .filter(user=request.user, enabled=False)
                    .first()
                )
                if not tfa or not tfa.secret:
                    return self._invalid_response()
                try:
                    valid = totp_service.verify_totp(tfa.get_totp_secret(), code)
                except Exception:
                    valid = False
                if not valid:
                    return self._invalid_response()
                tfa.enabled = True
                tfa.save(update_fields=['enabled', 'updated_at'])
                from .jwt import revoke_all_auth_sessions
                revoke_all_auth_sessions(request.user, reason='2fa_enabled')

            response = Response({'ok': True, 'message': '2FA 启用成功'})
            _clear_sso_cookies(request, response)
            return response

        # A caller must never be able to select the account by user_id.
        if 'user_id' in request.data:
            return self._invalid_response()
        if not isinstance(bearer, str) or not bearer:
            return self._invalid_response()

        challenge_hash = LoginChallenge.hash_bearer(bearer)
        access = refresh = None
        used_backup = False
        with transaction.atomic():
            challenge = (
                LoginChallenge.objects.select_for_update()
                .select_related('user')
                .filter(challenge_hash=challenge_hash)
                .first()
            )
            now = timezone.now()
            if (
                challenge is None
                or challenge.used_at is not None
                or challenge.expires_at <= now
                or challenge.attempts >= 5
            ):
                return self._invalid_response()

            user = challenge.user
            tfa = (
                TwoFactorAuth.objects.select_for_update()
                .filter(user=user, enabled=True)
                .first()
            )
            if not user.is_active or tfa is None or not tfa.secret:
                challenge.attempts += 1
                challenge.save(update_fields=['attempts'])
                return self._invalid_response()

            try:
                valid_totp = totp_service.verify_totp(tfa.get_totp_secret(), code)
            except Exception:
                valid_totp = False
            valid_backup = False
            backup_index = None
            if not valid_totp:
                valid_backup, backup_index = totp_service.verify_backup_code(
                    tfa.backup_codes, code
                )
            if not valid_totp and not valid_backup:
                challenge.attempts += 1
                challenge.save(update_fields=['attempts'])
                return self._invalid_response()

            if valid_backup:
                tfa.backup_codes = totp_service.remove_used_backup_code(
                    tfa.backup_codes, backup_index
                )
                tfa.save(update_fields=['backup_codes', 'updated_at'])
                used_backup = True
            challenge.used_at = now
            challenge.save(update_fields=['used_at'])

            from .jwt import issue_token_pair
            access, refresh = issue_token_pair(user)

        response_data = {
            'ok': True,
            'verified': True,
            'access': access,
            'refresh': refresh,
        }
        if used_backup:
            response_data['used_backup'] = True
        response = Response(response_data)
        _set_sso_cookies(request, response, access, refresh)
        return response


class TwoFactorAuthDisableView(generics.GenericAPIView):
    """
    禁用 2FA: POST /api/auth/2fa/disable/
    需要验证密码
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def post(self, request):
        user = request.user
        password = request.data.get('password')

        if not password:
            return Response({'error': '请提供密码'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(password):
            return Response({'error': '密码错误'}, status=status.HTTP_400_BAD_REQUEST)

        tfa = TwoFactorAuth.objects.filter(user=user).first()
        if not tfa or not tfa.enabled:
            return Response({'error': '2FA 未启用'}, status=status.HTTP_400_BAD_REQUEST)

        tfa.enabled = False
        tfa.secret = ''
        tfa.backup_codes = []
        tfa.save()

        from .jwt import revoke_all_auth_sessions
        revoke_all_auth_sessions(user, reason='2fa_disabled')
        response = Response({'ok': True, 'message': '2FA 已禁用'})
        _clear_sso_cookies(request, response)
        return response


class TwoFactorAuthStatusView(generics.GenericAPIView):
    """
    查询 2FA 状态: GET /api/auth/2fa/status/
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def get(self, request):
        user = request.user
        tfa = TwoFactorAuth.objects.filter(user=user).first()

        if not tfa or not tfa.enabled:
            return Response({
                'enabled': False,
                'method': None,
                'backup_codes_remaining': 0,
            })

        return Response({
            'enabled': True,
            'method': tfa.method,
            'backup_codes_remaining': len(tfa.backup_codes),
        })


# =============================================================================
# Account Deletion
# =============================================================================

class AccountDeletionRequestView(generics.GenericAPIView):
    """
    提交账户注销申请: POST /api/account/request-deletion/
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def post(self, request):
        user = request.user
        reason = request.data.get('reason', '')

        # 检查是否已有待处理的注销申请
        existing = AccountDeletionRequest.objects.filter(
            user=user,
            status='pending'
        ).first()

        if existing:
            return Response(
                {'error': '已有待处理的注销申请，请等待处理完成'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 创建注销申请
        deletion_request = AccountDeletionRequest.objects.create(
            user=user,
            reason=reason,
            status='pending'
        )

        return Response({
            'ok': True,
            'request_id': deletion_request.id,
            'status': deletion_request.status,
            'requested_at': deletion_request.requested_at.isoformat(),
        }, status=status.HTTP_201_CREATED)


class AccountDeletionStatusView(generics.GenericAPIView):
    """
    查询注销状态: GET /api/account/deletion-status/
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def get(self, request):
        user = request.user
        deletion_request = AccountDeletionRequest.objects.filter(
            user=user
        ).order_by('-requested_at').first()

        if not deletion_request:
            return Response({
                'has_request': False,
            })

        return Response({
            'has_request': True,
            'request_id': deletion_request.id,
            'status': deletion_request.status,
            'reason': deletion_request.reason,
            'requested_at': deletion_request.requested_at.isoformat(),
            'processed_at': deletion_request.processed_at.isoformat() if deletion_request.processed_at else None,
            'data_anonymized': deletion_request.data_anonymized,
        })


class AccountDeleteConfirmView(generics.GenericAPIView):
    """
    确认注销（需验证密码）: DELETE /api/account/
    执行数据匿名化
    """
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieOrHeaderJWTAuthentication]

    def delete(self, request):
        user = request.user
        password = request.data.get('password')

        if not password:
            return Response({'error': '请提供密码以确认注销'}, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(password):
            return Response({'error': '密码错误'}, status=status.HTTP_400_BAD_REQUEST)

        # 获取或创建待处理的注销申请
        deletion_request, created = AccountDeletionRequest.objects.get_or_create(
            user=user,
            status='pending',
            defaults={'reason': '用户主动注销'}
        )

        # 执行数据匿名化
        # 1. 保留租户和订阅记录（审计需要）
        # 2. 匿名化用户个人信息
        user.username = f"deleted_user_{user.id}_{timezone.now().strftime('%Y%m%d%H%M%S')}"
        user.email = f"deleted_{user.id}@anonymized.local"
        user.first_name = ''
        user.last_name = ''
        user.is_active = False

        # 如果有 2FA，禁用它
        TwoFactorAuth.objects.filter(user=user).delete()

        user.save()

        # 更新注销申请状态
        deletion_request.status = 'completed'
        deletion_request.processed_at = timezone.now()
        deletion_request.data_anonymized = True
        deletion_request.anonymized_at = timezone.now()
        deletion_request.save()

        # 清除 SSO cookies
        response = Response({'ok': True, 'message': '账户已注销'})
        _clear_sso_cookies(request, response)
        return response


# =============================================================================
# Phase 9 — 个人/企业注册 + 邮箱登录 + 微信扫码登录 + 邮箱验证码
# =============================================================================

import secrets
import logging

logger = logging.getLogger(__name__)


def _resolve_register_identifier(phone: str, email: str) -> str:
    """Pick the unique identifier used for the User.username column."""
    if phone:
        return phone
    return email.lower()


def _consume_sms_code(identifier_value: str, code: str, purpose: str, *, by_phone: bool):
    """原子取一条未用且未过期的验证码并标记已用。"""
    lookup = {'phone': identifier_value} if by_phone else {'email': identifier_value.lower()}
    lookup.update(code=code, purpose=purpose, is_used=False, expires_at__gt=timezone.now())
    return (
        SMSCode.objects.select_for_update()
        .filter(**lookup)
        .order_by('-created_at')
        .first()
    )


def _build_personal_tenant(user, display_name: str) -> Tenant:
    """Create a personal workspace tenant and an owner TeamMember."""
    slug = f"personal-{user.id}-{secrets.token_hex(3)}"
    tenant = Tenant.objects.create(
        name=f"{display_name} 的个人空间",
        slug=slug,
        owner=user,
        status='trial',
        type='personal',
        max_users=2,
        max_api_calls=2000,
    )
    TeamMember.objects.create(tenant=tenant, user=user, role='owner', status='active')
    return tenant


class SendEmailCodeView(generics.GenericAPIView):
    """发送邮箱 6 位验证码：POST /api/auth/send-email-code/

    Body: { email, purpose: 'register'|'login' }
    限速：同一邮箱每小时最多 EMAIL_CODE_HOURLY_LIMIT 封。
    """
    permission_classes = [AllowAny]
    serializer_class = SendEmailCodeSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()
        purpose = serializer.validated_data['purpose']

        hourly_limit = getattr(settings, 'EMAIL_CODE_HOURLY_LIMIT', 5)
        one_hour_ago = timezone.now() - timezone.timedelta(hours=1)
        recent = SMSCode.objects.filter(
            email=email,
            purpose=purpose,
            created_at__gte=one_hour_ago,
        ).count()
        if recent >= hourly_limit:
            return Response(
                {'error': f'发送过于频繁,请 {60} 分钟后再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        code = generate_code()
        SMSCode.objects.create(
            email=email,
            code=code,
            purpose=purpose,
            expires_at=timezone.now() + timezone.timedelta(minutes=SMS_CODE_EXPIRE_MINUTES),
        )

        masked = f"{email[:2]}***{email[-6:]}" if len(email) > 8 else email
        try:
            sent = send_mail(
                subject='【飞谱智能】您的验证码',
                message=f'您的验证码是: {code},{SMS_CODE_EXPIRE_MINUTES} 分钟内有效。如非本人操作请忽略。',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
        except Exception as e:
            logger.exception("send_mail failed for %s", masked)
            return Response(
                {'error': f'邮件发送失败: {e}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if settings.DEBUG:
            logger.info('[Email code] %s purpose=%s code=%s', masked, purpose, code)
        return Response({'ok': True, 'sent': sent})


class RegisterPersonalView(generics.GenericAPIView):
    """个人注册：POST /api/auth/register/personal/

    Body: { name, phone|email, code, password, tos_accepted:true }
    自动创建 personal tenant,签发 token 对。
    """
    permission_classes = [AllowAny]
    serializer_class = RegisterPersonalSerializer

    @transaction.atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        phone = d.get('phone', '')
        email = d.get('email', '')
        identifier = _resolve_register_identifier(phone, email)
        by_phone = bool(phone)

        valid_code = _consume_sms_code(
            phone or email, d['code'], purpose='register', by_phone=by_phone,
        )
        if valid_code is None:
            return Response(
                {'error': '验证码无效或已过期'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(username=identifier).exists():
            return Response(
                {'error': '该账号已注册,请直接登录'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_user(
            username=identifier,
            email=email,
            password=d['password'],
            first_name=d['name'][:30],
        )

        valid_code.is_used = True
        valid_code.save(update_fields=['is_used'])

        AccountProfile.objects.create(
            user=user,
            account_type='personal',
            display_name=d['name'],
            tos_accepted_at=timezone.now(),
        )
        tenant = _build_personal_tenant(user, d['name'])

        from .jwt import issue_token_pair

        access, refresh = issue_token_pair(user)
        response = Response(
            {
                'access': access,
                'refresh': refresh,
                'account_type': 'personal',
                'tenant_id': tenant.id,
                'tenant_name': tenant.name,
            },
            status=status.HTTP_201_CREATED,
        )
        _set_sso_cookies(request, response, access, refresh)
        return response


class RegisterEnterpriseView(generics.GenericAPIView):
    """企业注册：POST /api/auth/register/enterprise/

    Body: { name, phone|email, code, password, tos_accepted,
            company_name, uscc, scale, industry, legal_representative? }
    """
    permission_classes = [AllowAny]
    serializer_class = RegisterEnterpriseSerializer

    @transaction.atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        d = serializer.validated_data

        phone = d.get('phone', '')
        email = d.get('email', '')
        identifier = _resolve_register_identifier(phone, email)
        by_phone = bool(phone)

        valid_code = _consume_sms_code(
            phone or email, d['code'], purpose='register', by_phone=by_phone,
        )
        if valid_code is None:
            return Response(
                {'error': '验证码无效或已过期'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(username=identifier).exists():
            return Response(
                {'error': '该账号已注册,请直接登录'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        uscc = d['uscc'].upper()
        if Tenant.objects.filter(uscc=uscc).exists():
            return Response(
                {'error': '该统一社会信用代码已注册'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_user(
            username=identifier,
            email=email,
            password=d['password'],
            first_name=d['name'][:30],
        )

        valid_code.is_used = True
        valid_code.save(update_fields=['is_used'])

        AccountProfile.objects.create(
            user=user,
            account_type='enterprise',
            display_name=d['name'],
            tos_accepted_at=timezone.now(),
        )

        slug = f"ent-{uscc[-8:].lower()}"
        tenant = Tenant.objects.create(
            name=d['company_name'],
            slug=slug,
            owner=user,
            status='trial',
            type='enterprise',
            uscc=uscc,
            scale=d['scale'],
            industry=d['industry'],
            legal_representative=d.get('legal_representative', ''),
        )
        TeamMember.objects.create(tenant=tenant, user=user, role='owner', status='active')

        from .jwt import issue_token_pair

        access, refresh = issue_token_pair(user)
        response = Response(
            {
                'access': access,
                'refresh': refresh,
                'account_type': 'enterprise',
                'tenant_id': tenant.id,
                'tenant_name': tenant.name,
                'company_name': d['company_name'],
            },
            status=status.HTTP_201_CREATED,
        )
        _set_sso_cookies(request, response, access, refresh)
        return response


class LoginEmailView(generics.GenericAPIView):
    """邮箱密码登录：POST /api/auth/login/email/

    Body: { email, password }
    """
    permission_classes = [AllowAny]
    serializer_class = LoginEmailSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()
        password = serializer.validated_data['password']

        # 用户可以用 email 或 username(手机号)登录
        user = (
            User.objects.filter(email__iexact=email)
            .union(User.objects.filter(username__iexact=email))
            .first()
        )

        if user is None or not user.check_password(password):
            return Response(
                {'error': '邮箱或密码错误'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.is_active:
            return Response(
                {'error': '账户已被停用'},
                status=status.HTTP_403_FORBIDDEN,
            )

        if _requires_two_factor(user):
            return _login_challenge_response(user)

        from .jwt import issue_token_pair

        access, refresh = issue_token_pair(user)
        response = Response({'access': access, 'refresh': refresh})
        _set_sso_cookies(request, response, access, refresh)
        return response


class WeChatLoginView(generics.GenericAPIView):
    """GET /api/auth/oauth/wechat/?redirect=<frontend_url>

    返回 JSON {authorize_url, configured};未配置时 authorize_url=None,前端降级。
    """
    permission_classes = [AllowAny]

    def get(self, request):
        oauth = WeChatOAuth()
        if not oauth.is_configured:
            return Response({
                'configured': False,
                'authorize_url': None,
                'message': '微信扫码登录尚未配置,敬请期待',
            })
        state = secrets.token_urlsafe(16)
        request.session['wechat_oauth_state'] = state
        redirect = request.query_params.get('redirect', 'https://fipai.cn/')
        request.session['wechat_oauth_redirect'] = redirect
        return Response({
            'configured': True,
            'authorize_url': oauth.build_authorize_url(state),
            'state': state,
        })


class WeChatOAuthCallbackView(generics.GenericAPIView):
    """GET /api/auth/oauth/wechat/callback/?code=...&state=...

    已绑定的 openid → 立即签 token 重定向回前端;未绑定 → 重定向带 wechat_openid
    让前端走「绑定/注册」流程。
    """
    permission_classes = [AllowAny]

    def get(self, request):
        code = request.query_params.get('code')
        state = request.query_params.get('state')
        expected = request.session.pop('wechat_oauth_state', None)
        redirect = request.session.pop('wechat_oauth_redirect', 'https://fipai.cn/')

        if not code or not expected or state != expected:
            return Response({'error': 'invalid state'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            token_info = WeChatOAuth().exchange_code(code)
        except WeChatOAuthError as e:
            return Response({'error': str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        openid = token_info.get('openid', '')
        unionid = token_info.get('unionid', '')

        profile = AccountProfile.objects.filter(
            Q(wechat_unionid=unionid) if unionid else Q(wechat_openid=openid)
        ).filter(
            Q(wechat_unionid=unionid) | Q(wechat_openid=openid)
        ).first() if (unionid or openid) else None

        if profile is None:
            params = urlencode({
                'wechat_openid': openid,
                'wechat_unionid': unionid or '',
                'next': redirect,
            })
            return HttpResponseRedirect(f"/login?from=wechat&{params}")

        user = profile.user
        from .jwt import issue_token_pair

        access, refresh = issue_token_pair(user)
        # 把 token 放到 URL fragment,前端用 useEffect 读取后调 useAuthStore().login()
        fragment = urlencode({'access': access, 'refresh': refresh or ''})
        return HttpResponseRedirect(f"{redirect}#{fragment}")
