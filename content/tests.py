from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .models import BlogPost, CaseStudy, DocItem


class ContentApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.published_at = timezone.now() - timedelta(minutes=1)
        self.public_post = BlogPost.objects.create(
            slug='public-post', title='Public', title_en='Public', status='published', published_at=self.published_at
        )
        BlogPost.objects.create(slug='draft-post', title='Draft', status='draft')
        self.public_doc = DocItem.objects.create(
            slug='bizgen-start', product='bizgen', title='BizGen', status='published', published_at=self.published_at
        )
        CaseStudy.objects.create(
            slug='public-case', title='Case', status='published', published_at=self.published_at
        )

    def test_public_lists_only_published_content(self):
        response = self.client.get('/api/content/posts/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['slug'], 'public-post')

    def test_public_can_filter_bizgen_docs(self):
        response = self.client.get('/api/content/docs/?product=bizgen')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['product'], 'bizgen')

    def test_anonymous_cannot_create_content(self):
        response = self.client.post('/api/content/posts/', {'slug': 'new', 'title': 'New'})
        self.assertEqual(response.status_code, 401)

    def test_staff_can_create_content(self):
        user = get_user_model().objects.create_user(username='editor', password='test-password', is_staff=True)
        self.client.force_authenticate(user=user)
        response = self.client.post('/api/content/posts/', {'slug': 'new', 'title': 'New', 'status': 'draft'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['slug'], 'new')

