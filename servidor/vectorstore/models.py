from django.db import models


class KnowledgeSource(models.Model):
    """A source of knowledge that can be indexed for RAG retrieval."""

    class SourceType(models.TextChoices):
        GIT = "git", "Git Repository"
        WEB = "web", "Web Page / Documentation"

    url = models.URLField(unique=True)
    name = models.CharField(max_length=255)
    source_type = models.CharField(
        max_length=10,
        choices=SourceType.choices,
        default=SourceType.GIT,
    )
    last_indexed = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        default='pending',
        choices=[
            ('pending', 'Pending'),
            ('indexing', 'Indexing'),
            ('ready', 'Ready'),
            ('error', 'Error'),
        ],
    )
    error_message = models.TextField(blank=True)
    chunks_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Knowledge Source"
        verbose_name_plural = "Knowledge Sources"

    def __str__(self):
        return f"{self.name} [{self.source_type}] ({self.status})"
