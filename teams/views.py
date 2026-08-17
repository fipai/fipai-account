"""
Teams API Views
"""
import secrets
from django.utils import timezone
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from .models import TeamMember, Invitation
from .serializers import (
    TeamMemberSerializer,
    TeamMemberCreateSerializer,
    InvitationSerializer,
    InvitationCreateSerializer,
)


class TeamMemberViewSet(viewsets.ModelViewSet):
    """团队成员管理"""
    serializer_class = TeamMemberSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # 用户作为成员的所有租户
        return TeamMember.objects.filter(
            user=self.request.user,
            status='active'
        ).select_related('tenant')

    def create(self, request, *args, **kwargs):
        """添加团队成员"""
        serializer = TeamMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant_id = serializer.validated_data['tenant_id']
        user_email = serializer.validated_data.get('email')
        role = serializer.validated_data.get('role', 'member')
        product_permissions = serializer.validated_data.get('product_permissions', {})

        # 检查权限
        try:
            membership = TeamMember.objects.get(
                tenant_id=tenant_id,
                user=request.user,
                status='active',
                role__in=['owner', 'admin']
            )
        except TeamMember.DoesNotExist:
            return Response({'error': '无权限添加成员'}, status=status.HTTP_403_FORBIDDEN)

        # 查找用户
        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = User.objects.get(email=user_email)
        except User.DoesNotExist:
            return Response({'error': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 检查是否已是成员
        if TeamMember.objects.filter(tenant_id=tenant_id, user=user).exists():
            return Response({'error': '用户已是成员'}, status=status.HTTP_400_BAD_REQUEST)

        # 创建成员
        member = TeamMember.objects.create(
            tenant_id=tenant_id,
            user=user,
            role=role,
            product_permissions=product_permissions,
            invited_by=request.user
        )

        return Response(TeamMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['put'])
    def update_role(self, request, pk=None):
        """更新成员角色"""
        member = self.get_object()

        # 检查权限：只有 owner 或 admin 可以修改角色
        try:
            request_membership = TeamMember.objects.get(
                tenant=member.tenant,
                user=request.user,
                status='active',
                role__in=['owner', 'admin']
            )
        except TeamMember.DoesNotExist:
            return Response({'error': '无权限修改角色'}, status=status.HTTP_403_FORBIDDEN)

        # 成员不能自我提权为 owner
        if member.user == request.user and request.data.get('role') == 'owner':
            return Response({'error': '无法自我提升为所有者'}, status=status.HTTP_403_FORBIDDEN)

        # 只有 owner 可以修改 owner
        if member.role == 'owner' and request.data.get('role') != 'owner':
            owner_count = TeamMember.objects.filter(tenant=member.tenant, role='owner').count()
            if owner_count <= 1:
                return Response({'error': '至少需要保留一个所有者'}, status=status.HTTP_400_BAD_REQUEST)

        member.role = request.data.get('role', member.role)
        member.save()
        return Response(TeamMemberSerializer(member).data)

    @action(detail=True, methods=['put'])
    def update_permissions(self, request, pk=None):
        """更新成员产品权限"""
        member = self.get_object()

        # 检查权限
        if not member.is_admin and not request.user.is_superuser:
            return Response({'error': '无权限修改权限'}, status=status.HTTP_403_FORBIDDEN)

        product_permissions = request.data.get('product_permissions', {})
        member.product_permissions = product_permissions
        member.save()
        return Response(TeamMemberSerializer(member).data)

    @action(detail=True, methods=['post'])
    def remove(self, request, pk=None):
        """移除成员（软删除）"""
        member = self.get_object()

        if member.role == 'owner':
            return Response({'error': '无法移除所有者'}, status=status.HTTP_400_BAD_REQUEST)

        # 软删除：更新状态
        member.status = 'disabled'
        member.save(update_fields=['status'])
        return Response({'message': '成员已移除'})


class InvitationViewSet(viewsets.ModelViewSet):
    """邀请管理"""
    serializer_class = InvitationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Invitation.objects.filter(
            Q(invited_by=self.request.user) | Q(tenant__members__user=self.request.user)
        ).distinct().select_related('tenant', 'invited_by')

    def create(self, request, *args, **kwargs):
        """发送邀请"""
        serializer = InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant_id = serializer.validated_data['tenant_id']
        email = serializer.validated_data.get('email')
        phone = serializer.validated_data.get('phone')
        role = serializer.validated_data.get('role', 'member')
        product_permissions = serializer.validated_data.get('product_permissions', {})

        # 检查权限
        try:
            membership = TeamMember.objects.get(
                tenant_id=tenant_id,
                user=request.user,
                status='active',
                role__in=['owner', 'admin']
            )
        except TeamMember.DoesNotExist:
            return Response({'error': '无权限邀请成员'}, status=status.HTTP_403_FORBIDDEN)

        # 检查是否已是成员（通过 email 或 phone）
        from django.contrib.auth import get_user_model
        User = get_user_model()
        existing_user = None

        if email:
            existing_user = User.objects.filter(email=email).first()
        elif phone:
            existing_user = User.objects.filter(username=phone).first()

        if existing_user and TeamMember.objects.filter(tenant_id=tenant_id, user=existing_user).exists():
            return Response({'error': '用户已是成员'}, status=status.HTTP_400_BAD_REQUEST)

        # 创建邀请 - 使用安全的随机码
        code = secrets.token_urlsafe(32)
        invitation = Invitation.objects.create(
            tenant_id=tenant_id,
            email=email,
            phone=phone,
            role=role,
            product_permissions=product_permissions,
            invited_by=request.user,
            code=code,
            expires_at=timezone.now() + timezone.timedelta(days=7)
        )

        return Response(InvitationSerializer(invitation).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='accept')
    def accept_invitation(self, request):
        """
        接受邀请: POST /api/invitations/accept/
        Body: { "code": "xxx" }

        Fix: 使用 select_for_update 重新查询并锁定 invitation 记录，
        避免并发请求在 status 检查后、状态更新前的时间窗口内重复接受邀请。
        """
        code = request.data.get('code')
        if not code:
            return Response({'error': 'code is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            invitation = Invitation.objects.get(code=code, status='pending')
        except Invitation.DoesNotExist:
            return Response({'error': '邀请不存在或已失效'}, status=status.HTTP_404_NOT_FOUND)

        if invitation.is_expired:
            invitation.status = 'expired'
            invitation.save()
            return Response({'error': '邀请已过期'}, status=status.HTTP_400_BAD_REQUEST)

        # 检查用户是否已经是成员
        if TeamMember.objects.filter(tenant=invitation.tenant, user=request.user, status='active').exists():
            return Response({'error': '您已是该租户成员'}, status=status.HTTP_400_BAD_REQUEST)

        # 校验邀请人与用户信息匹配
        if invitation.email and invitation.email != request.user.email:
            return Response({'error': '邀请邮箱与您注册的邮箱不一致'}, status=status.HTTP_403_FORBIDDEN)
        if invitation.phone and invitation.phone != request.user.username:
            return Response({'error': '邀请手机号与您注册的手机号不一致'}, status=status.HTTP_403_FORBIDDEN)

        # 使用 select_for_update 重新查询并锁定记录，防止竞态条件
        from django.db import transaction
        with transaction.atomic():
            try:
                invitation = Invitation.objects.select_for_update().get(code=code)
            except Invitation.DoesNotExist:
                return Response({'error': '邀请不存在或已失效'}, status=status.HTTP_404_NOT_FOUND)

            # 重新检查状态
            if invitation.status != 'pending':
                return Response({'error': '邀请状态已变更，请刷新后重试'}, status=status.HTTP_400_BAD_REQUEST)

            # 创建成员
            member = TeamMember.objects.create(
                tenant=invitation.tenant,
                user=request.user,
                role=invitation.role,
                product_permissions=invitation.product_permissions,
                invited_by=invitation.invited_by
            )

            # 更新邀请状态
            invitation.status = 'accepted'
            invitation.accepted_at = timezone.now()
            invitation.save()

        return Response({
            'message': '成功加入租户',
            'tenant_id': invitation.tenant_id,
            'tenant_name': invitation.tenant.name,
            'role': member.role,
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """取消邀请"""
        invitation = self.get_object()

        if invitation.invited_by != request.user:
            return Response({'error': '无权限取消邀请'}, status=status.HTTP_403_FORBIDDEN)

        invitation.status = 'rejected'
        invitation.save()
        return Response({'message': '邀请已取消'})
