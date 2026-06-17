from django.contrib import admin

from .models import Repository


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'url', 'status', 'chunks_count', 'last_indexed', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('created_at',)
