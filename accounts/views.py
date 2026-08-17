from typing import Optional

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.contrib.auth import get_user_model, authenticate, login
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone

from .serializers import (
    RegisterSerializer, UserSerializer,
    SendCodeSerializer, RegisterPhoneSerializer, LoginPhoneSerializer,
)
from .models import SMSCode, TwoFactorAuth, AccountDeletionRequest
from .sms import generate_code, get_sms_client, SMS_CODE_EXPIRE_MINUTES, SMS_DAILY_LIMIT
from .authentication import CookieOrHeaderJWTAuthentication
import accounts.totp_service as totp_service
from subscriptions.models import Subscription
from payments.models import PaymentTransaction
from django.contrib.auth.hashers import check_password

User = get_user_model()

SSO_ACCESS_COOKIE_NAME = "fip_access_token"
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


def add_custom_token_claims(refresh_token, user):
    """
    为 JWT token 添加自定义 claims
    - tenant_id: 用户所属租户 ID
    - product_scopes: 用户可访问的产品列表
    - roles: 用户在租户中的角色
    """
    # 设置在 refresh_token 上（不是 access_token）
    # RefreshToken.access_token 会从 refresh_token.token 复制 claims
    refresh_token['tenant_id'] = None
    refresh_token['product_scopes'] = []
    refresh_token['roles'] = []

    from teams.models import TeamMember
    membership = TeamMember.objects.filter(
        user=user,
        status='active'
    ).select_related('tenant').first()

    if membership:
        refresh_token['tenant_id'] = membership.tenant_id
        refresh_token['roles'] = [membership.role]

        # 从订阅获取产品权限范围
        active_subs = Subscription.objects.filter(
            user=user,
            status='active',
            end_date__gt=timezone.now()
        ).select_related('plan')

        product_scopes = []
        for sub in active_subs:
            if sub.plan:
                product_scopes.append(sub.plan.product)

        refresh_token['product_scopes'] = list(set(product_scopes))

    return refresh_token


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
        refresh = RefreshToken.for_user(user)
        refresh = add_custom_token_claims(refresh, user)

        response = Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }, status=status.HTTP_201_CREATED)
        _set_sso_cookies(request, response, str(refresh.access_token), str(refresh))
        return response


class LoginPhoneView(generics.GenericAPIView):
    """
    手机号登录: POST /api/auth/login/phone/
    Body: { "phone": "13800000000", "code": "123456" }
    """
    permission_classes = [AllowAny]
    serializer_class = LoginPhoneSerializer

    def post(self, request):
        serializer = LoginPhoneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        phone = serializer.validated_data['phone']
        code = serializer.validated_data['code']

        # 验证验证码
        valid_code = SMSCode.objects.filter(
            phone=phone,
            code=code,
            purpose='login',
            is_used=False,
            expires_at__gt=timezone.now(),
        ).order_by('-created_at').first()

        if not valid_code:
            return Response({'error': '验证码无效或已过期'}, status=status.HTTP_400_BAD_REQUEST)

        # 查找用户
        try:
            user = User.objects.get(username=phone)
        except User.DoesNotExist:
            return Response({'error': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

        if not user.is_active:
            return Response({'error': '账号已被禁用'}, status=status.HTTP_403_FORBIDDEN)

        # 标记验证码已使用
        valid_code.is_used = True
        valid_code.save()

        # 生成 JWT
        refresh = RefreshToken.for_user(user)
        refresh = add_custom_token_claims(refresh, user)

        response = Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })
        _set_sso_cookies(request, response, str(refresh.access_token), str(refresh))
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
class LoginView(TokenObtainPairView):
    """
    登录（密码）: POST /api/auth/login/
    username 可以是手机号或邮箱
    """
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == 200:
            username = request.data.get('username')
            password = request.data.get('password')
            user = authenticate(username=username, password=password)
            if user:
                login(request, user)
                request.session.cycle_key()
            try:
                access = response.data.get("access")
                refresh = response.data.get("refresh")
                _set_sso_cookies(request, response, access, refresh)
            except Exception:
                pass

        return response


# =============================================================================
# 用户信息
# =============================================================================

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

    def post(self, request):
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

        return Response({'detail': '密码修改成功'})


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

        # 保存到数据库（secret 和 backup_codes 都要哈希存储）
        tfa.secret = secret
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
    """
    验证 2FA 代码: POST /api/auth/2fa/verify/
    用于启用时验证和登录时二次认证
    """
    permission_classes = [AllowAny]  # 登录时用户未认证

    def post(self, request):
        # 支持两种模式：启用验证（需认证）和 登录验证（未认证）
        user = request.user if request.user.is_authenticated else None

        code = request.data.get('code')
        password = request.data.get('password')  # 用于启用 2FA 时的密码验证

        if not code:
            return Response({'error': '请提供验证码'}, status=status.HTTP_400_BAD_REQUEST)

        if user:
            # 已认证用户 - 启用 2FA 验证
            tfa = TwoFactorAuth.objects.filter(user=user, enabled=False).first()
            if not tfa or not tfa.secret:
                return Response({'error': '请先设置 2FA'}, status=status.HTTP_400_BAD_REQUEST)

            # 验证 TOTP 代码
            if totp_service.verify_totp(tfa.secret, code):
                tfa.enabled = True
                tfa.save()
                return Response({'ok': True, 'message': '2FA 启用成功'})

            return Response({'error': '验证码无效'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # 未认证用户 - 登录时 2FA 验证（通过 user_id 或 session）
            user_id = request.data.get('user_id')
            if not user_id:
                return Response({'error': '需要用户标识'}, status=status.HTTP_400_BAD_REQUEST)

            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response({'error': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

            tfa = TwoFactorAuth.objects.filter(user=user, enabled=True).first()
            if not tfa:
                return Response({'error': '该用户未启用 2FA'}, status=status.HTTP_400_BAD_REQUEST)

            # 验证 TOTP 代码
            if totp_service.verify_totp(tfa.secret, code):
                return Response({'ok': True, 'verified': True})

            # 验证备份码
            is_backup, index = totp_service.verify_backup_code(tfa.backup_codes, code)
            if is_backup:
                # 使用备份码后将其移除
                tfa.backup_codes = totp_service.remove_used_backup_code(tfa.backup_codes, index)
                tfa.save()
                return Response({'ok': True, 'verified': True, 'used_backup': True})

            return Response({'error': '验证码无效'}, status=status.HTTP_400_BAD_REQUEST)


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

        return Response({'ok': True, 'message': '2FA 已禁用'})


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
