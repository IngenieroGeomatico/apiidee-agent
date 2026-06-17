"""Repository indexer — clones a repo, chunks files, embeds, stores in FAISS."""

import logging
import os
import shutil
import tempfile
from pathlib import Path

from django.conf import settings

from .chunking import chunk_file

logger = logging.getLogger(__name__)

# Directories and file patterns to skip during indexing
_SKIP_DIRS = {
    '.git', 'node_modules', 'dist', 'build', '__pycache__',
    '.tox', '.venv', 'venv', '.eggs', '.mypy_cache',
    '.pytest_cache', 'coverage', '.next',
}

# Binary / non-text extensions to skip
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

# Maximum file size to index (500 KB)
_MAX_FILE_SIZE = 500 * 1024


def index_repository(repo_url: str, repo_name: str) -> int:
    """Clone a repository and index its contents into FAISS.

    Returns the number of chunks created.
    """
    from langchain_community.vectorstores import FAISS
    from langchain_openai import OpenAIEmbeddings

    tmp_dir = tempfile.mkdtemp(prefix="apiidee_index_")

    try:
        # Clone repository
        logger.info("Cloning %s ...", repo_url)
        _clone_repo(repo_url, tmp_dir)

        # Walk files and collect chunks
        logger.info("Chunking files ...")
        all_chunks = _collect_chunks(tmp_dir)
        logger.info("Created %d chunks", len(all_chunks))

        if not all_chunks:
            logger.warning("No chunks created — nothing to index.")
            return 0

        # Build FAISS index
        logger.info("Embedding and building FAISS index ...")
        embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)

        texts = [c["content"] for c in all_chunks]
        metadatas = [c["metadata"] for c in all_chunks]

        store = FAISS.from_texts(texts, embeddings, metadatas=metadatas)

        # Save index
        store_path = Path(settings.VECTORSTORE_DIR) / repo_name
        store_path.mkdir(parents=True, exist_ok=True)
        store.save_local(str(store_path))
        logger.info("Saved FAISS index to %s", store_path)

        return len(all_chunks)

    finally:
        # Clean up temp directory
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _clone_repo(repo_url: str, dest: str) -> None:
    """Clone a git repository to the destination directory."""
    import git

    git.Repo.clone_from(repo_url, dest, depth=1)


def _collect_chunks(repo_dir: str) -> list:
    """Walk the repository and chunk all eligible files."""
    all_chunks = []

    for root, dirs, files in os.walk(repo_dir):
        # Prune skipped directories in-place
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]

        for filename in files:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, repo_dir)

            # Skip by extension
            _, ext = os.path.splitext(filename)
            if ext.lower() in _SKIP_EXTENSIONS:
                continue

            # Skip large files
            try:
                if os.path.getsize(file_path) > _MAX_FILE_SIZE:
                    continue
            except OSError:
                continue

            # Try to read as text
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError):
                continue

            if not content.strip():
                continue

            # Chunk the file
            chunks = chunk_file(content, rel_path)
            all_chunks.extend(chunks)

    return all_chunks
