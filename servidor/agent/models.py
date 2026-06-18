import uuid

from django.db import models


class Conversation(models.Model):
    """Modelo que representa una conversación entre el usuario y el agente."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        """Devuelve el título de la conversación o su UUID si no tiene título."""
        return self.title or str(self.id)


class Message(models.Model):
    """Modelo que representa un mensaje individual dentro de una conversación."""

    class Role(models.TextChoices):
        """Roles posibles para un mensaje: usuario, asistente o sistema."""
        USER = "user"
        ASSISTANT = "assistant"
        SYSTEM = "system"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        Conversation, on_delete=models.CASCADE, related_name="messages"
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        """Devuelve una representación corta del mensaje con rol y comienzo del contenido."""
        return f"{self.role}: {self.content[:50]}"
