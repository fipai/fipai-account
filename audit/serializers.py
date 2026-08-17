"""
Audit Log Serializers
"""
from rest_framework import serializers
from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """审计日志序列化器"""
    username = serializers.CharField(source='user.username', read_only=True, default='')
    tenant_name = serializers.CharField(source='tenant.name', read_only=True, default='')
    action_display = serializers.CharField(source='get_action_display', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'tenant', 'tenant_name', 'user', 'username',
            'action', 'action_display', 'resource_type', 'resource_id',
            'details', 'ip_address', 'user_agent', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']
