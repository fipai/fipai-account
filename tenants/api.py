"""
行业包安装 API
"""
import json

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_http_methods

from .models import IndustryPackage, Tenant


def _staff_required(user):
    """Only platform staff can install industry packages into a tenant.

    The package's `agents` JSON is opaque and installs trusted code; allowing
    any authenticated tenant user to invoke this would let one tenant
    compromise another's agents. A request rejected here yields 403.
    """
    return user.is_authenticated and user.is_staff


@require_http_methods(["POST"])
@login_required(login_url="/api/auth/login")
@user_passes_test(_staff_required, login_url=None)
def install_package(request: HttpRequest) -> JsonResponse:
    """安装行业包到租户

    路由要求：登录用户 + is_staff=True（平台管理员），无登录态返回 401，
    登录但非 staff 返回 403。租户必须由调用方在 body 中显式提供 ——
    不能再 fallback 到 tenant_id=1（audit P0 #3）。
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON"}, status=400
        )

    package_id = data.get("package_id")
    tenant_id = data.get("tenant_id")
    if not package_id:
        return JsonResponse(
            {"success": False, "error": "package_id required"}, status=400
        )
    if tenant_id is None:
        return JsonResponse(
            {"success": False, "error": "tenant_id required"}, status=400
        )

    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except (Tenant.DoesNotExist, ValueError):
        return JsonResponse(
            {"success": False, "error": "Tenant not found"}, status=404
        )

    try:
        package = IndustryPackage.objects.get(id=package_id, is_active=True)
    except (IndustryPackage.DoesNotExist, ValueError):
        return JsonResponse(
            {"success": False, "error": "Package not found"}, status=404
        )

    # Lazy import: `core.agents.models` is referenced by this view but is
    # not part of this repo (audit P0 finding). Without this guard, the
    # whole module fails to import and Django would 500 every request that
    # loads urls.py. With it, install_package is at least importable; the
    # actual install will surface a 500 with a clear message.
    try:
        from core.agents.models import Agent  # type: ignore  # noqa: F401
    except ImportError:
        return JsonResponse(
            {
                "success": False,
                "error": (
                    "Industry package installation requires core.agents to be"
                    " deployed alongside this service. See tenants/api.py."
                ),
            },
            status=501,
        )

    installed = []
    for agent_config in package.agents:
        name = agent_config.get("name")
        if not name:
            continue
        Agent.objects.update_or_create(  # type: ignore[name-defined]
            tenant=tenant,
            name=name,
            defaults={
                "agent_type": agent_config.get("type", "worker"),
                "is_active": True,
                "status": "idle",
                "config": agent_config.get("config", {}),
            },
        )
        installed.append(name)

    return JsonResponse(
        {
            "success": True,
            "message": f"已安装 {len(installed)} 个智能体: {', '.join(installed)}",
        }
    )


@require_http_methods(["GET"])
@login_required(login_url="/api/auth/login")
@user_passes_test(_staff_required, login_url=None)
def package_list_api(request: HttpRequest) -> JsonResponse:
    """API: 获取行业包列表（同样限平台员工）"""
    packages = IndustryPackage.objects.filter(is_active=True)
    data = [
        {
            "id": p.id,
            "name": p.name,
            "version": p.version,
            "description": p.description,
            "category": p.category,
            "agent_count": len(p.agents),
        }
        for p in packages
    ]
    return JsonResponse({"packages": data})