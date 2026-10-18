from django.utils import timezone
from rest_framework import viewsets
from rest_framework.filters import OrderingFilter, SearchFilter

from .models import BlogPost, CaseStudy, DocItem, PublicationStatus
from .permissions import PublicReadEditorialWrite
from .serializers import BlogPostSerializer, CaseStudySerializer, DocItemSerializer


class PublishedOrEditorialViewSet(viewsets.ModelViewSet):
    permission_classes = [PublicReadEditorialWrite]
    filter_backends = [SearchFilter, OrderingFilter]

    def get_queryset(self):
        queryset = super().get_queryset()
        if not (self.request.user and self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(status=PublicationStatus.PUBLISHED).filter(
                published_at__isnull=False, published_at__lte=timezone.now()
            )
        return queryset


class BlogPostViewSet(PublishedOrEditorialViewSet):
    queryset = BlogPost.objects.all()
    serializer_class = BlogPostSerializer
    search_fields = ['title', 'title_en', 'excerpt', 'excerpt_en', 'category', 'category_en']
    ordering_fields = ['published_at', 'created_at', 'updated_at', 'view_count']


class DocItemViewSet(PublishedOrEditorialViewSet):
    queryset = DocItem.objects.all()
    serializer_class = DocItemSerializer
    search_fields = ['title', 'title_en', 'category', 'category_en', 'product']
    ordering_fields = ['display_order', 'updated_at', 'created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        product = self.request.query_params.get('product')
        if product:
            queryset = queryset.filter(product=product)
        return queryset


class CaseStudyViewSet(PublishedOrEditorialViewSet):
    queryset = CaseStudy.objects.all()
    serializer_class = CaseStudySerializer
    search_fields = ['title', 'title_en', 'company', 'company_en', 'industry', 'industry_en', 'business_goal', 'business_goal_en']
    ordering_fields = ['featured', 'display_order', 'published_at', 'created_at', 'view_count']

    def get_queryset(self):
        queryset = super().get_queryset()
        for field in ('industry', 'case_type', 'business_goal'):
            value = self.request.query_params.get(field)
            if value:
                queryset = queryset.filter(**{f'{field}__iexact': value})
        product = self.request.query_params.get('product')
        if product:
            queryset = queryset.filter(products__contains=[product])
        tag = self.request.query_params.get('tag')
        if tag:
            queryset = queryset.filter(business_tags__contains=[tag])
        return queryset
