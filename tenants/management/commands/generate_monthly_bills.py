"""
生成月度账单命令

用法:
    python manage.py generate_monthly_bills --year 2026 --month 3
    python manage.py generate_monthly_bills --last
"""
import csv
import os
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db.models import Sum, Count
from tenants.models import Tenant, UsageRecord, Bill


class Command(BaseCommand):
    help = '为所有租户生成月度账单'
    
    def add_arguments(self, parser):
        parser.add_argument('--year', type=int, help='年份')
        parser.add_argument('--month', type=int, help='月份 (1-12)')
        parser.add_argument('--last', action='store_true', help='生成上个月的账单')
        parser.add_argument('--export-csv', type=str, help='导出 CSV 文件路径')
    
    def handle(self, *args, **options):
        # 确定年月
        if options.get('last'):
            # 上个月
            today = timezone.now()
            if today.month == 1:
                year = today.year - 1
                month = 12
            else:
                year = today.year
                month = today.month - 1
        else:
            year = options.get('year')
            month = options.get('month')
            if not year or not month:
                raise CommandError('请指定 --year 和 --month，或使用 --last')
        
        if month < 1 or month > 12:
            raise CommandError('月份必须在 1-12 之间')
        
        self.stdout.write(f'生成 {year} 年 {month:02d} 月账单...')
        
        # 获取该月的日期范围
        from datetime import datetime
        start_date = timezone.make_aware(datetime(year, month, 1))
        if month == 12:
            end_date = timezone.make_aware(datetime(year + 1, 1, 1))
        else:
            end_date = timezone.make_aware(datetime(year, month + 1, 1))
        
        # 获取所有租户
        tenants = Tenant.objects.all()
        
        bills_created = 0
        bill_data = []
        
        for tenant in tenants:
            # 查询该租户的用量
            usage = UsageRecord.objects.filter(
                tenant=tenant,
                timestamp__gte=start_date,
                timestamp__lt=end_date
            ).aggregate(
                total_calls=Count('id'),
                total_input_tokens=Sum('input_tokens'),
                total_output_tokens=Sum('output_tokens'),
                total_tokens=Sum('total_tokens'),
                total_cost=Sum('cost'),
            )
            
            total_calls = usage['total_calls'] or 0
            total_cost = usage['total_cost'] or Decimal('0')
            
            # 如果有用量，创建账单
            if total_calls > 0:
                # 检查是否已存在
                bill, created = Bill.objects.update_or_create(
                    tenant=tenant,
                    year=year,
                    month=month,
                    defaults={
                        'total_calls': total_calls,
                        'total_input_tokens': usage['total_input_tokens'] or 0,
                        'total_output_tokens': usage['total_output_tokens'] or 0,
                        'total_tokens': usage['total_tokens'] or 0,
                        'cost': total_cost,
                        'status': 'pending',
                    }
                )
                
                bills_created += 1
                self.stdout.write(f'  ✓ {tenant.name}: {total_calls} 次调用, ¥{total_cost}')
                
                bill_data.append({
                    'tenant': tenant.name,
                    'year': year,
                    'month': month,
                    'total_calls': total_calls,
                    'total_tokens': usage['total_tokens'] or 0,
                    'cost': float(total_cost),
                })
            else:
                self.stdout.write(f'  - {tenant.name}: 无用量')
        
        # 导出 CSV
        csv_path = options.get('export_csv')
        if csv_path and bill_data:
            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.DictWriter(f, fieldnames=['tenant', 'year', 'month', 'total_calls', 'total_tokens', 'cost'])
                writer.writeheader()
                writer.writerows(bill_data)
            self.stdout.write(self.style.SUCCESS(f'\n已导出 CSV: {csv_path}'))
        
        self.stdout.write(self.style.SUCCESS(f'\n完成！共生成 {bills_created} 个账单'))
