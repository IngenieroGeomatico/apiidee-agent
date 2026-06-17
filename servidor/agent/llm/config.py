from typing import Dict, List, Optional

from django.conf import settings

from .providers import BaseLLMProvider, GeminiProvider, OpenAICompatibleProvider, OpenAIProvider


def get_configured_providers() -> List[Dict]:
    """
    Return all configured providers with their available models.

    Each entry: { "name": str, "models": [{ "id": str, "label": str }], "default_model": str }
    This is safe to expose to the client (no API keys).
    """
    result = []
    for provider in settings.LLM_PROVIDERS:
        models = []
        for label, model_id in provider.get("model_map", {}).items():
            models.append({"id": model_id, "label": label})
        result.append({
            "name": provider["name"],
            "models": models,
            "default_model": provider.get("default_model", models[0]["id"] if models else ""),
        })
    return result


def get_provider(provider_name: str, model: str) -> BaseLLMProvider:
    """
    Get a configured LLM provider by name and model.

    Looks up the provider in settings.LLM_PROVIDERS and creates
    an OpenAICompatibleProvider with the matching base_url and api_key.
    """
    for provider in settings.LLM_PROVIDERS:
        if provider["name"].lower() == provider_name.lower():
            return OpenAICompatibleProvider(
                base_url=provider["base_url"],
                api_key=provider["api_key"],
                model=model,
            )

    raise ValueError(
        f"Unknown provider '{provider_name}'. "
        f"Available: {[p['name'] for p in settings.LLM_PROVIDERS]}"
    )


def get_llm_provider() -> BaseLLMProvider:
    """
    Legacy fallback: return a provider based on LLM_PROVIDER env var.
    Used when no provider is specified by the client.
    """
    provider_name = settings.LLM_PROVIDER

    if settings.LLM_PROVIDERS:
        try:
            return get_provider(provider_name, settings.LLM_MODEL)
        except ValueError:
            pass

    provider_registry = {
        'openai': OpenAIProvider,
        'gemini': GeminiProvider,
    }
    provider_cls = provider_registry.get(provider_name)
    if provider_cls is None:
        raise ValueError(
            f"Unknown LLM provider '{provider_name}'. "
            f"Available dynamic: {[p['name'] for p in settings.LLM_PROVIDERS]} | "
            f"Legacy: {list(provider_registry.keys())}"
        )
    return provider_cls()
