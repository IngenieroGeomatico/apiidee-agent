"""Tests unitarios para el comando de gestión cleanup_conversations.

Cubre la eliminación de conversaciones expiradas, el modo --dry-run
y la opción --hours para personalizar el TTL.
"""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from agent.models import Conversation


class CleanupConversationsCommandTest(TestCase):
    """Verifica el comando cleanup_conversations con distintas opciones."""

    def test_elimina_conversaciones_expiradas(self):
        """El comando borra conversaciones con updated_at anterior al TTL."""
        # Crear conversación y forzar updated_at antiguo
        conv_old = Conversation.objects.create(title="Expirada")
        Conversation.objects.filter(id=conv_old.id).update(
            updated_at=timezone.now() - timedelta(hours=999)
        )
        conv_recent = Conversation.objects.create(title="Reciente")

        out = StringIO()
        call_command("cleanup_conversations", stdout=out)

        # La expirada se borró, la reciente sigue
        self.assertFalse(Conversation.objects.filter(id=conv_old.id).exists())
        self.assertTrue(Conversation.objects.filter(id=conv_recent.id).exists())
        self.assertIn("Eliminadas", out.getvalue())

    def test_dry_run_no_borra(self):
        """El comando con --dry-run muestra cuántas se borrarían sin borrarlas."""
        conv = Conversation.objects.create(title="Para dry-run")
        Conversation.objects.filter(id=conv.id).update(
            updated_at=timezone.now() - timedelta(hours=999)
        )

        out = StringIO()
        call_command("cleanup_conversations", "--dry-run", stdout=out)

        # La conversación sigue existiendo
        self.assertTrue(Conversation.objects.filter(id=conv.id).exists())
        self.assertIn("dry-run", out.getvalue())

    def test_hours_personalizado(self):
        """El comando con --hours usa el TTL personalizado en lugar del configurado."""
        # Crear conversación con 5 horas de antigüedad
        conv = Conversation.objects.create(title="Semi-antigua")
        Conversation.objects.filter(id=conv.id).update(
            updated_at=timezone.now() - timedelta(hours=5)
        )

        # Con --hours=3, debería borrarla (5h > 3h)
        out = StringIO()
        call_command("cleanup_conversations", "--hours=3", stdout=out)

        self.assertFalse(Conversation.objects.filter(id=conv.id).exists())
