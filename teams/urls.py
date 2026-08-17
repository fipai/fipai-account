"""
Teams URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TeamMemberViewSet, InvitationViewSet

router = DefaultRouter()
router.register(r'members', TeamMemberViewSet, basename='team-members')
router.register(r'invitations', InvitationViewSet, basename='invitations')

urlpatterns = [
    path('', include(router.urls)),
]
