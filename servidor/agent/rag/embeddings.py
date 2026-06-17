"""Embeddings factory — picks the best available embedding provider.

Configure via EMBEDDINGS_PROVIDER in .env:
  - "openai"  → OpenAIEmbeddings (requires OPENAI_API_KEY)
  - "gemini"  → GoogleGenerativeAIEmbeddings (requires GOOGLE_API_KEY)
  - "local"   → FastEmbedEmbeddings (free, offline, ~80MB model download)
"""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def get_embeddings():
    provider = getattr(settings, 'EMBEDDINGS_PROVIDER', '').lower()
    model = getattr(settings, 'EMBEDDINGS_MODEL', '')

    if provider == 'openai':
        return _openai_embeddings(model)
    if provider == 'gemini':
        return _gemini_embeddings(model)
    if provider == 'local':
        return _local_embeddings(model)

    # Auto-detect fallback
    if settings.OPENAI_API_KEY:
        return _openai_embeddings(model)
    if settings.GOOGLE_API_KEY:
        return _gemini_embeddings(model)

    logger.info("No API keys found, falling back to local embeddings")
    return _local_embeddings(model)


def _openai_embeddings(model: str):
    from langchain_openai import OpenAIEmbeddings
    logger.info("Using OpenAI embeddings (model=%s)", model or "text-embedding-3-small")
    kwargs = {"api_key": settings.OPENAI_API_KEY}
    if model:
        kwargs["model"] = model
    return OpenAIEmbeddings(**kwargs)


def _gemini_embeddings(model: str):
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    logger.info("Using Gemini embeddings (model=%s)", model or "models/embedding-001")
    return GoogleGenerativeAIEmbeddings(
        model=model or "models/embedding-001",
        google_api_key=settings.GOOGLE_API_KEY,
    )


def _local_embeddings(model: str):
    from langchain_community.embeddings import FastEmbedEmbeddings
    logger.info("Using local embeddings (model=%s)", model or "BAAI/bge-small-en-v1.5")
    return FastEmbedEmbeddings(model_name=model or "BAAI/bge-small-en-v1.5")
