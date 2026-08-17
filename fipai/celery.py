"""
Celery 配置文件
"""
import os
from celery import Celery

# 设置 Django settings 模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'fipai.settings')

# 创建 Celery app
app = Celery('fipai')

# 从 Django settings 加载配置
app.config_from_object('django.conf:settings', namespace='CELERY')

# 自动发现 tasks
# app.autodiscover_tasks(['fipai'])

# 手动导入任务
from fipai import tasks  # noqa


# Celery 配置
app.conf.update(
    # Broker
    broker_url='redis://localhost:6379/0',
    result_backend='redis://localhost:6379/1',
    
    # 任务序列化
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    
    # 时区
    timezone='Asia/Shanghai',
    enable_utc=True,
    
    # 任务配置
    task_track_started=True,
    task_time_limit=3600,  # 1小时超时
    task_soft_time_limit=3000,
    
    # Worker 配置
    worker_prefetch_multiplier=1,
    worker_concurrency=4,
)
