"""
Management command para limpiar conversaciones expiradas.

Borra conversaciones cuyo ``updated_at`` supere el TTL configurado
en ``CONVERSATION_TTL_HOURS`` (por defecto 24h).

Uso::

    python manage.py cleanup_conversations
    python manage.py cleanup_conversations --hours 48
"""
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from agent.models import Conversation


class Command(BaseCommand):
    help = "Elimina conversaciones no actualizadas en las ultimas N horas."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=None,
            help=(
                "Horas de inactividad tras las que se borra una conversacion. "
                "Por defecto usa CONVERSATION_TTL_HOURS del .env."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Muestra cuantas conversaciones se borrarian sin borrarlas.",
        )

    def handle(self, *args, **options):
        ttl_hours = options["hours"] or getattr(
            settings, "CONVERSATION_TTL_HOURS", 24
        )
        cutoff = timezone.now() - timedelta(hours=ttl_hours)
        expired = Conversation.objects.filter(updated_at__lt=cutoff)
        count = expired.count()

        if options["dry_run"]:
            self.stdout.write(
                f"[dry-run] Se borrarian {count} conversaciones "
                f"(TTL={ttl_hours}h, cutoff={cutoff.isoformat()})."
            )
            return

        if count == 0:
            self.stdout.write("No hay conversaciones expiradas.")
            return

        expired.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Eliminadas {count} conversaciones "
                f"(TTL={ttl_hours}h, cutoff={cutoff.isoformat()})."
            )
        )
