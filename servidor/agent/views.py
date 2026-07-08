"""
Vistas — Envoltorios HTTP ligeros que delegan en el Agent.

Estas vistas gestionan:
- Petición/respuesta HTTP (serialización, códigos de estado)
- Persistencia (guardar mensajes en la BD)
- Gestión de conversaciones (crear, listar, eliminar)

NO contienen lógica del agente (construcción de prompts, llamadas al LLM, recuperación RAG).
"""
import json
import logging
import threading
from collections import OrderedDict

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
    """Devuelve todos los proveedores configurados y sus modelos disponibles (sin API keys)."""
    return JsonResponse(get_configured_providers(), safe=False)


@api_view(['POST'])
def test_api_key(request):
    """Prueba una API key contra un proveedor específico obteniendo sus modelos."""
    provider_name = request.data.get('provider', '')
    api_key = request.data.get('api_key', '')

    if not api_key:
        return Response({"valid": False, "error": "API key es requerida"}, status=400)
    if not provider_name:
        return Response({"valid": False, "error": "Nombre del proveedor es requerido"}, status=400)

    # Buscar configuración del proveedor
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

    # Probar la key obteniendo modelos del endpoint compatible con OpenAI
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
        """Lista todos los mensajes de una conversación."""
        conversation = self.get_object()
        serializer = MessageSerializer(conversation.messages.all(), many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'], url_path='chat')
    def chat(self, request, pk=None):
        """Envía un mensaje y obtén una respuesta de la IA."""
        conversation = self.get_object()

        input_serializer = ChatInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        user_content = input_serializer.validated_data['content']
        map_state = input_serializer.validated_data.get('map_state')
        provider_name = input_serializer.validated_data.get('provider')
        model = input_serializer.validated_data.get('model')
        api_key = input_serializer.validated_data.get('api_key')

        # Persistir mensaje del usuario
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=[{"type": "text", "text": user_content}],
        )
        if not conversation.title:
            conversation.title = user_content[:100]
            conversation.save(update_fields=['title'])

        # Delegar al Agent
        history = _build_history(conversation)
        agent = _make_agent(provider_name, model, api_key)
        result = agent.run(user_content, history, map_state=map_state)

        extra = {}
        if result.tool_calls:
            extra["tool_calls"] = result.tool_calls
        return _assistant_response(conversation, result, extra)

    @action(detail=True, methods=['post'], url_path='tool-result')
    def tool_result(self, request, pk=None):
        """Recibe resultados de ejecución de herramientas desde el plugin."""
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

        # Persistir resultado de la herramienta
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.SYSTEM,
            content=[{"type": "tool_result", "tool_name": tool_name, "content": result_data, "success": success, "tool_call_id": tool_call_id}],
            metadata={"role": "tool", "tool_call_id": tool_call_id, "tool_name": tool_name},
        )

        # Si el resultado incluye una URL de GeoJSON, responder directamente
        # con un bloque layer para que el plugin lo cargue en el mapa.
        if isinstance(result_data, dict) and result_data.get("geojsonURL"):
            assistant_msg = Message.objects.create(
                conversation=conversation,
                role=Message.Role.ASSISTANT,
                content=[{"type": "layer", "layer": {"type": "geojson", "url": result_data["geojsonURL"], "name": result_data.get("name", "Capa")}}],
            )
            raw = MessageSerializer(assistant_msg).data
            data = {
                "id": raw["id"],
                "role": raw["role"],
                "created_at": raw["created_at"],
                "content": raw["content"],
            }
            return Response(data, status=status.HTTP_201_CREATED)

        # Delegar al Agent
        history = _build_history(conversation)
        agent = _make_agent(provider_name, model, api_key)
        result = agent.process_tool_result(tool_name, result_data, success, history)

        return _assistant_response(conversation, result)


_MAX_HISTORY_MESSAGES = 50

