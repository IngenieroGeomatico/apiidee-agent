"""Comando de gestión para indexar una fuente de conocimiento en el almacén vectorial FAISS."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from agent.rag.indexer import index_source
from vectorstore.models import KnowledgeSource


class Command(BaseCommand):
    help = 'Indexa una fuente de conocimiento (repo git o página web) para recuperación RAG.'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str, help='URL de la fuente a indexar')
        parser.add_argument(
            '--type',
            type=str,
            default='git',
            choices=['git', 'web'],
            help='Tipo de fuente: git (repositorio) o web (página de documentación)',
        )
        parser.add_argument(
            '--name',
            type=str,
            default=None,
            help='Nombre de la fuente (por defecto, el último segmento de la URL)',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100,
            help='Fragmentos por lote de embeddings (menor = menos memoria, por defecto: 100)',
        )

    def handle(self, *args, **options):
        url = options['url'].rstrip('/')
        source_type = options['type']
        name = options['name'] or url.rstrip('/').split('/')[-1]
        batch_size = options['batch_size']

        self.stdout.write(f"Indexing [{source_type}]: {url}")
        self.stdout.write(f"Name: {name}")

        source, _ = KnowledgeSource.objects.update_or_create(
            url=url,
            defaults={
                'name': name,
                'source_type': source_type,
                'status': 'indexing',
                'error_message': '',
            },
        )

        try:
            chunks_count = index_source(url, name, source_type=source_type, batch_size=batch_size)

            source.status = 'ready'
            source.chunks_count = chunks_count
            source.last_indexed = timezone.now()
            source.error_message = ''
            source.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Indexed {chunks_count} chunks from {name} [{source_type}]"
                )
            )

        except Exception as exc:
            source.status = 'error'
            source.error_message = str(exc)
            source.save()

            raise CommandError(f"Indexing failed: {exc}") from exc
