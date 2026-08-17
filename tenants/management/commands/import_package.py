"""
Django management command to import industry package from JSON file.
Usage: python manage.py import_package /path/to/package.json
"""
import json
from django.core.management.base import BaseCommand
from tenants.models import IndustryPackage


class Command(BaseCommand):
    help = 'Import industry package from JSON file'
    
    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to package JSON file')
    
    def handle(self, *args, **options):
        file_path = options['file_path']
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            self.stderr.write(self.style.ERROR(f"File not found: {file_path}"))
            return
        except json.JSONDecodeError as e:
            self.stderr.write(self.style.ERROR(f"Invalid JSON: {e}"))
            return
        
        # 创建或更新包
        package, created = IndustryPackage.objects.update_or_create(
            name=data.get('name'),
            version=data.get('version', '1.0.0'),
            defaults={
                'description': data.get('description', ''),
                'category': data.get('category', '通用'),
                'agents': data.get('agents', []),
                'thumbnail': data.get('thumbnail', ''),
                'is_active': data.get('is_active', True),
            }
        )
        
        if created:
            self.stdout.write(self.style.SUCCESS(f"Created package: {package.name}"))
        else:
            self.stdout.write(self.style.SUCCESS(f"Updated package: {package.name}"))
        
        self.stdout.write(f"  Agents: {len(package.agents)}")
