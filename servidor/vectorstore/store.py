"""FAISS vector store wrapper utilities."""

import logging
from pathlib import Path
from typing import List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)


def get_vectorstore(repo_name: str):
    """Load and return a FAISS vector store for the given repo, or None."""
    store_path = Path(settings.VECTORSTORE_DIR) / repo_name
    index_path = store_path / "index.faiss"

    if not index_path.exists():
        return None

    try:
        from langchain_community.vectorstores import FAISS
        from langchain_openai import OpenAIEmbeddings

        embeddings = OpenAIEmbeddings(api_key=settings.OPENAI_API_KEY)
        return FAISS.load_local(
            str(store_path),
            embeddings,
            allow_dangerous_deserialization=True,
        )
    except Exception:
        logger.exception("Failed to load FAISS store for %s", repo_name)
        return None


def list_available_stores() -> List[str]:
    """Return names of all indexed repositories with a valid FAISS index."""
    vectorstore_dir = Path(settings.VECTORSTORE_DIR)
    if not vectorstore_dir.exists():
        return []

    stores: List[str] = []
    for entry in vectorstore_dir.iterdir():
        if entry.is_dir() and (entry / "index.faiss").exists():
            stores.append(entry.name)
    return stores
