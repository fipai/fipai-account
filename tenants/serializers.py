"""
Tenant Serializers
"""
from rest_framework import serializers
from .models import Tenant


class TenantSerializer(serializers.ModelSerializer):
    owner_name = serializers.CharField(source='owner.name', read_only=True)
    owner_email = serializers.CharField(source='owner.email', read_only=True)

    class Meta:
        model = Tenant
        fields = [
            'id', 'name', 'slug', 'domain', 'owner', 'owner_name', 'owner_email',
            'status', 'is_active', 'current_plan', 'logo', 'description',
            'max_users', 'max_api_calls', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']


class TenantCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ['name', 'slug', 'description', 'logo']

    def create(self, validated_data):
        # 创建租户并将当前用户设为所有者
        validated_data['owner'] = self.context['request'].user
        tenant = Tenant.objects.create(**validated_data)
        # 自动创建 owner 成员关系
        from teams.models import TeamMember
        TeamMember.objects.create(
            tenant=tenant,
            user=self.context['request'].user,
            role='owner',
            status='active',
        )
        return tenant
