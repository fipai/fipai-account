from django.core.management.base import BaseCommand, CommandError
from tenants.models import Tenant, Domain, User
from core.agents.models import Agent


class Command(BaseCommand):
    help = '创建新租户并自动配置默认 Agent'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, required=True, help='租户公司名称')
        parser.add_argument('--slug', type=str, required=True, help='租户标识（用于子域名）')
        parser.add_argument('--domain', type=str, required=True, help='主域名（如 tenant1.example.com）')
        parser.add_argument('--email', type=str, help='管理员邮箱')
        parser.add_argument(
            '--password',
            type=str,
            required=True,
            help='管理员密码（必填；曾有默认值 admin123，已删除以防运维误用造成公开可猜账号）',
        )
        parser.add_argument('--phone', type=str, help='联系电话')

    def handle(self, *args, **options):
        name = options['name']
        slug = options['slug']
        domain = options['domain']
        email = options.get('email', f'admin@{domain}')
        password = options['password']
        phone = options.get('phone', '')

        # 检查租户是否已存在
        if Tenant.objects.filter(slug=slug).exists():
            raise CommandError(f"租户 slug '{slug}' 已存在！")

        # 检查域名是否已存在
        if Domain.objects.filter(domain=domain).exists():
            raise CommandError(f"域名 '{domain}' 已被使用！")

        # 创建租户
        tenant = Tenant.objects.create(
            name=name,
            slug=slug,
            is_active=True,
        )
        self.stdout.write(self.style.SUCCESS(f'✅ 租户 "{name}" 创建成功'))

        # 创建域名
        Domain.objects.create(
            tenant=tenant,
            domain=domain,
            is_primary=True,
        )
        self.stdout.write(self.style.SUCCESS(f'✅ 域名 "{domain}" 绑定成功'))

        # 创建管理员用户
        username = slug + '_admin'
        admin_user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            tenant=tenant,
            is_staff=True,
            is_superuser=True,
        )
        self.stdout.write(self.style.SUCCESS(f'✅ 管理员用户 "{username}" 创建成功'))

        # 创建默认 Agent
        default_agents = [
            {
                'name': f'{slug}_planner',
                'agent_type': 'planner',
                'config': {
                    'model': 'default',
                    'temperature': 0.7,
                },
                'capabilities': ['planning', 'reasoning'],
                'is_active': True,
            },
            {
                'name': f'{slug}_worker',
                'agent_type': 'worker',
                'config': {
                    'model': 'default',
                    'max_retries': 3,
                },
                'capabilities': ['execution', 'tool_use'],
                'is_active': True,
            },
        ]

        for agent_data in default_agents:
            Agent.objects.create(tenant=tenant, **agent_data)
            self.stdout.write(self.style.SUCCESS(f'✅ Agent "{agent_data["name"]}" ({agent_data["agent_type"]}) 创建成功'))

        # 输出信息
        self.stdout.write('')
        self.stdout.write('=' * 50)
        self.stdout.write(f'🎉 租户创建完成！')
        self.stdout.write(f'   公司: {name}')
        self.stdout.write(f'   标识: {slug}')
        self.stdout.write(f'   域名: {domain}')
        self.stdout.write(f'   管理员: {username} / {password}')
        self.stdout.write('=' * 50)
