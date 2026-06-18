"""Embeddings factory — picks the best available embedding provider.

Configure via EMBEDDINGS_PROVIDER in .env:
  - "openai"  → OpenAIEmbeddings (requires OPENAI_API_KEY)
  - "gemini"  → GoogleGenerativeAIEmbeddings (requires GOOGLE_API_KEY)
  - "local"   → FastEmbedEmbeddings (free, offline, ~80MB model download)

Uses a singleton cache so the embedding model is only created once.
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

_embeddings_cache = {}


def get_embeddings():
    """Devuelve el proveedor de embeddings configurado (OpenAI, Gemini o local).

    Utiliza un caché singleton para crear el modelo una sola vez.
    """
    provider = getattr(settings, 'EMBEDDINGS_PROVIDER', '').lower()
    model = getattr(settings, 'EMBEDDINGS_MODEL', '')

    cache_key = f"{provider}:{model}" if provider else model

    if cache_key in _embeddings_cache:
        return _embeddings_cache[cache_key]

    if provider == 'openai':
        instance = _openai_embeddings(model)
    elif provider == 'gemini':
        instance = _gemini_embeddings(model)
    elif provider == 'local':
        instance = _local_embeddings(model)
    else:
        # Auto-detect fallback
        if settings.OPENAI_API_KEY:
            instance = _openai_embeddings(model)
        elif settings.GOOGLE_API_KEY:
            instance = _gemini_embeddings(model)
        else:
            logger.info("No API keys found, falling back to local embeddings")
            instance = _local_embeddings(model)

    _embeddings_cache[cache_key] = instance
    return instance


def _openai_embeddings(model: str):
    """Crea una instancia de OpenAIEmbeddings con la clave API y modelo configurados."""
    from langchain_openai import OpenAIEmbeddings
    logger.info("Using OpenAI embeddings (model=%s)", model or "text-embedding-3-small")
    kwargs = {"api_key": settings.OPENAI_API_KEY}
    if model:
        kwargs["model"] = model
    return OpenAIEmbeddings(**kwargs)


def _gemini_embeddings(model: str):
    """Crea una instancia de GoogleGenerativeAIEmbeddings con la clave API y modelo configurados."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    logger.info("Using Gemini embeddings (model=%s)", model or "models/embedding-001")
    return GoogleGenerativeAIEmbeddings(
        model=model or "models/embedding-001",
        google_api_key=settings.GOOGLE_API_KEY,
    )


def _local_embeddings(model: str):
    """Crea una instancia de FastEmbedEmbeddings usando un modelo local gratuito."""
    from langchain_community.embeddings import FastEmbedEmbeddings
    logger.info("Using local embeddings (model=%s)", model or "BAAI/bge-m3")
    return FastEmbedEmbeddings(model_name=model or "BAAI/bge-m3")
