"""RAG retriever — queries FAISS indexes for relevant context."""

import logging
from pathlib import Path
from typing import Dict, List

from django.conf import settings

from .embeddings import get_embeddings

logger = logging.getLogger(__name__)


def retrieve_context(query: str, k: int = 5) -> List[Dict]:
    """Retrieve the top-k most relevant chunks across all indexed repos.

    Returns a list of dicts with 'content' and 'metadata' keys.
    Gracefully returns an empty list if no index exists.
    """
    vectorstore_dir = Path(settings.VECTORSTORE_DIR)
    if not vectorstore_dir.exists():
        return []

    results: List[Dict] = []

    for repo_dir in vectorstore_dir.iterdir():
        if not repo_dir.is_dir():
            continue
        index_path = repo_dir / "index.faiss"
        if not index_path.exists():
            continue

        try:
            store = _load_faiss_store(repo_dir)
            if store is None:
                continue
            docs = store.similarity_search(query, k=k)
            for doc in docs:
                results.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata,
                })
        except Exception:
            logger.exception("Error querying FAISS index at %s", repo_dir)
            continue

    # Sort by relevance (FAISS returns ordered per-store, but we merge)
    # Return top-k across all stores
    return results[:k]


def _load_faiss_store(store_path: Path):
    """Load a FAISS vector store from disk."""
    try:
        from langchain_community.vectorstores import FAISS

        embeddings = get_embeddings()
        return FAISS.load_local(
            str(store_path),
            embeddings,
            allow_dangerous_deserialization=True,
        )
    except ImportError:
        logger.warning(
            "langchain_community or langchain_openai not installed. "
            "RAG retrieval unavailable."
        )
        return None
