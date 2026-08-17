"""
Subscriptions API Views
"""
from django.utils import timezone
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny

from .models import SubscriptionPlan, Subscription
from .serializers import (
    SubscriptionPlanSerializer,
    SubscriptionSerializer,
    SubscriptionCreateSerializer,
)


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    """套餐列表"""
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    permission_classes = [AllowAny]

    def list(self, request, *args, **kwargs):
        # 按产品分组返回
        plans = self.get_queryset()
        data = {}
        for plan in plans:
            product = plan.product
            if product not in data:
                data[product] = {
                    'product': product,
                    'product_name': plan.get_product_display(),
                    'plans': []
                }
            data[product]['plans'].append(SubscriptionPlanSerializer(plan).data)
        return Response(list(data.values()))


class SubscriptionViewSet(viewsets.ModelViewSet):
    """用户订阅管理"""
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Subscription.objects.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        """创建订阅"""
        serializer = SubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plan_id = serializer.validated_data['plan_id']
        try:
            plan = SubscriptionPlan.objects.get(id=plan_id, is_active=True)
        except SubscriptionPlan.DoesNotExist:
            return Response({'error': '套餐不存在'}, status=status.HTTP_404_NOT_FOUND)

        # 检查是否已有相同产品的活跃订阅
        existing = Subscription.objects.filter(
            user=request.user,
            plan__product=plan.product,
            status='active',
            end_date__gt=timezone.now()
        ).first()

        if existing:
            return Response(
                {'error': f'您已有 {plan.get_product_display()} 的活跃订阅'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 创建待支付订阅
        subscription = Subscription.objects.create(
            user=request.user,
            plan=plan,
            status='pending'
        )

        return Response(SubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """
        开通订阅并创建租户: POST /api/subscriptions/{id}/activate/
        Body: { "company_email": "user@company.com", "tenant_name": "我的公司" }
        """
        # 检查用户归属：只能操作自己的订阅
        try:
            subscription = Subscription.objects.get(pk=pk, user=request.user)
        except Subscription.DoesNotExist:
            return Response(
                {'error': '订阅不存在或无权操作'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 检查状态：必须是 pending 且已支付
        if subscription.status != 'pending':
            return Response(
                {'error': '订阅状态不是待开通'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 检查是否有已支付的 PaymentTransaction
        has_paid = subscription.payment_transactions.filter(status='paid').exists()
        if not has_paid:
            return Response(
                {'error': '该订阅尚未支付，无法开通'},
                status=status.HTTP_400_BAD_REQUEST
            )

        company_email = request.data.get('company_email')
        tenant_name = request.data.get('tenant_name')

        if not company_email or not tenant_name:
            return Response(
                {'error': 'company_email 和 tenant_name 是必填项'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 检查用户是否已有租户
        from teams.models import TeamMember
        existing_membership = TeamMember.objects.filter(
            user=request.user,
            status='active'
        ).select_related('tenant').first()

        if existing_membership:
            # 用户已有租户，直接激活订阅
            subscription.activate()
            return Response({
                'tenant_id': existing_membership.tenant_id,
                'tenant_name': existing_membership.tenant.name,
                'subscription_id': subscription.id,
                'status': 'active',
                'message': '订阅已开通（用户已有租户）'
            })

        # 创建租户 - slug 需要唯一
        from tenants.models import Tenant
        import secrets
        base_slug = tenant_name.lower().replace(' ', '-')[:50]
        slug = base_slug
        while Tenant.objects.filter(slug=slug).exists():
            slug = f"{base_slug[:47]}-{secrets.token_hex(3)}"
        tenant = Tenant.objects.create(
            name=tenant_name,
            slug=slug,
            owner=request.user,
            status='active',
            current_plan=subscription.plan.name,
        )

        # 创建团队成员（owner）
        TeamMember.objects.create(
            tenant=tenant,
            user=request.user,
            role='owner',
            status='active',
        )

        # 更新用户邮箱为公司邮箱
        if company_email and not request.user.email:
            request.user.email = company_email
            request.user.save(update_fields=['email'])

        # 激活订阅并关联租户
        subscription.activate()
        subscription.tenant = tenant
        subscription.save(update_fields=['tenant'])

        return Response({
            'tenant_id': tenant.id,
            'tenant_name': tenant.name,
            'subscription_id': subscription.id,
            'status': 'active',
        })

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """取消订阅"""
        subscription = self.get_object()
        if subscription.status != 'active':
            return Response({'error': '订阅未生效，无法取消'}, status=status.HTTP_400_BAD_REQUEST)

        subscription.cancel()
        return Response({'message': '订阅已取消'})

    @action(detail=False, methods=['get'])
    def active(self, request):
        """获取用户所有活跃订阅"""
        subscriptions = self.get_queryset().filter(
            status='active',
            end_date__gt=timezone.now()
        )
        return Response(SubscriptionSerializer(subscriptions, many=True).data)
