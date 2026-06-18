"""
Indexer — Modular system for indexing knowledge sources into FAISS.

Supports multiple source types via BaseIndexer subclasses:
- GitRepoIndexer: clones a git repo and indexes its files
- WebIndexer: crawls a web page and indexes its content

To add a new source type: create a new class extending BaseIndexer.
"""
import logging
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List

from django.conf import settings

from html.parser import HTMLParser

from .chunking import chunk_file

logger = logging.getLogger(__name__)


# =========================================================================
# Base indexer
# =========================================================================

class BaseIndexer(ABC):
    """Base class for all knowledge source indexers."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Identifier for this indexer type (must match KnowledgeSource.SourceType)."""
        pass

    @abstractmethod
    def collect_chunks(self, url: str) -> List[Dict]:
        """
        Fetch content from the source and return a list of chunks.

        Each chunk is a dict with:
          - "content": str — the text content
          - "metadata": dict — at minimum {"source": str, "chunk_index": int}

        Returns:
            List of chunk dicts.
        """
        pass

    def index(self, url: str, name: str, batch_size: int = 100) -> int:
        """
        Full indexing pipeline: collect chunks, embed, store in FAISS.

        Args:
            url: URL of the knowledge source.
            name: Name used for the FAISS store directory.
            batch_size: Number of chunks to embed per batch (lower = less memory).

        Returns:
            Number of chunks created.
        """
        from langchain_community.vectorstores import FAISS
        from .embeddings import get_embeddings

        logger.info("[%s] Collecting chunks from %s ...", self.source_type, url)
        all_chunks = self.collect_chunks(url)
        logger.info("[%s] Created %d chunks", self.source_type, len(all_chunks))

        if not all_chunks:
            logger.warning("[%s] No chunks created — nothing to index.", self.source_type)
            return 0

        logger.info("[%s] Embedding and building FAISS index ...", self.source_type)
        embeddings = get_embeddings()

        store = None
        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]
            texts = [c["content"] for c in batch]
            metadatas = [c["metadata"] for c in batch]

            if store is None:
                store = FAISS.from_texts(texts, embeddings, metadatas=metadatas)
            else:
                store.add_texts(texts, metadatas=metadatas)

            logger.info(
                "[%s] Indexed batch %d/%d (%d chunks)",
                self.source_type,
                i // batch_size + 1,
                (len(all_chunks) + batch_size - 1) // batch_size,
                len(texts),
            )

        store_path = Path(settings.VECTORSTORE_DIR) / name
        store_path.mkdir(parents=True, exist_ok=True)
        store.save_local(str(store_path))
        logger.info("[%s] Saved FAISS index to %s", self.source_type, store_path)

        return len(all_chunks)


# =========================================================================
# Git repository indexer
# =========================================================================

_SKIP_DIRS = {
    '.git', 'node_modules', 'dist', 'build', '__pycache__',
    '.tox', '.venv', 'venv', '.eggs', '.mypy_cache',
    '.pytest_cache', 'coverage', '.next',
}

_SKIP_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.bmp', '.webp',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.zip', '.tar', '.gz', '.bz2', '.7z', '.rar',
    '.exe', '.dll', '.so', '.dylib', '.o', '.a',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx',
    '.mp3', '.mp4', '.wav', '.avi', '.mov',
    '.pyc', '.pyo', '.class', '.jar',
    '.min.js', '.map',
    '.lock',
}

_MAX_FILE_SIZE = 500 * 1024  # 500 KB


class GitRepoIndexer(BaseIndexer):
    """Indexes a git repository by cloning it and chunking its files."""

    @property
    def source_type(self):
        return "git"

    def collect_chunks(self, url: str) -> List[Dict]:
        import git

        tmp_dir = tempfile.mkdtemp(prefix="indexer_git_")
        try:
            logger.info("Cloning %s ...", url)
            git.Repo.clone_from(url, tmp_dir, depth=1)

            all_chunks = []
            for root, dirs, files in os.walk(tmp_dir):
                dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

                for filename in files:
                    file_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(file_path, tmp_dir)

                    _, ext = os.path.splitext(filename)
                    if ext.lower() in _SKIP_EXTENSIONS:
                        continue

                    try:
                        if os.path.getsize(file_path) > _MAX_FILE_SIZE:
                            continue
                    except OSError:
                        continue

                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                    except (OSError, UnicodeDecodeError):
                        continue

                    if not content.strip():
                        continue

                    chunks = chunk_file(content, rel_path)
                    all_chunks.extend(chunks)

            return all_chunks
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# =========================================================================
# Web page indexer
# =========================================================================

