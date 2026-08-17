"""
Custom JWT Token Serializer with additional claims
"""
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """自定义 JWT Payload，添加 tenant_id, product_scopes, roles"""

    def get_token(self, user):
        token = super().get_token(user)

        # 添加自定义 claims
        # 设置在 token 上（RefreshToken），不是 access_token
        # RefreshToken.access_token 会自动复制这些 claims 到 access token
        token['tenant_id'] = None
        token['product_scopes'] = []
        token['roles'] = []

        # 从数据库查询用户的租户和产品权限
        from teams.models import TeamMember
        membership = TeamMember.objects.filter(
            user=user,
            status='active'
        ).select_related('tenant').first()

        if membership:
            token['tenant_id'] = membership.tenant_id
            token['roles'] = [membership.role]

            # 从订阅获取产品权限范围
            from subscriptions.models import Subscription
            from django.utils import timezone

            active_subs = Subscription.objects.filter(
                user=user,
                status='active',
                end_date__gt=timezone.now()
            ).select_related('plan')

            product_scopes = []
            for sub in active_subs:
                if sub.plan:
                    product_scopes.append(sub.plan.product)

            # 去重
            token['product_scopes'] = list(set(product_scopes))

        return token


class CustomTokenObtainPairView(TokenObtainPairView):
    """使用自定义 serializer 的 token view"""
    serializer_class = CustomTokenObtainPairSerializer
