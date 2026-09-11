"""
Teams URL Configuration
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import TeamMemberViewSet, InvitationViewSet, InvitationPreviewView

router = DefaultRouter()
router.register(r'members', TeamMemberViewSet, basename='team-members')
router.register(r'invitations', InvitationViewSet, basename='invitations')

urlpatterns = [
    path('', include(router.urls)),
    # Phase 9 — 邀请码预览（落地页用）
    path('invitations/<str:code>/preview/', InvitationPreviewView.as_view(), name='invitation-preview'),
]
