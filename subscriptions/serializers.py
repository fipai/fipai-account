"""
Subscriptions Serializers
"""
from rest_framework import serializers
from .models import SubscriptionPlan, Subscription


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='get_product_display', read_only=True)
    tier_display = serializers.CharField(source='get_tier_display', read_only=True)
    period_display = serializers.CharField(source='get_period_display', read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = [
            'id', 'product', 'product_name', 'tier', 'tier_display',
            'period', 'period_display', 'name', 'description',
            'price', 'max_users', 'max_api_calls',
            'max_storage_gb', 'features'
        ]


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)
    plan_detail = SubscriptionPlanSerializer(source='plan', read_only=True)
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Subscription
        fields = [
            'id', 'user', 'plan', 'plan_detail', 'status',
            'start_date', 'end_date', 'auto_renew', 'tenant',
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['user', 'status', 'start_date', 'end_date']


class SubscriptionCreateSerializer(serializers.Serializer):
    plan_id = serializers.IntegerField()
    auto_renew = serializers.BooleanField(default=True)
