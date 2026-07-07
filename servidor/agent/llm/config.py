from typing import Dict, List, Optional

from django.conf import settings

from .providers import BaseLLMProvider, GeminiProvider, OpenAICompatibleProvider, OpenAIProvider


def get_configured_providers() -> List[Dict]:
    """
    Devuelve todos los proveedores configurados con sus modelos disponibles.

    Cada entrada: { "name": str, "models": [{ "id": str, "label": str }], "default_model": str }
    Esto es seguro de exponer al cliente (sin API keys).
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


def get_provider(provider_name: str, model: str,
                 api_key: Optional[str] = None) -> BaseLLMProvider:
    """
    Obtiene un proveedor LLM configurado por nombre y modelo.

    Busca el proveedor en settings.LLM_PROVIDERS y crea
    un OpenAICompatibleProvider con el base_url y api_key correspondientes.

    Si se proporciona api_key, esta sobrescribe la clave configurada (para
    claves proporcionadas por el usuario desde el frontend).
    """
    for provider in settings.LLM_PROVIDERS:
        if provider["name"].lower() == provider_name.lower():
            return OpenAICompatibleProvider(
                base_url=provider["base_url"],
                api_key=api_key or provider["api_key"],
                model=model,
            )

    raise ValueError(
        f"Unknown provider '{provider_name}'. "
        f"Available: {[p['name'] for p in settings.LLM_PROVIDERS]}"
    )


def get_llm_provider() -> BaseLLMProvider:
    """
    Fallback heredado: devuelve un proveedor basado en la variable de entorno LLM_PROVIDER.
    Se usa cuando el cliente no especifica ningún proveedor.
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
