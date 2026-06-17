"""Management command to index a knowledge source into the FAISS vector store."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from agent.rag.indexer import index_source
from vectorstore.models import KnowledgeSource


class Command(BaseCommand):
    help = 'Index a knowledge source (git repo or web page) for RAG retrieval.'

    def add_arguments(self, parser):
        parser.add_argument('url', type=str, help='URL of the source to index')
        parser.add_argument(
            '--type',
            type=str,
            default='git',
            choices=['git', 'web'],
            help='Source type: git (repository) or web (documentation page)',
        )
        parser.add_argument(
            '--name',
            type=str,
            default=None,
            help='Source name (defaults to last segment of URL)',
        )

    def handle(self, *args, **options):
        url = options['url'].rstrip('/')
        source_type = options['type']
        name = options['name'] or url.rstrip('/').split('/')[-1]

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
            chunks_count = index_source(url, name, source_type=source_type)

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
