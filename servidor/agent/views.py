"""
Views — Thin HTTP wrappers that delegate to the Agent.

These views handle:
- HTTP request/response (serialization, status codes)
- Persistence (saving messages to DB)
- Conversation management (create, list, delete)

They do NOT contain agent logic (prompt building, LLM calls, RAG retrieval).
"""
import json
import logging

from django.conf import settings
from django.http import JsonResponse
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.response import Response

from .agent import Agent
from .llm.config import get_configured_providers
from .models import Conversation, Message
from .serializers import ChatInputSerializer, ConversationSerializer, MessageSerializer, ToolResultSerializer

logger = logging.getLogger(__name__)


def providers_list(request):
    """Return all configured providers and their available models (no API keys)."""
    return JsonResponse(get_configured_providers(), safe=False)


@api_view(['POST'])
def test_api_key(request):
    """Test an API key against a specific provider by fetching its models."""
    provider_name = request.data.get('provider', '')
    api_key = request.data.get('api_key', '')

    if not api_key:
        return Response({"valid": False, "error": "API key es requerida"}, status=400)
    if not provider_name:
        return Response({"valid": False, "error": "Nombre del proveedor es requerido"}, status=400)

    # Find provider config
    provider_config = None
    for p in settings.LLM_PROVIDERS:
        if p["name"].lower() == provider_name.lower():
            provider_config = p
            break

    if not provider_config:
        return Response({
            "valid": False,
            "error": f"Proveedor '{provider_name}' no encontrado. Disponibles: {', '.join(p['name'] for p in settings.LLM_PROVIDERS)}"
        })

    # Test the key by fetching models from the OpenAI-compatible endpoint
    try:
        import requests
        base_url = provider_config["base_url"].rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}"}
        resp = requests.get(f"{base_url}/models", headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            models = sorted(set(m["id"] for m in data.get("data", []) if "id" in m))
            return Response({
                "valid": True,
                "provider": provider_config["name"],
                "models": models,
            })
        else:
            return Response({
                "valid": False,
                "error": f"HTTP {resp.status_code}: API key rechazada para '{provider_name}'",
            })
    except ImportError:
        return Response({"valid": False, "error": "requests no instalado"}, status=500)
    except Exception as exc:
        logger.exception("Error testing API key")
        return Response({"valid": False, "error": str(exc)})


class ConversationViewSet(
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.DestroyModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """ViewSet para gestionar conversaciones. Soporta crear, listar,
    recuperar y eliminar conversaciones, así como enviar mensajes
    y procesar resultados de herramientas a través del agente."""

    queryset = Conversation.objects.all()
    serializer_class = ConversationSerializer

    def create(self, request, *args, **kwargs):
        """Crea una nueva conversación."""
        return super().create(request, *args, **kwargs)

    def list(self, request, *args, **kwargs):
        """Lista todas las conversaciones."""
        return super().list(request, *args, **kwargs)

    def retrieve(self, request, *args, **kwargs):
        """Recupera una conversación por su ID."""
        return super().retrieve(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        """Elimina una conversación."""
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['get'], url_path='messages')
    def messages(self, request, pk=None):
        """List all messages in a conversation."""
        conversation = self.get_object()
        serializer = MessageSerializer(conversation.messages.all(), many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='chat')
    def chat(self, request, pk=None):
        """Send a message and get an AI response."""
        conversation = self.get_object()

        input_serializer = ChatInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        user_content = input_serializer.validated_data['content']
        map_state = input_serializer.validated_data.get('map_state')
        provider_name = input_serializer.validated_data.get('provider')
        model = input_serializer.validated_data.get('model')
        api_key = input_serializer.validated_data.get('api_key')

        # Persist user message
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=user_content,
        )
        if not conversation.title:
            conversation.title = user_content[:100]
            conversation.save(update_fields=['title'])

        # Delegate to Agent
        history = _build_history(conversation)
        agent = _make_agent(provider_name, model, api_key)
        result = agent.run(user_content, history, map_state=map_state)

        extra = {}
        if result.tool_calls:
            extra["tool_calls"] = result.tool_calls
        return _assistant_response(conversation, result, extra)

    @action(detail=True, methods=['post'], url_path='tool-result')
    def tool_result(self, request, pk=None):
        """Receive tool execution results from the plugin."""
        conversation = self.get_object()

        serializer = ToolResultSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tool_name = serializer.validated_data['tool_name']
        tool_call_id = serializer.validated_data['tool_call_id']
        result_data = serializer.validated_data['result']
        success = serializer.validated_data['success']
        provider_name = serializer.validated_data.get('provider')
        model = serializer.validated_data.get('model')
        api_key = serializer.validated_data.get('api_key')

        # Persist tool result
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.SYSTEM,
            content=json.dumps({"tool": tool_name, "result": result_data, "success": success}),
            metadata={"role": "tool", "tool_call_id": tool_call_id, "tool_name": tool_name},
        )

        # Delegate to Agent
        history = _build_history(conversation)
        agent = _make_agent(provider_name, model, api_key)
        result = agent.process_tool_result(tool_name, result_data, success, history)

        return _assistant_response(conversation, result)


def _build_history(conversation) -> list:
    """Convert conversation messages to list of dicts for the Agent."""
    messages = []
    for msg in conversation.messages.all():
        m = {"role": msg.role, "content": msg.content}
        if msg.metadata.get("tool_calls"):
            m["tool_calls"] = msg.metadata["tool_calls"]
        if msg.metadata.get("role") == "tool":
            m["role"] = "tool"
            m["tool_call_id"] = msg.metadata.get("tool_call_id", "")
        messages.append(m)
    return messages


def _make_agent(provider_name, model, api_key):
    """Crea un agente con los parámetros opcionales de proveedor, modelo y API key."""
    return Agent(provider_name=provider_name, model=model, api_key=api_key)


def _assistant_response(conversation, result, extra=None):
    """Persiste la respuesta del asistente y devuelve un Response DRF."""
    metadata = {"sources": result.sources}
    if extra:
        metadata.update(extra)
    msg = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=result.content,
        metadata=metadata,
    )
    data = MessageSerializer(msg).data
    data["type"] = result.type
    if extra and "tool_calls" in extra:
        data["tool_calls"] = extra["tool_calls"]
    return Response(data, status=status.HTTP_201_CREATED)
