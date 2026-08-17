"""
Subscriptions URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SubscriptionPlanViewSet, SubscriptionViewSet

router = DefaultRouter()
router.register(r'plans', SubscriptionPlanViewSet, basename='subscription-plans')
router.register(r'', SubscriptionViewSet, basename='subscriptions')

urlpatterns = [
    path('', include(router.urls)),
]
