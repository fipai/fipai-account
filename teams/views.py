"""
Teams API Views
"""
import secrets
from django.utils import timezone
from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from tenants.eligibility import eligible_tenant_filters, is_tenant_eligible
from .models import TeamMember, Invitation
from .serializers import (
    TeamMemberSerializer,
    TeamMemberCreateSerializer,
    InvitationSerializer,
    InvitationCreateSerializer,
)


class TeamMemberViewSet(viewsets.ModelViewSet):
    """团队成员管理。敏感变更只允许通过显式 action。"""
    serializer_class = TeamMemberSerializer
    permission_classes = [IsAuthenticated]
    role_rank = {'viewer': 0, 'member': 1, 'admin': 2, 'owner': 3}

    @staticmethod
    def _is_platform_admin(user):
        return bool(user.is_staff or user.is_superuser)

    def _requester_membership(self, request, tenant_id):
        """每次写操作都从数据库重新确认请求者在目标租户的有效管理员身份。"""
        if self._is_platform_admin(request.user):
            return None
        return TeamMember.objects.filter(
            tenant_id=tenant_id,
            user=request.user,
            status='active',
            role__in=['owner', 'admin'],
            **eligible_tenant_filters(),
        ).first()

    def _has_management_access(self, request, requester_membership):
        return self._is_platform_admin(request.user) or requester_membership is not None

    def get_queryset(self):
        queryset = TeamMember.objects.select_related('tenant', 'user')
        if self._is_platform_admin(self.request.user):
            return queryset

        tenant_ids = TeamMember.objects.filter(
            user=self.request.user,
            status='active',
            **eligible_tenant_filters(),
        ).values_list('tenant_id', flat=True)
        return queryset.filter(
            tenant_id__in=tenant_ids,
            **eligible_tenant_filters(),
        )

    def list(self, request, *args, **kwargs):
        if not self._is_platform_admin(request.user):
            has_historical_membership = TeamMember.objects.filter(
                user=request.user,
                status='active',
            ).exists()
            has_eligible_membership = TeamMember.objects.filter(
                user=request.user,
                status='active',
                **eligible_tenant_filters(),
            ).exists()
            if has_historical_membership and not has_eligible_membership:
                return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        return super().list(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def create(self, request, *args, **kwargs):
        """添加团队成员"""
        serializer = TeamMemberCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tenant_id = serializer.validated_data['tenant_id']
        user_email = serializer.validated_data.get('email')
        role = serializer.validated_data.get('role', 'member')
        product_permissions = serializer.validated_data.get('product_permissions', {})

        try:
            requester_membership = TeamMember.objects.get(
                tenant_id=tenant_id,
                user=request.user,
                status='active',
                role__in=['owner', 'admin'],
                **eligible_tenant_filters(),
            )
        except TeamMember.DoesNotExist:
            return Response({'error': '无权限添加成员'}, status=status.HTTP_403_FORBIDDEN)

        if role == 'owner' and requester_membership.role != 'owner':
            return Response({'error': '管理员不能授予所有者角色'}, status=status.HTTP_403_FORBIDDEN)

        from django.contrib.auth import get_user_model
        User = get_user_model()

        try:
            user = User.objects.get(email=user_email)
        except User.DoesNotExist:
            return Response({'error': '用户不存在'}, status=status.HTTP_404_NOT_FOUND)

        if TeamMember.objects.filter(tenant_id=tenant_id, user=user).exists():
            return Response({'error': '用户已是成员'}, status=status.HTTP_400_BAD_REQUEST)

        member = TeamMember.objects.create(
            tenant_id=tenant_id,
            user=user,
            role=role,
            product_permissions=product_permissions,
            invited_by=request.user,
        )
        return Response(TeamMemberSerializer(member).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['put'])
    def update_role(self, request, pk=None):
        """更新成员角色，并保护 owner 边界。"""
        visible_member = self.get_object()
        new_role = request.data.get('role')
        if new_role not in self.role_rank:
            return Response({'error': '无效角色'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            member = TeamMember.objects.select_for_update().get(pk=visible_member.pk)
            requester_membership = self._requester_membership(request, member.tenant_id)
            if not self._has_management_access(request, requester_membership):
                return Response({'error': '无权限修改角色'}, status=status.HTTP_403_FORBIDDEN)

            if (
                requester_membership is not None
                and requester_membership.role == 'admin'
                and member.role == 'owner'
            ):
                return Response({'error': '管理员不能修改所有者'}, status=status.HTTP_403_FORBIDDEN)

            if (
                member.user_id == request.user.id
                and self.role_rank[new_role] > self.role_rank[member.role]
            ):
                return Response({'error': '无法自我提升权限'}, status=status.HTTP_403_FORBIDDEN)

            if (
                requester_membership is not None
                and requester_membership.role == 'admin'
                and new_role == 'owner'
            ):
                return Response({'error': '管理员不能授予所有者角色'}, status=status.HTTP_403_FORBIDDEN)

            if member.role == 'owner' and new_role != 'owner' and member.status == 'active':
                active_owner_count = TeamMember.objects.select_for_update().filter(
                    tenant_id=member.tenant_id,
                    role='owner',
                    status='active',
                ).count()
                if active_owner_count <= 1:
                    return Response({'error': '至少需要保留一个所有者'}, status=status.HTTP_400_BAD_REQUEST)

            member.role = new_role
            member.save(update_fields=['role'])

        return Response(TeamMemberSerializer(member).data)

    @action(detail=True, methods=['put'])
    def update_permissions(self, request, pk=None):
        """更新成员产品权限。请求者权限始终按目标租户重新查询。"""
        visible_member = self.get_object()

        with transaction.atomic():
            member = TeamMember.objects.select_for_update().get(pk=visible_member.pk)
            requester_membership = self._requester_membership(request, member.tenant_id)
            if not self._has_management_access(request, requester_membership):
                return Response({'error': '无权限修改权限'}, status=status.HTTP_403_FORBIDDEN)
            if (
                requester_membership is not None
                and requester_membership.role == 'admin'
                and member.role == 'owner'
            ):
                return Response({'error': '管理员不能修改所有者权限'}, status=status.HTTP_403_FORBIDDEN)
            if member.user_id == request.user.id:
                return Response({'error': '无法修改自己的产品权限'}, status=status.HTTP_403_FORBIDDEN)

            product_permissions = request.data.get('product_permissions')
            if not isinstance(product_permissions, dict):
                return Response({'error': 'product_permissions 必须是对象'}, status=status.HTTP_400_BAD_REQUEST)
            member.product_permissions = product_permissions
            member.save(update_fields=['product_permissions'])

        return Response(TeamMemberSerializer(member).data)

    @action(detail=True, methods=['post'])
    def remove(self, request, pk=None):
        """移除成员（软删除）；owner 必须先通过角色 action 完成安全交接。"""
        visible_member = self.get_object()

        with transaction.atomic():
            member = TeamMember.objects.select_for_update().get(pk=visible_member.pk)
            requester_membership = self._requester_membership(request, member.tenant_id)
            if not self._has_management_access(request, requester_membership):
                return Response({'error': '无权限移除成员'}, status=status.HTTP_403_FORBIDDEN)
            if member.role == 'owner':
                return Response({'error': '无法移除所有者'}, status=status.HTTP_400_BAD_REQUEST)

            member.status = 'disabled'
            member.save(update_fields=['status'])

        return Response({'message': '成员已移除'})


class InvitationViewSet(viewsets.ModelViewSet):
    """邀请管理。邀请状态只能通过 accept/cancel 显式 action 改变。"""
    serializer_class = InvitationSerializer
    permission_classes = [IsAuthenticated]

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method)

    def get_queryset(self):
        queryset = Invitation.objects.select_related('tenant', 'invited_by')
        if self.request.user.is_staff or self.request.user.is_superuser:
            return queryset
        return queryset.filter(
            tenant__members__user=self.request.user,
            tenant__members__status='active',
            **eligible_tenant_filters(),
        ).distinct()

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
                role__in=['owner', 'admin'],
                **eligible_tenant_filters(),
            )
        except TeamMember.DoesNotExist:
            return Response({'error': '无权限邀请成员'}, status=status.HTTP_403_FORBIDDEN)

        if role == 'owner' and membership.role != 'owner':
            return Response({'error': '管理员不能授予所有者角色'}, status=status.HTTP_403_FORBIDDEN)

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
        """接受仍由有效 owner/admin 背书的有效租户邀请。"""
        code = request.data.get('code')
        if not code:
            return Response({'error': 'code is required'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            try:
                invitation = (
                    Invitation.objects.select_for_update()
                    .select_related('tenant', 'invited_by')
                    .get(code=code)
                )
            except Invitation.DoesNotExist:
                return Response({'error': '邀请不存在或已失效'}, status=status.HTTP_404_NOT_FOUND)

            if invitation.status != 'pending':
                return Response({'error': '邀请状态已变更，请刷新后重试'}, status=status.HTTP_400_BAD_REQUEST)
            if not is_tenant_eligible(invitation.tenant):
                return Response({'error': '租户不可用'}, status=status.HTTP_400_BAD_REQUEST)
            if not TeamMember.objects.select_for_update().filter(
                tenant=invitation.tenant,
                user=invitation.invited_by,
                status='active',
                role__in=['owner', 'admin'],
                **eligible_tenant_filters(),
            ).exists():
                return Response({'error': '邀请人已无有效管理权限'}, status=status.HTTP_403_FORBIDDEN)
            if invitation.is_expired:
                invitation.status = 'expired'
                invitation.save(update_fields=['status'])
                return Response({'error': '邀请已过期'}, status=status.HTTP_400_BAD_REQUEST)
            if TeamMember.objects.filter(
                tenant=invitation.tenant,
                user=request.user,
            ).exists():
                return Response({'error': '您已是该租户成员'}, status=status.HTTP_400_BAD_REQUEST)
            if invitation.email and invitation.email != request.user.email:
                return Response({'error': '邀请邮箱与您注册的邮箱不一致'}, status=status.HTTP_403_FORBIDDEN)
            if invitation.phone and invitation.phone != request.user.username:
                return Response({'error': '邀请手机号与您注册的手机号不一致'}, status=status.HTTP_403_FORBIDDEN)

            member = TeamMember.objects.create(
                tenant=invitation.tenant,
                user=request.user,
                role=invitation.role,
                product_permissions=invitation.product_permissions,
                invited_by=invitation.invited_by,
            )
            invitation.status = 'accepted'
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=['status', 'accepted_at'])

        return Response({
            'message': '成功加入租户',
            'tenant_id': invitation.tenant_id,
            'tenant_name': invitation.tenant.name,
            'role': member.role,
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """原子取消 pending 邀请，并复核当前管理权限。"""
        visible_invitation = self.get_object()

        with transaction.atomic():
            invitation = (
                Invitation.objects.select_for_update()
                .select_related('tenant', 'invited_by')
                .get(pk=visible_invitation.pk)
            )
            if invitation.status != 'pending':
                return Response({'error': '仅可取消待接受邀请'}, status=status.HTTP_400_BAD_REQUEST)
            if not is_tenant_eligible(invitation.tenant):
                return Response({'error': '租户不可用'}, status=status.HTTP_400_BAD_REQUEST)

            is_platform_admin = request.user.is_staff or request.user.is_superuser
            inviter_still_manages = (
                invitation.invited_by_id == request.user.id
                and TeamMember.objects.select_for_update().filter(
                    tenant=invitation.tenant,
                    user=request.user,
                    status='active',
                    role__in=['owner', 'admin'],
                    **eligible_tenant_filters(),
                ).exists()
            )
            if not (is_platform_admin or inviter_still_manages):
                return Response({'error': '无权限取消邀请'}, status=status.HTTP_403_FORBIDDEN)

            invitation.status = 'rejected'
            invitation.save(update_fields=['status'])

        return Response({'message': '邀请已取消'})
