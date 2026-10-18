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
    def validate_metrics(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('metrics must be a list.')
        for metric in value:
            if not isinstance(metric, dict) or not metric.get('label') or not metric.get('value'):
                raise serializers.ValidationError('Each metric requires label and value.')
        return value

    def validate_automation_steps(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError('automation_steps must be a list.')
        if any(not isinstance(step, (str, dict)) for step in value):
            raise serializers.ValidationError('Each automation step must be text or an object.')
        return value

    class Meta(ContentSerializer.Meta):
        model = CaseStudy
        fields = '__all__'
