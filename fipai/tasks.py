"""
Celery Tasks - Agent 执行引擎
"""
import time
import uuid
import random
from decimal import Decimal
from celery import shared_task
from django.utils import timezone
from django.db import transaction


def record_usage(task, agent, input_text: str, output_text: str, model: str = 'gpt-3.5-turbo'):
    """
    记录用量到数据库
    
    使用 tiktoken 计算 token 数，并计算成本
    """
    try:
        from tenants.models import UsageRecord
        
        # 计算 token 数
        input_tokens = _count_tokens(input_text, model)
        output_tokens = _count_tokens(output_text, model)
        total_tokens = input_tokens + output_tokens
        
        # 计算成本 (GPT-3.5: $0.0015/1K input, $0.002/1K output)
        # 转换为人民币 (假设 1 USD = 7.2 CNY)
        rate = Decimal('0.0072')  # $0.0015 * 7.2
        output_rate = Decimal('0.0144')  # $0.002 * 7.2
        cost = (Decimal(str(input_tokens)) * rate + Decimal(str(output_tokens)) * output_rate) / 1000
        
        # 写入数据库
        UsageRecord.objects.create(
            tenant=task.tenant,
            agent_id=agent.id if agent else None,
            task_id=str(task.task_id),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cost=cost,
            model=model,
        )
        
        print(f"Usage recorded: {input_tokens} + {output_tokens} = {total_tokens} tokens, ¥{cost}")
        return True
        
    except Exception as e:
        print(f"Failed to record usage: {e}")
        return False


def _count_tokens(text: str, model: str = 'gpt-3.5-turbo') -> int:
    """计算 token 数量（使用 tiktoken）"""
    try:
        import tiktoken
        enc = tiktoken.encoding_for_model(model)
        # 如果模型不支持，使用 cl100k_base
    except KeyError:
        enc = tiktoken.get_encoding('cl100k_base')
    
    if not text:
        return 0
    return len(enc.encode(text))


@shared_task(bind=True)
def execute_task(self, task_id: str):
    """
    执行任务的通用 Celery 任务
    
    根据 Agent 类型执行不同的逻辑：
    - worker: 模拟执行任务
    - planner: 解析需求，生成子任务
    - evaluator: 评估任务输出
    """
    from core.agents.models import Agent
    from core.tasks.models import Task
    
    try:
        # 获取任务
        task = Task.objects.select_related('agent').get(task_id=task_id)
        agent = task.agent
        
        # 更新任务状态为运行中
        task.status = 'running'
        task.save()
        
        if not agent:
            task.status = 'failed'
            task.output_data = {'error': 'No agent assigned'}
            task.save()
            return
        
        # 根据 Agent 类型执行
        if agent.agent_type == 'worker':
            _execute_worker(task, agent)
        elif agent.agent_type == 'planner':
            _execute_planner(task, agent)
        elif agent.agent_type == 'evaluator':
            _execute_evaluator(task, agent)
        elif agent.agent_type == 'matcher':
            _execute_matcher(task, agent)
        else:
            # 未知类型，模拟执行
            _execute_default(task, agent)
            
    except Task.DoesNotExist:
        print(f"Task {task_id} not found")
    except Exception as e:
        print(f"Error executing task {task_id}: {e}")
        try:
            task = Task.objects.get(task_id=task_id)
            task.status = 'failed'
            task.output_data = {'error': str(e)}
            task.save()
        except:
            pass


def _execute_worker(task, agent):
    """Worker: 模拟执行任务"""
    # 获取配置
    config = agent.config or {}
    process_time = config.get('process_time', 2)  # 默认2秒
    
    # 模拟处理时间
    time.sleep(process_time)
    
    # 生成输出
    input_data = task.input_data or {}
    input_text = input_data.get('text', input_data.get('query', ''))
    result_text = f'Processed: {input_text}'
    
    # 简单处理
    output = {
        'result': result_text,
        'agent': agent.name,
        'agent_type': agent.agent_type,
        'processed_at': timezone.now().isoformat(),
    }
    
    # 更新任务
    task.status = 'completed'
    task.output_data = output
    task.completed_at = timezone.now()
    task.save()
    
    # 记录用量
    record_usage(task, agent, input_text, result_text)


def _execute_planner(task, agent):
    """Planner: 解析需求，生成子任务计划"""
    from core.tasks.models import Task
    
    input_data = task.input_data or {}
    demand_text = input_data.get('demand_text', '')
    
    # 简单的关键词匹配生成子任务
    subtasks = _generate_subtasks(demand_text)
    
    # 创建子任务
    created_tasks = []
    for subtask in subtasks:
        subtask_obj = Task.objects.create(
            tenant=task.tenant,
            agent=None,  # 暂时不分配 agent
            task_type=subtask['type'],
            input_data=subtask['input'],
            status='pending',
            priority=task.priority,
        )
        created_tasks.append({
            'task_id': str(subtask_obj.task_id),
            'type': subtask_obj.task_type,
            'status': subtask_obj.status,
        })
    
    # 更新父任务
    task.status = 'completed'
    task.output_data = {
        'plan': subtasks,
        'subtasks': created_tasks,
        'total': len(created_tasks),
        'agent': agent.name,
    }
    task.completed_at = timezone.now()
    task.save()


