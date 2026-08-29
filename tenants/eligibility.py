"""Shared tenant lifecycle eligibility rules for tenant-scoped access."""

ELIGIBLE_TENANT_STATUSES = ("trial", "active")


def eligible_tenant_filters(prefix="tenant"):
    """Return ORM kwargs requiring an enabled tenant in an eligible status.

    ``prefix`` is the relation path from the queried model to ``Tenant``;
    pass an empty string when filtering ``Tenant`` itself.
    """
    relation = f"{prefix.rstrip('__')}__" if prefix else ""
    return {
        f"{relation}is_active": True,
        f"{relation}status__in": ELIGIBLE_TENANT_STATUSES,
    }


def is_tenant_eligible(tenant):
    """Return whether a loaded tenant is enabled for tenant-scoped access."""
    return tenant.is_active and tenant.status in ELIGIBLE_TENANT_STATUSES
