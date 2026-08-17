"""
Tenant Management Views
"""
import secrets
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response

from .models import Tenant
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
    DELETE /api/tenants/{id}/ - 删除租户
    GET /api/tenants/{id}/members/ - 获取成员
    """
    serializer_class = TenantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 返回用户所属的租户
        memberships = TeamMember.objects.filter(user=self.request.user, status='active')
        tenant_ids = memberships.values_list('tenant_id', flat=True)
        return Tenant.objects.filter(id__in=tenant_ids)

    def get_permissions(self):
        if self.action == 'list' or self.action == 'retrieve':
            return [IsAuthenticated()]
        return [IsAuthenticated()]

    def create(self, request, *args, **kwargs):
        serializer = TenantCreateSerializer(data=request.data, context=self.get_serializer_context())
        serializer.is_valid(raise_exception=True)
        tenant = serializer.save()
        return Response(TenantSerializer(tenant).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def members(self, request, pk=None):
        """获取租户成员列表"""
        tenant = self.get_object()
        memberships = TeamMember.objects.filter(tenant=tenant, status='active')
        data = []
        for m in memberships:
            data.append({
                'user_id': m.user_id,
                'email': m.user.email if m.user else '',
                'name': m.user.first_name if m.user else '',
                'role': m.role,
                'product_permissions': m.product_permissions,
                'joined_at': m.created_at,
            })
        return Response(data)

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
            tenant = Tenant.objects.get(slug=pk, is_active=True)
            return Response({
                'name': tenant.name,
                'logo': tenant.logo,
                'description': tenant.description,
            })
        except Tenant.DoesNotExist:
            return Response({'error': 'Tenant not found'}, status=status.HTTP_404_NOT_FOUND)