def _build_history(conversation, max_messages: int = _MAX_HISTORY_MESSAGES) -> list:
    """Convierte los mensajes de la conversación a una lista de dicts para el Agent.

    Sólo se incluyen los últimos *max_messages* mensajes para evitar
    exceder la ventana de contexto del LLM en conversaciones largas.
    """
    qs = conversation.messages.all()
    total = qs.count()
    if total > max_messages:
        qs = qs[total - max_messages:]

    messages = []
    for msg in qs:
        # Extrae texto plano de los bloques de contenido
        if isinstance(msg.content, list):
            # Bloques tipo texto
            texts = [b.get("text", "") for b in msg.content if b.get("type") == "text"]
            plain = "\n".join(texts) if texts else ""
        else:
            plain = str(msg.content)
        m = {"role": msg.role, "content": plain}
        # Incluye tool_calls si están en metadata
        if msg.metadata.get("tool_calls"):
            m["tool_calls"] = msg.metadata["tool_calls"]
        # Manejo especial para mensajes de herramienta (role="tool")
        if msg.metadata.get("role") == "tool":
            # Busca el bloque tool_result para extraer su payload
            tool_res = None
            if isinstance(msg.content, list):
                for b in msg.content:
                    if b.get("type") == "tool_result":
                        tool_res = b.get("content")
                        break
            m["role"] = "tool"
            m["tool_call_id"] = msg.metadata.get("tool_call_id", "")
            # El contenido del mensaje de herramienta será JSON string del resultado
            if tool_res is not None:
                m["content"] = json.dumps(tool_res, ensure_ascii=False)
        messages.append(m)
    return messages


_agent_cache: OrderedDict = OrderedDict()
_agent_cache_lock = threading.Lock()
_AGENT_CACHE_MAXSIZE = 128

def _make_agent(provider_name, model, api_key):
    """Devuelve un Agent cacheado para esta combinación de proveedor/modelo/key.

    Los Agents no guardan estado entre peticiones, por lo que se pueden
    reutilizar. El caché tiene un tamaño máximo LRU de ``_AGENT_CACHE_MAXSIZE``
    entradas para evitar fugas de memoria.  El acceso está protegido por
    un lock para garantizar thread-safety.
    """
    cache_key = (provider_name, model, api_key)
    with _agent_cache_lock:
        try:
            _agent_cache.move_to_end(cache_key)
            return _agent_cache[cache_key]
        except KeyError:
            pass
    # Crear fuera del lock para no bloquear otros hilos durante la inicialización
    agent = Agent(provider_name=provider_name, model=model, api_key=api_key)
    with _agent_cache_lock:
        _agent_cache[cache_key] = agent
        if len(_agent_cache) > _AGENT_CACHE_MAXSIZE:
            _agent_cache.popitem(last=False)
    return agent


def _assistant_response(conversation, result, extra=None):
    """Persiste la respuesta del asistente y devuelve un Response DRF.

    Las capas GeoJSON generadas por herramientas del servidor (ej:
    detecciones ML) se leen de ``result.layers`` — sin estado global.
    """
    metadata = {"sources": result.sources}
    if extra:
        metadata.update(extra)
    msg = Message.objects.create(
        conversation=conversation,
        role=Message.Role.ASSISTANT,
        content=result.content,
        metadata=metadata,
    )
    raw = MessageSerializer(msg).data
    # `msg.content` is already a list of content blocks (text, tool_call, geojson)
    content = raw["content"] if isinstance(raw["content"], list) else []

    # Ensure text block is present (AgentResponse.text ensures this)
    if not any(b.get("type") == "text" for b in content):
        content.insert(0, {"type": "text", "text": ""})

    if extra and "tool_calls" in extra:
        content.append({"type": "tool_call", "toolCalls": extra["tool_calls"]})

    # Incluir capas GeoJSON propagadas por el agente (ej: detecciones ML)
    for layer in getattr(result, "layers", []):
        content.append({"type": "layer", "layer": layer})

    data = {
        "id": raw["id"],
        "role": raw["role"],
        "created_at": raw["created_at"],
        "content": content,
    }

    return Response(data, status=status.HTTP_201_CREATED)
