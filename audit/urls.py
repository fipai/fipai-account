"""
Audit URL Configuration
"""
from django.urls import path
from .views import AuditLogListView, AuditLogDetailView

urlpatterns = [
    path('logs/', AuditLogListView.as_view(), name='audit-logs'),
    path('logs/<int:pk>/', AuditLogDetailView.as_view(), name='audit-log-detail'),
]
