from django.contrib.auth import get_user_model
from rest_framework import serializers

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """当前用户信息（/api/auth/me/）"""

    # 额外字段
    is_tenant_admin = serializers.SerializerMethodField()
    tenant_id = serializers.SerializerMethodField()
    tenant_name = serializers.SerializerMethodField()
    subscriptions = serializers.SerializerMethodField()
    phone = serializers.CharField(source='username', read_only=True)
    name = serializers.CharField(source='first_name', read_only=True)
    display_name = serializers.SerializerMethodField()
    avatar_url = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'username', 'email', 'first_name', 'phone', 'name',
            'display_name', 'avatar_url',
            'date_joined', 'is_staff', 'is_active',
            'is_tenant_admin', 'tenant_id', 'tenant_name',
            'subscriptions'
        )
        read_only_fields = fields

    def get_is_tenant_admin(self, obj):
        """是否是某个租户的管理员"""
        from teams.models import TeamMember
        return TeamMember.objects.filter(
            user=obj, role__in=['owner', 'admin'], status='active'
        ).exists()

    def get_tenant_id(self, obj):
        """获取主租户 ID"""
        from teams.models import TeamMember
        membership = TeamMember.objects.filter(user=obj, status='active').first()
        return membership.tenant_id if membership else None

    def get_tenant_name(self, obj):
        """获取主租户名称"""
        from teams.models import TeamMember
        membership = TeamMember.objects.filter(user=obj, status='active').first()
        return membership.tenant.name if membership else None

    def get_subscriptions(self, obj):
        """获取用户的订阅信息"""
        from subscriptions.models import Subscription
        from subscriptions.serializers import SubscriptionSerializer
        subs = Subscription.objects.filter(user=obj, status='active')
        return SubscriptionSerializer(subs, many=True).data

    def get_display_name(self, obj):
        """从 AccountProfile 拉显示名（Phase 9 字段）"""
        profile = getattr(obj, 'profile', None)
        if profile is None:
            return None
        return profile.display_name or None

    def get_avatar_url(self, obj):
        """从 AccountProfile 拉头像 URL（Phase 9 字段）"""
        profile = getattr(obj, 'profile', None)
        if profile is None:
            return None
        return profile.avatar_url or None


class RegisterSerializer(serializers.ModelSerializer):
    """注册：username, email, password, name"""
    password = serializers.CharField(write_only=True, min_length=8, style={'input_type': 'password'})
    name = serializers.CharField(required=False, allow_blank=True, default='')

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'name')

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError('该用户名已被使用。')
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('该邮箱已被注册。')
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('name', ''),
        )
        return user


class SendCodeSerializer(serializers.Serializer):
    """发送验证码请求"""
    phone = serializers.CharField(max_length=20)
    purpose = serializers.ChoiceField(choices=['register', 'login'])

    def validate_phone(self, value):
        import re
        if not re.match(r'^1[3-9]\d{9}$', value):
            raise serializers.ValidationError('手机号格式不正确')
        return value


class RegisterPhoneSerializer(serializers.Serializer):
    """手机号注册"""
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)
    password = serializers.CharField(min_length=8, write_only=True)

    def validate_phone(self, value):
        import re
        if not re.match(r'^1[3-9]\d{9}$', value):
            raise serializers.ValidationError('手机号格式不正确')
        return value


class LoginPhoneSerializer(serializers.Serializer):
    """手机号登录"""
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6)

    def validate_phone(self, value):
        import re
        if not re.match(r'^1[3-9]\d{9}$', value):
            raise serializers.ValidationError('手机号格式不正确')
        return value


class TenantSwitchSerializer(serializers.Serializer):
    """Validate a requested tenant context without querying tenant existence."""

    tenant_id = serializers.IntegerField(min_value=1)


# =============================================================================
# Phase 9 — 个人/企业注册 + 邮箱密码登录
# =============================================================================

from django.core.validators import RegexValidator


class RegisterPersonalSerializer(serializers.Serializer):
    """POST /api/auth/register/personal/"""

    name = serializers.CharField(max_length=64)
    phone = serializers.CharField(
        required=False, allow_blank=True, max_length=20,
        validators=[RegexValidator(r'^1[3-9]\d{9}$', message='手机号格式不正确')],
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    code = serializers.CharField(max_length=6, min_length=6)
    password = serializers.CharField(min_length=8, max_length=64, write_only=True)
    tos_accepted = serializers.BooleanField()

    def validate(self, attrs):
        if not attrs.get('tos_accepted'):
            raise serializers.ValidationError({'tos_accepted': '必须同意用户协议和隐私政策'})
        phone = attrs.get('phone', '')
        email = attrs.get('email', '')
        if not phone and not email:
            raise serializers.ValidationError('手机号和邮箱至少填一个')
        if phone and email:
            raise serializers.ValidationError('手机号和邮箱只能填一个')
        return attrs


class RegisterEnterpriseSerializer(RegisterPersonalSerializer):
    """POST /api/auth/register/enterprise/"""

    company_name = serializers.CharField(max_length=128)
    uscc = serializers.CharField(
        max_length=32,
        validators=[RegexValidator(r'^[0-9A-Z]{18}$', message='统一社会信用代码为18位字母数字')],
    )
    scale = serializers.CharField(max_length=16)
    industry = serializers.CharField(max_length=64)
    legal_representative = serializers.CharField(
        max_length=64, required=False, allow_blank=True, default='',
    )

    def validate_scale(self, value):
        from tenants.models import Tenant
        valid = {k for k, _ in Tenant.SCALE_CHOICES}
        if value not in valid:
            raise serializers.ValidationError(f'企业规模必须是 {sorted(valid)} 之一')
        return value


class LoginEmailSerializer(serializers.Serializer):
    """POST /api/auth/login/email/"""

    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class SendEmailCodeSerializer(serializers.Serializer):
    """POST /api/auth/send-email-code/"""

    email = serializers.EmailField()
    purpose = serializers.ChoiceField(choices=['register', 'login'], default='register')
