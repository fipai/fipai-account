"""给租户开通 FIP 全平台产品（自助联调用）。

背景：产品访问范围由两处共同决定 —— 订阅（Subscription）与成员权限
（TeamMember.product_permissions）。两者缺一，签发出来的 token 里
`product_scopes` 就少一个产品，下游按 scope 校验时直接 401/403。

平台自己的租户（FIP.AI）当初只订了 AgenticOrcha，结果 DataCognis /
DecisionOps / BusinessBuilder 三个产品的 API 对真实用户全部不可用 —— SPA 能打开，
一调接口就 401，而日志里看不出是订阅问题。

本命令幂等：重复执行不会重复建套餐，也不会把已生效的订阅改坏。
"""
from __future__ import annotations

import datetime

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from subscriptions.models import Subscription, SubscriptionPlan
from teams.models import TeamMember
from tenants.models import Tenant

# canonical scope 以各产品实际校验的值为准：
# BizGen 同时接受 bizgen / businessbuilder，这里用 businessbuilder。
PLATFORM_PRODUCTS = ('datacognis', 'decisionops', 'businessbuilder')

PRODUCT_LABELS = {
    'datacognis': 'DataCognis',
    'decisionops': 'DecisionOps',
    'businessbuilder': 'BusinessBuilder',
    'agenticorcha': 'AgenticOrcha',
}


class Command(BaseCommand):
    help = '给指定租户开通 FIP 全平台产品访问权（订阅 + 成员权限），用于自有租户的联调与演示'

    def add_arguments(self, parser):
        parser.add_argument('--tenant-id', type=int, required=True, help='要开通的租户 id')
        parser.add_argument(
            '--products',
            nargs='+',
            default=list(PLATFORM_PRODUCTS),
            help='要开通的产品，默认全平台三个产品',
        )
        parser.add_argument(
            '--years',
            type=int,
            default=10,
            help='订阅有效期（年），默认 10 年',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='只打印将要做的改动，不写库',
        )

    def handle(self, *args, **options):
        tenant_id = options['tenant_id']
        products = options['products']
        years = options['years']
        dry_run = options['dry_run']

        tenant = Tenant.objects.filter(pk=tenant_id, is_active=True).first()
        if tenant is None:
            raise CommandError(f'租户 {tenant_id} 不存在或已停用')

        valid_products = {choice[0] for choice in SubscriptionPlan.PRODUCT_CHOICES}
        unknown = [p for p in products if p not in valid_products]
        if unknown:
            raise CommandError(f'未知产品: {unknown}')

        members = TeamMember.objects.filter(tenant=tenant, status='active')
        if not members.exists():
            raise CommandError(f'租户 {tenant_id} 没有 active 成员，无人可授予权限')

        now = timezone.now()
        deadline = now + datetime.timedelta(days=365 * years)

        for product in products:
            plan = self._ensure_plan(product, dry_run)
            self._ensure_subscription(tenant, plan, now, deadline, dry_run)

        for member in members:
            self._ensure_permissions(member, products, dry_run)

        if dry_run:
            self.stdout.write(self.style.WARNING('dry-run：以上改动均未写库'))
        else:
            self.stdout.write(self.style.SUCCESS(f'租户 {tenant_id} 已开通: {", ".join(products)}'))

    # ---- 内部步骤 ----

    def _ensure_plan(self, product: str, dry_run: bool) -> SubscriptionPlan:
        label = PRODUCT_LABELS.get(product, product)
        plan = SubscriptionPlan.objects.filter(product=product, tier='enterprise').first()
        if plan is not None:
            return plan
        if dry_run:
            self.stdout.write(f'[dry-run] 将新建套餐: FIP.AI {label} 企业版')
            return SubscriptionPlan(
                product=product,
                tier='enterprise',
                period='yearly',
                name=f'FIP.AI {label} 企业版',
                price=0,
            )
        plan = SubscriptionPlan.objects.create(
            product=product,
            tier='enterprise',
            period='yearly',
            name=f'FIP.AI {label} 企业版',
            description='平台自有租户的全产品联调授权',
            price=0,
            max_users=999,
            max_api_calls=100_000_000,
            max_storage_gb=100,
            features=['全平台联调'],
        )
        self.stdout.write(f'  新建套餐 #{plan.id} {plan.name}')
        return plan

    def _ensure_subscription(self, tenant, plan, now, deadline, dry_run: bool) -> None:
        subscription = Subscription.objects.filter(tenant=tenant, plan=plan).first()
        if subscription is None:
            if dry_run:
                self.stdout.write(f'[dry-run] 将新建订阅: {tenant.name} / {plan.name}')
                return
            Subscription.objects.create(
                user=self._any_owner(tenant),
                plan=plan,
                tenant=tenant,
                status='active',
                start_date=now,
                end_date=deadline,
                auto_renew=False,
            )
            self.stdout.write(f'  新建订阅: {tenant.name} / {plan.name}')
            return
        if subscription.status == 'active' and subscription.end_date and subscription.end_date > now:
            return
        if dry_run:
            self.stdout.write(f'[dry-run] 将重新生效订阅: {plan.name}')
            return
        subscription.status = 'active'
        subscription.start_date = now
        subscription.end_date = deadline
        subscription.save()
        self.stdout.write(f'  重新生效订阅: {plan.name}')

    def _ensure_permissions(self, member, products, dry_run: bool) -> None:
        permissions = dict(member.product_permissions or {})
        changed = False
        for product in products:
            current = permissions.get(product)
            if not isinstance(current, dict) or current.get('access') is not True:
                permissions[product] = {'access': True, 'role': 'platform_admin'}
                changed = True
        if not changed:
            return
        if dry_run:
            self.stdout.write(f'[dry-run] 将更新成员 #{member.id} 的产品权限')
            return
        member.product_permissions = permissions
        member.save(update_fields=['product_permissions'])
        self.stdout.write(f'  更新成员 #{member.id} ({member.user_id}) 产品权限: {sorted(permissions)}')

    @staticmethod
    def _any_owner(tenant):
        member = TeamMember.objects.filter(tenant=tenant, status='active').order_by('id').first()
        user = get_user_model().objects.filter(pk=member.user_id).first()
        if user is None:
            raise CommandError(f'租户 {tenant.name} 的成员账号不存在')
        return user
