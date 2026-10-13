from django.utils.text import slugify
from rest_framework import serializers
from .models import BlogPost, CaseStudy, DocItem, ProductKey


class ContentSerializer(serializers.ModelSerializer):
    class Meta:
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        if not validated_data.get('slug'):
            base = slugify(validated_data.get('title', 'content')) or 'content'
            slug = base
            model = self.Meta.model
            counter = 2
            while model.objects.filter(slug=slug).exists():
                slug = f'{base}-{counter}'
                counter += 1
            validated_data['slug'] = slug
        return super().create(validated_data)


class BlogPostSerializer(ContentSerializer):
    class Meta(ContentSerializer.Meta):
        model = BlogPost
        fields = '__all__'


class DocItemSerializer(ContentSerializer):
    class Meta(ContentSerializer.Meta):
        model = DocItem
        fields = '__all__'


class CaseStudySerializer(ContentSerializer):
    class Meta(ContentSerializer.Meta):
        model = CaseStudy
        fields = '__all__'
