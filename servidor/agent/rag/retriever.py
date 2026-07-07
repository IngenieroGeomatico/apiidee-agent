"""Recuperador RAG — consulta índices FAISS para obtener contexto relevante.

Los almacenes FAISS se cargan una vez y se guardan en caché en memoria
para evitar E/S repetitiva de disco en cada solicitud.
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.conf import settings

from .embeddings import get_embeddings

logger = logging.getLogger(__name__)

# Caché en memoria: repo_dir -> instancia del almacén FAISS
_faiss_store_cache: dict[str, object] = {}


def retrieve_context(query: str, k: int = 5) -> List[Dict]:
    """Recupera los top-k fragmentos más relevantes de todos los repositorios indexados.

    Devuelve una lista de dicts con las claves ``content`` y ``metadata``,
    ordenados por relevancia (menor distancia FAISS = más relevante) a
    través de todos los stores. Devuelve una lista vacía si no existe
    ningún índice.
    """
    vectorstore_dir = Path(settings.VECTORSTORE_DIR)
    if not vectorstore_dir.exists():
        return []

    scored_results: list[tuple] = []  # (score, dict)

    for repo_dir in vectorstore_dir.iterdir():
        if not repo_dir.is_dir():
            continue
        index_path = repo_dir / "index.faiss"
        if not index_path.exists():
            continue

        try:
            store = _get_faiss_store(str(repo_dir))
            if store is None:
                continue
            docs_and_scores = store.similarity_search_with_score(query, k=k)
            for doc, score in docs_and_scores:
                scored_results.append((score, {"content": doc.page_content, "metadata": doc.metadata}))
        except Exception:
            logger.exception("Error querying FAISS index at %s", repo_dir)
            continue

    # Ordenar por distancia FAISS (menor = más relevante) y devolver top-k
    scored_results.sort(key=lambda x: x[0])
    return [item for _, item in scored_results[:k]]


def _get_faiss_store(store_path: str):
    """Return a cached FAISS store or load it from disk."""
    if store_path in _faiss_store_cache:
        return _faiss_store_cache[store_path]
    store = _load_faiss_store(Path(store_path))
    if store is not None:
        _faiss_store_cache[store_path] = store
    return store


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


def clear_faiss_cache():
    """Limpia el caché en memoria de los almacenes FAISS (útil después de re-indexar)."""
    _faiss_store_cache.clear()
    logger.info("FAISS store cache cleared")