class _TextExtractor(HTMLParser):
    """Extrae texto plano y enlaces de HTML, ignorando script/style/nav/footer/header."""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.links = []
        self._skip = False
        self._skip_tags = {'script', 'style', 'nav', 'footer', 'header'}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True
        if tag == 'a':
            for attr_name, attr_val in attrs:
                if attr_name == 'href' and attr_val:
                    self.links.append(attr_val)
        if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(tag[1])
            self.text_parts.append('\n' + '#' * level + ' ')
        if tag in ('p', 'div', 'li', 'br', 'tr'):
            self.text_parts.append('\n')

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self.text_parts.append(data)


class WebIndexer(BaseIndexer):
    """Indexes a web page by fetching its HTML and extracting text content."""

    @property
    def source_type(self):
        return "web"

    def collect_chunks(self, url: str) -> List[Dict]:
        import re
        from urllib.request import urlopen, Request
        from urllib.parse import urljoin, urlparse

        visited = set()
        all_chunks = []
        base_domain = urlparse(url).netloc

        urls_to_visit = [url]
        max_pages = 50  # safety limit

        while urls_to_visit and len(visited) < max_pages:
            current_url = urls_to_visit.pop(0)
            if current_url in visited:
                continue
            visited.add(current_url)

            try:
                logger.info("Fetching %s ...", current_url)
                req = Request(current_url, headers={'User-Agent': 'APIIDEEAgent/1.0'})
                with urlopen(req, timeout=15) as resp:
                    if 'text/html' not in resp.headers.get('Content-Type', ''):
                        continue
                    html = resp.read().decode('utf-8', errors='ignore')
            except Exception as exc:
                logger.warning("Failed to fetch %s: %s", current_url, exc)
                continue

            # Extract text and links
            text, links = _parse_html(html)

            if text.strip():
                from .chunking import chunk_markdown_file
                page_chunks = chunk_markdown_file(text, current_url)
                all_chunks.extend(page_chunks)

            # Follow same-domain links
            for link in links:
                abs_link = urljoin(current_url, link)
                parsed = urlparse(abs_link)
                clean_link = parsed.scheme + '://' + parsed.netloc + parsed.path
                if parsed.netloc == base_domain and clean_link not in visited:
                    urls_to_visit.append(clean_link)

        return all_chunks


def _parse_html(html: str):
    """Extract text content and links from HTML."""
    parser = _TextExtractor()
    parser.feed(html)
    return ''.join(parser.text_parts), parser.links


# =========================================================================
# Indexer registry
# =========================================================================

_INDEXER_REGISTRY = {
    'git': GitRepoIndexer,
    'web': WebIndexer,
}


def get_indexer(source_type: str) -> BaseIndexer:
    """Get an indexer instance for the given source type."""
    cls = _INDEXER_REGISTRY.get(source_type)
    if cls is None:
        raise ValueError(
            f"Unknown source type '{source_type}'. "
            f"Available: {list(_INDEXER_REGISTRY.keys())}"
        )
    return cls()


def index_source(url: str, name: str, source_type: str = "git", batch_size: int = 100) -> int:
    """
    Index a knowledge source.

    This is the main entry point — replaces the old index_repository().

    Args:
        url: URL of the source (git repo URL or web page URL).
        name: Name for the FAISS store directory.
        source_type: "git" or "web".
        batch_size: Number of chunks to embed per batch (lower = less memory).

    Returns:
        Number of chunks created.
    """
    indexer = get_indexer(source_type)
    return indexer.index(url, name, batch_size=batch_size)


# Backward compatibility
def index_repository(repo_url: str, repo_name: str, batch_size: int = 100) -> int:
    """Legacy wrapper — calls index_source with source_type='git'."""
    return index_source(repo_url, repo_name, source_type="git", batch_size=batch_size)
