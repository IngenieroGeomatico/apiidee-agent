"""Fábrica de embeddings — elige el mejor proveedor de embeddings disponible.

Configurar mediante EMBEDDINGS_PROVIDER en .env:
  - "openai"  → OpenAIEmbeddings (requiere OPENAI_API_KEY)
  - "gemini"  → GoogleGenerativeAIEmbeddings (requiere GOOGLE_API_KEY)
  - "local"   → FastEmbedEmbeddings (gratuito, offline, descarga de ~80MB)

Utiliza un caché singleton para que el modelo de embedding se cree solo una vez.
"""

import logging
import threading

from django.conf import settings

logger = logging.getLogger(__name__)

_embeddings_cache: dict = {}
_embeddings_lock = threading.Lock()


def get_embeddings():
    """Devuelve el proveedor de embeddings configurado (OpenAI, Gemini o local).

    Utiliza un caché singleton thread-safe para crear el modelo una sola vez.
    """
    provider = getattr(settings, 'EMBEDDINGS_PROVIDER', '').lower()
    model = getattr(settings, 'EMBEDDINGS_MODEL', '')

    cache_key = f"{provider}:{model}" if provider else model

    with _embeddings_lock:
        if cache_key in _embeddings_cache:
            return _embeddings_cache[cache_key]

    if provider == 'openai':
        instance = _openai_embeddings(model)
    elif provider == 'gemini':
        instance = _gemini_embeddings(model)
    elif provider == 'local':
        instance = _local_embeddings(model)
    else:
        # Detección automática como fallback
        if settings.OPENAI_API_KEY:
            instance = _openai_embeddings(model)
        elif settings.GOOGLE_API_KEY:
            instance = _gemini_embeddings(model)
        else:
            logger.info("No API keys found, falling back to local embeddings")
            instance = _local_embeddings(model)

    with _embeddings_lock:
        # Double-check: otro hilo pudo crearlo mientras tanto
        if cache_key not in _embeddings_cache:
            _embeddings_cache[cache_key] = instance
        else:
            instance = _embeddings_cache[cache_key]
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