def _execute_evaluator(task, agent):
    """Evaluator: 评估任务输出"""
    input_data = task.input_data or {}
    config = agent.config or {}
    
    # 获取被评估的任务 ID
    target_task_id = input_data.get('task_id')
    if not target_task_id:
        task.status = 'failed'
        task.output_data = {'error': 'No target task_id provided'}
        task.save()
        return
    
    try:
        target_task = Task.objects.get(task_id=target_task_id)
    except Task.DoesNotExist:
        task.status = 'failed'
        task.output_data = {'error': f'Target task {target_task_id} not found'}
        task.save()
        return
    
    # 获取评估配置
    confidence_threshold = config.get('confidence_threshold', 0.7)
    
    # 简单评估逻辑
    output_data = target_task.output_data or {}
    result = output_data.get('result', '')
    
    # 检查是否有结果
    if not result:
        review_status = 'rejected'
        feedback = 'No output to evaluate'
        confidence = 0.0
    else:
        # 简单规则：结果越长置信度越高
        confidence = min(len(result) / 100.0, 1.0)
        
        if confidence >= confidence_threshold:
            review_status = 'approved'
            feedback = f'Approved with confidence {confidence:.2f}'
        else:
            review_status = 'rejected'
            feedback = f'Confidence {confidence:.2f} below threshold {confidence_threshold}'
    
    # 更新被评估任务
    target_task.review_status = review_status
    target_task.save()
    
    # 更新评估任务
    task.status = 'completed'
    task.output_data = {
        'target_task_id': str(target_task_id),
        'review_status': review_status,
        'confidence': confidence,
        'feedback': feedback,
        'agent': agent.name,
    }
    task.completed_at = timezone.now()
    task.save()


def _execute_matcher(task, agent):
    """Matcher: 匹配任务（暂简单实现）"""
    input_data = task.input_data or {}
    
    # 简单的匹配逻辑
    items = input_data.get('items', [])
    criteria = input_data.get('criteria', {})
    
    matched = []
    for item in items:
        # 简单匹配
        if criteria:
            matched.append(item)
        else:
            matched.append(item)
    
    task.status = 'completed'
    task.output_data = {
        'matched': matched,
        'total': len(items),
        'matched_count': len(matched),
        'agent': agent.name,
    }
    task.completed_at = timezone.now()
    task.save()


def _execute_default(task, agent):
    """默认执行：模拟处理"""
    time.sleep(1)
    
    task.status = 'completed'
    task.output_data = {
        'result': 'Default execution completed',
        'agent': agent.name,
        'agent_type': agent.agent_type,
    }
    task.completed_at = timezone.now()
    task.save()


def _generate_subtasks(demand_text: str):
    """根据需求文本生成子任务列表"""
    subtasks = []
    demand_lower = demand_text.lower()
    
    # 关键词匹配
    if any(k in demand_lower for k in ['分析', '分析报告', 'report']):
        subtasks.append({
            'type': 'analysis',
            'input': {'query': f'分析: {demand_text}'},
        })
    
    if any(k in demand_lower for k in ['搜索', '查找', 'search']):
        subtasks.append({
            'type': 'search',
            'input': {'query': f'搜索: {demand_text}'},
        })
    
    if any(k in demand_lower for k in ['推荐', 'recommend']):
        subtasks.append({
            'type': 'recommendation',
            'input': {'context': demand_text},
        })
    
    if any(k in demand_lower for k in ['客服', 'support', 'question']):
        subtasks.append({
            'type': 'support',
            'input': {'question': demand_text},
        })
    
    # 如果没有匹配，创建通用任务
    if not subtasks:
        subtasks.append({
            'type': 'general',
            'input': {'text': demand_text},
        })
    
    return subtasks


@shared_task
def evaluate_task(task_id: str, evaluator_agent_id: int):
    """
    单独调用 Evaluator 评估任务的便捷任务
    """
    from core.agents.models import Agent
    from core.tasks.models import Task
    
    try:
        evaluator_agent = Agent.objects.get(id=evaluator_agent_id)
        
        # 创建评估任务
        task = Task.objects.create(
            tenant=evaluator_agent.tenant,
            agent=evaluator_agent,
            task_type='evaluation',
            input_data={'task_id': task_id},
            status='pending',
        )
        
        # 异步执行
        execute_task.delay(str(task.task_id))
        
        return str(task.task_id)
    except Agent.DoesNotExist:
        return None
