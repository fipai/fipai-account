from django.contrib import admin
from .models import Tenant, Domain, UsageRecord, Bill, IndustryPackage

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'domain', 'is_active', 'created_at']
    list_filter = ['is_active']

@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    list_display = ['domain', 'tenant', 'is_primary']

@admin.register(UsageRecord)
class UsageRecordAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'date', 'api_calls', 'tokens_used', 'cost']
    list_filter = ['date']

@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ['tenant', 'period_start', 'period_end', 'amount', 'is_paid']
    list_filter = ['is_paid']

@admin.register(IndustryPackage)
class IndustryPackageAdmin(admin.ModelAdmin):
    list_display = ['name', 'version', 'category', 'is_active', 'created_at']
    list_filter = ['category', 'is_active']
