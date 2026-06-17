from django.conf import settings

from .providers import BaseLLMProvider, OpenAIProvider, GeminiProvider

_provider_registry = {
    'openai': OpenAIProvider,
    'gemini': GeminiProvider,
}

_cached_provider: BaseLLMProvider | None = None


def get_llm_provider() -> BaseLLMProvider:
    """Return a configured LLM provider instance (cached)."""
    global _cached_provider
    if _cached_provider is not None:
        return _cached_provider

    provider_name = settings.LLM_PROVIDER
    provider_cls = _provider_registry.get(provider_name)
    if provider_cls is None:
        raise ValueError(
            f"Unknown LLM provider '{provider_name}'. "
            f"Available: {list(_provider_registry.keys())}"
        )

    _cached_provider = provider_cls()
    return _cached_provider
