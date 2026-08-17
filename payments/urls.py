"""
Payments URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PaymentViewSet, PaymentCallbackView, RefundRequestViewSet

# Payment routes at /api/payments/
payment_router = DefaultRouter(trailing_slash=False)
payment_router.register(r'', PaymentViewSet, basename='payments')

# Refund routes at /api/payments/refunds/
# Use trailing_slash=True so /refunds/{pk}/status/ works
refund_router = DefaultRouter(trailing_slash=True)
refund_router.register(r'', RefundRequestViewSet, basename='refunds')

urlpatterns = [
    path('', include(payment_router.urls)),
    path('refunds/', include(refund_router.urls)),
    path('callback/<str:gateway_name>/', PaymentCallbackView.as_view(), name='payment-callback'),
]
