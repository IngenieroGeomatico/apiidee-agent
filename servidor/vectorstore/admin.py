from django.contrib import admin

from .models import KnowledgeSource


@admin.register(KnowledgeSource)
class KnowledgeSourceAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_type', 'url', 'status', 'chunks_count', 'last_indexed', 'created_at')
    list_filter = ('status', 'source_type')
    readonly_fields = ('created_at',)
