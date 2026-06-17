from django.db import models


class Repository(models.Model):
    url = models.URLField(unique=True)
    name = models.CharField(max_length=255)
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

    def __str__(self):
        return f"{self.name} ({self.status})"
