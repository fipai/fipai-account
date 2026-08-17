"""
Invoices URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import InvoiceRequestViewSet

router = DefaultRouter(trailing_slash=False)
router.register(r'', InvoiceRequestViewSet, basename='invoices')

urlpatterns = [
    path('', include(router.urls)),
]