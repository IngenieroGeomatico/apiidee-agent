"""Management command to index a git repository into the FAISS vector store."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from agent.rag.indexer import index_repository
from vectorstore.models import Repository


class Command(BaseCommand):
    help = 'Clone and index a git repository for RAG retrieval.'

    def add_arguments(self, parser):
        parser.add_argument('repo_url', type=str, help='Git repository URL to index')
        parser.add_argument(
            '--name',
            type=str,
            default=None,
            help='Repository name (defaults to last segment of URL)',
        )

    def handle(self, *args, **options):
        repo_url = options['repo_url'].rstrip('/')
        repo_name = options['name'] or repo_url.rstrip('/').split('/')[-1]

        self.stdout.write(f"Indexing repository: {repo_url}")
        self.stdout.write(f"Repository name: {repo_name}")

        # Create or update Repository record
        repo, created = Repository.objects.update_or_create(
            url=repo_url,
            defaults={
                'name': repo_name,
                'status': 'indexing',
                'error_message': '',
            },
        )

        try:
            chunks_count = index_repository(repo_url, repo_name)

            repo.status = 'ready'
            repo.chunks_count = chunks_count
            repo.last_indexed = timezone.now()
            repo.error_message = ''
            repo.save()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully indexed {chunks_count} chunks from {repo_name}"
                )
            )

        except Exception as exc:
            repo.status = 'error'
            repo.error_message = str(exc)
            repo.save()

            raise CommandError(f"Indexing failed: {exc}") from exc
