"""
Audit Log Views
"""
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q

from .models import AuditLog
from .serializers import AuditLogSerializer
from teams.models import TeamMember


class AuditLogListView(generics.ListAPIView):
    """
    查询审计日志列表: GET /api/audit/logs/
    支持分页和过滤
    """
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # 获取用户所在的租户
        memberships = TeamMember.objects.filter(user=user, status='active')
        tenant_ids = memberships.values_list('tenant_id', flat=True)

        queryset = AuditLog.objects.filter(
            Q(tenant_id__in=tenant_ids) | Q(user=user)
        ).distinct().order_by('-created_at')

        # 过滤条件
        action = self.request.query_params.get('action')
        if action:
            queryset = queryset.filter(action=action)

        resource_type = self.request.query_params.get('resource_type')
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)

        user_id = self.request.query_params.get('user_id')
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        tenant_id = self.request.query_params.get('tenant_id')
        if tenant_id:
            queryset = queryset.filter(tenant_id=tenant_id)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # 分页
        page_size = request.query_params.get('page_size', 20)
        try:
            page_size = min(int(page_size), 100)
        except ValueError:
            page_size = 20

        page = request.query_params.get('page', 1)
        try:
            page = int(page)
        except ValueError:
            page = 1

        start = (page - 1) * page_size
        end = start + page_size

        logs = queryset[start:end]
        total = queryset.count()

        serializer = self.get_serializer(logs, many=True)
        return Response({
            'total': total,
            'page': page,
            'page_size': page_size,
            'results': serializer.data,
        })


class AuditLogDetailView(generics.RetrieveAPIView):
    """
    查询审计日志详情: GET /api/audit/logs/{id}/
    """
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    queryset = AuditLog.objects.all()

    def get_queryset(self):
        user = self.request.user
        memberships = TeamMember.objects.filter(user=user, status='active')
        tenant_ids = memberships.values_list('tenant_id', flat=True)

        return AuditLog.objects.filter(
            Q(tenant_id__in=tenant_ids) | Q(user=user)
        ).distinct()
