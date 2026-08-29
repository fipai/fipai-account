"""
Tenant Management Views
"""
import secrets
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .eligibility import eligible_tenant_filters
from .models import Tenant
from .permissions import TenantObjectPermission
from .serializers import TenantSerializer, TenantCreateSerializer
from teams.models import TeamMember, Invitation
from teams.serializers import InvitationSerializer


class TenantViewSet(viewsets.ModelViewSet):
    """
    租户管理 API

    GET /api/tenants/ - 列出我的租户
    POST /api/tenants/ - 创建租户
    GET /api/tenants/{id}/ - 获取租户详情
    PUT /api/tenants/{id}/ - 更新租户
    DELETE /api/tenants/{id}/ - 软停用租户
    GET /api/tenants/{id}/members/ - 获取成员
    """
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated, TenantObjectPermission]

    def get_queryset(self):
        # 平台管理员仅在管理操作中可定位任意租户；读取仍按活跃成员隔离。
        if (
            self.action in {'update', 'partial_update', 'destroy'}
            and (self.request.user.is_staff or self.request.user.is_superuser)
        ):
            return Tenant.objects.all().select_related('owner')

        tenant_ids = TeamMember.objects.filter(
            user=self.request.user,
            status='active',
            **eligible_tenant_filters(),
        ).values_list('tenant_id', flat=True)
        return Tenant.objects.filter(
            id__in=tenant_ids,
            **eligible_tenant_filters(prefix=""),
        ).select_related('owner')

    def create(self, request, *args, **kwargs):
        serializer = TenantCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        tenant = serializer.save()
        return Response(
            TenantSerializer(tenant, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        """获取租户成员列表"""
        tenant = self.get_object()
        memberships = TeamMember.objects.filter(
            tenant=tenant,
            status='active',
        ).select_related('user')
        data = []
        for m in memberships:
            data.append({
                'user_id': m.user_id,
                'email': m.user.email if m.user else '',
                'name': m.user.first_name if m.user else '',
                'role': m.role,
                'product_permissions': m.product_permissions,
                'joined_at': m.joined_at,
            })
        return Response(data)

    def destroy(self, request, *args, **kwargs):
        """可恢复地停用租户，保留其成员和关联数据。"""
        tenant = self.get_object()
        tenant.status = 'cancelled'
        tenant.is_active = False
        tenant.save(update_fields=['status', 'is_active', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'])
    def invite(self, request, pk=None):
        """
        邀请成员: POST /api/tenants/{id}/invite/
        Body: { "email": "xxx", "role": "member" }
        """
        tenant = self.get_object()

        # 检查权限：只有 owner 或 admin 可以邀请
        try:
            membership = TeamMember.objects.get(
                tenant=tenant,
                user=request.user,
                status='active',
                role__in=['owner', 'admin']
            )
        except TeamMember.DoesNotExist:
            return Response({'error': '无权限邀请成员'}, status=status.HTTP_403_FORBIDDEN)

        email = request.data.get('email')
        phone = request.data.get('phone')
        role = request.data.get('role', 'member')

        valid_roles = {choice[0] for choice in TeamMember.ROLE_CHOICES}
        if role not in valid_roles:
            return Response({'error': '无效角色'}, status=status.HTTP_400_BAD_REQUEST)
        if role == 'owner' and membership.role != 'owner':
            return Response({'error': '管理员不能授予所有者角色'}, status=status.HTTP_403_FORBIDDEN)

        if not email and not phone:
            return Response({'error': 'email 或 phone 至少填写一项'}, status=status.HTTP_400_BAD_REQUEST)

        # 检查是否已是成员
        from django.contrib.auth import get_user_model
        User = get_user_model()
        existing_user = None

        if email:
            existing_user = User.objects.filter(email=email).first()
        elif phone:
            existing_user = User.objects.filter(username=phone).first()

        if existing_user and TeamMember.objects.filter(tenant=tenant, user=existing_user).exists():
            return Response({'error': '用户已是成员'}, status=status.HTTP_400_BAD_REQUEST)

        # 创建邀请 - 使用安全的随机码
        code = secrets.token_urlsafe(32)
        invitation = Invitation.objects.create(
            tenant=tenant,
            email=email,
            phone=phone,
            role=role,
            product_permissions={},
            invited_by=request.user,
            code=code,
            expires_at=timezone.now() + timezone.timedelta(days=7)
        )

        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], permission_classes=[AllowAny])
    def public(self, request, pk=None):
        """获取公开租户信息"""
        try:
            tenant = Tenant.objects.get(
                slug=pk,
                **eligible_tenant_filters(prefix=""),
            )
            return Response({
                'name': tenant.name,
                'logo': tenant.logo,
                'description': tenant.description,
            })
        except Tenant.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)
