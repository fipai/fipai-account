"""
行业包安装 API
"""
import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import IndustryPackage, Tenant
from core.agents.models import Agent


@require_http_methods(["POST"])
def install_package(request):
    """安装行业包到租户"""
    try:
        data = json.loads(request.body)
        package_id = data.get('package_id')
        
        if not package_id:
            return JsonResponse({'success': False, 'error': 'package_id required'}, status=400)
        
        # 获取租户
        tenant_id = request.session.get('tenant_id')
        if not tenant_id:
            tenant_id = 1  # 默认
        
        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Tenant not found'}, status=404)
        
        # 获取行业包
        try:
            package = IndustryPackage.objects.get(id=package_id, is_active=True)
        except IndustryPackage.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Package not found'}, status=404)
        
        # 安装 agents
        installed = []
        for agent_config in package.agents:
            name = agent_config.get('name')
            agent_type = agent_config.get('type', 'worker')
            config = agent_config.get('config', {})
            
            # 创建或更新 agent
            agent, created = Agent.objects.update_or_create(
                tenant=tenant,
                name=name,
                defaults={
                    'agent_type': agent_type,
                    'is_active': True,
                    'status': 'idle',
                    'config': config,
                }
            )
            installed.append(name)
        
        return JsonResponse({
            'success': True,
            'message': f'已安装 {len(installed)} 个智能体: {", ".join(installed)}'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@require_http_methods(["GET"])
def package_list_api(request):
    """API: 获取行业包列表"""
    packages = IndustryPackage.objects.filter(is_active=True)
    data = [{
        'id': p.id,
        'name': p.name,
        'version': p.version,
        'description': p.description,
        'category': p.category,
        'agent_count': len(p.agents),
    } for p in packages]
    return JsonResponse({'packages': data})
