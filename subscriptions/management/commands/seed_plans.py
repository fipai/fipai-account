from django.core.management.base import BaseCommand
from subscriptions.models import SubscriptionPlan


class Command(BaseCommand):
    help = 'Seed subscription plans'

    def handle(self, *args, **options):
        plans = [
            # DataCognis
            {
                'product': 'datacognis',
                'tier': 'basic',
                'name': 'DataCognis 基础版',
                'price': 299,
                'period': 'monthly',
                'max_users': 5,
                'features': ['数据源连接', '基础指标', '仪表盘', '定时报告'],
            },
            {
                'product': 'datacognis',
                'tier': 'pro',
                'name': 'DataCognis 专业版',
                'price': 899,
                'period': 'monthly',
                'max_users': 20,
                'features': ['数据源连接', '全部指标', '高级仪表盘', 'AI 分析', '团队协作', 'API 访问'],
            },
            # AgenticOrcha
            {
                'product': 'agenticorcha',
                'tier': 'basic',
                'name': 'AgenticOrcha 基础版',
                'price': 499,
                'period': 'monthly',
                'max_users': 5,
                'features': ['工作流编排', '基础模板', 'Webhook 集成', '1000 次执行/月'],
            },
            {
                'product': 'agenticorcha',
                'tier': 'pro',
                'name': 'AgenticOrcha 专业版',
                'price': 1499,
                'period': 'monthly',
                'max_users': 50,
                'features': ['工作流编排', '全部模板', 'API 集成', 'AI Agent', '优先执行', '无限执行'],
            },
            # DecisionOps
            {
                'product': 'decisionops',
                'tier': 'basic',
                'name': 'DecisionOps 基础版',
                'price': 399,
                'period': 'monthly',
                'max_users': 5,
                'features': ['决策流程', '规则引擎', '基础报表', '1000 次决策/月'],
            },
            {
                'product': 'decisionops',
                'tier': 'pro',
                'name': 'DecisionOps 专业版',
                'price': 1299,
                'period': 'monthly',
                'max_users': 50,
                'features': ['决策流程', '高级规则引擎', 'AI 推荐', '实时监控', '无限决策'],
            },
            # BusinessBuilder — Portal (04UnifiedPortal) advertises this card; without
            # a seed plan the user can never subscribe and the card stays locked.
            {
                'product': 'businessbuilder',
                'tier': 'basic',
                'name': 'BusinessBuilder 基础版',
                'price': 199,
                'period': 'monthly',
                'max_users': 5,
                'features': ['应用模板', '可视化编排', 'Webhook 集成', '500 次构建/月'],
            },
            {
                'product': 'businessbuilder',
                'tier': 'pro',
                'name': 'BusinessBuilder 专业版',
                'price': 699,
                'period': 'monthly',
                'max_users': 20,
                'features': ['应用模板', '全部编排', 'API 集成', 'AI 助手', '优先构建', '无限构建'],
            },
        ]

        for plan_data in plans:
            plan, created = SubscriptionPlan.objects.update_or_create(
                product=plan_data['product'],
                tier=plan_data['tier'],
                defaults=plan_data
            )
            status = 'Created' if created else 'Updated'
            self.stdout.write(f'{status}: {plan.name} ({plan.product} - {plan.tier})')

        self.stdout.write(self.style.SUCCESS(f'Successfully seeded {len(plans)} subscription plans'))
