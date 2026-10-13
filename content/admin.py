from django.contrib import admin
from .models import BlogPost, CaseStudy, DocItem


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'published_at', 'updated_at')
    list_filter = ('status', 'category')
    search_fields = ('title', 'title_en', 'slug')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(DocItem)
class DocItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'product', 'status', 'display_order', 'updated_at')
    list_filter = ('product', 'status')
    search_fields = ('title', 'title_en', 'slug')


@admin.register(CaseStudy)
class CaseStudyAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'status', 'featured', 'published_at')
    list_filter = ('status', 'featured', 'industry')
    search_fields = ('title', 'title_en', 'company', 'company_en', 'slug')
    prepopulated_fields = {'slug': ('title',)}
