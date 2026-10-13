from rest_framework.routers import DefaultRouter
from .views import BlogPostViewSet, CaseStudyViewSet, DocItemViewSet

router = DefaultRouter()
router.register('posts', BlogPostViewSet, basename='content-post')
router.register('docs', DocItemViewSet, basename='content-doc')
router.register('cases', CaseStudyViewSet, basename='content-case')

urlpatterns = router.urls
