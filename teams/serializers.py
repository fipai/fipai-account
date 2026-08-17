"""
Teams Serializers
"""
from rest_framework import serializers
from .models import TeamMember, Invitation


class TeamMemberSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)
    user_name = serializers.CharField(source='user.first_name', read_only=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)

    class Meta:
        model = TeamMember
        fields = [
            'id', 'tenant', 'user', 'user_email', 'user_name',
            'role', 'role_display', 'status', 'product_permissions',
            'joined_at'
        ]
        read_only_fields = ['tenant', 'user', 'joined_at']


class TeamMemberCreateSerializer(serializers.Serializer):
    tenant_id = serializers.IntegerField()
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=TeamMember.ROLE_CHOICES, default='member')
    product_permissions = serializers.JSONField(required=False, default=dict)


class InvitationSerializer(serializers.ModelSerializer):
    tenant_name = serializers.CharField(source='tenant.name', read_only=True)
    invited_by_email = serializers.EmailField(source='invited_by.email', read_only=True)
    invited_by_name = serializers.CharField(source='invited_by.name', read_only=True, allow_null=True)
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    is_expired = serializers.BooleanField(read_only=True)

    class Meta:
        model = Invitation
        fields = [
            'id', 'tenant', 'tenant_name', 'email', 'phone', 'role', 'role_display',
            'invited_by', 'invited_by_email', 'invited_by_name', 'code', 'status', 'status_display',
            'product_permissions', 'expires_at', 'is_expired', 'created_at', 'accepted_at'
        ]
        read_only_fields = ['invited_by', 'code', 'status']


class InvitationCreateSerializer(serializers.Serializer):
    tenant_id = serializers.IntegerField()
    email = serializers.EmailField(required=False, allow_null=True)
    phone = serializers.CharField(max_length=20, required=False, allow_null=True)
    role = serializers.ChoiceField(choices=TeamMember.ROLE_CHOICES, default='member')
    product_permissions = serializers.JSONField(required=False, default=dict)
    expires_in_days = serializers.IntegerField(default=7)

    def validate(self, data):
        if not data.get('email') and not data.get('phone'):
            raise serializers.ValidationError('email 或 phone 至少填写一项')
        return data
