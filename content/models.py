from django.db import models


class PublicationStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    PUBLISHED = 'published', 'Published'
    ARCHIVED = 'archived', 'Archived'


class ProductKey(models.TextChoices):
    DATACOGNIS = 'datacognis', 'DataCognis'
    AGENTICORCHA = 'agenticorcha', 'AgenticOrcha'
    DECISIONOPS = 'decisionops', 'DecisionOps'
    BIZGEN = 'bizgen', 'BizGen'


class TimestampedContent(models.Model):
    status = models.CharField(max_length=16, choices=PublicationStatus.choices, default=PublicationStatus.DRAFT, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BlogPost(TimestampedContent):
    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=255)
    title_en = models.CharField(max_length=255, blank=True)
    excerpt = models.TextField(blank=True)
    excerpt_en = models.TextField(blank=True)
    content = models.TextField(blank=True)
    content_en = models.TextField(blank=True)
    author = models.CharField(max_length=120, blank=True)
    author_en = models.CharField(max_length=120, blank=True)
    category = models.CharField(max_length=120, blank=True)
    category_en = models.CharField(max_length=120, blank=True)
    tags = models.JSONField(default=list, blank=True)
    tags_en = models.JSONField(default=list, blank=True)
    cover_image = models.URLField(max_length=1000, blank=True)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.TextField(blank=True)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return self.title


class DocItem(TimestampedContent):
    slug = models.SlugField(max_length=160)
    product = models.CharField(max_length=32, choices=ProductKey.choices, db_index=True)
    title = models.CharField(max_length=255)
    title_en = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=120, blank=True)
    category_en = models.CharField(max_length=120, blank=True)
    content = models.TextField(blank=True)
    content_en = models.TextField(blank=True)
    display_order = models.IntegerField(default=1)
    version = models.CharField(max_length=40, default='1.0.0')
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.TextField(blank=True)

    class Meta:
        ordering = ['product', 'display_order', 'id']
        constraints = [models.UniqueConstraint(fields=['product', 'slug'], name='unique_content_doc_product_slug')]

    def __str__(self):
        return f'{self.product}: {self.title}'


class CaseStudy(TimestampedContent):
    slug = models.SlugField(max_length=160, unique=True)
    title = models.CharField(max_length=255)
    title_en = models.CharField(max_length=255, blank=True)
    company = models.CharField(max_length=255, blank=True)
    company_en = models.CharField(max_length=255, blank=True)
    industry = models.CharField(max_length=120, blank=True)
    industry_en = models.CharField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    challenge = models.TextField(blank=True)
    challenge_en = models.TextField(blank=True)
    solution = models.TextField(blank=True)
    solution_en = models.TextField(blank=True)
    results = models.TextField(blank=True)
    results_en = models.TextField(blank=True)
    products = models.JSONField(default=list, blank=True)
    cover_image = models.URLField(max_length=1000, blank=True)
    logo_image = models.URLField(max_length=1000, blank=True)
    featured = models.BooleanField(default=False)
    seo_title = models.CharField(max_length=255, blank=True)
    seo_description = models.TextField(blank=True)
    view_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-featured', '-published_at', '-created_at']

    def __str__(self):
        return self.title
