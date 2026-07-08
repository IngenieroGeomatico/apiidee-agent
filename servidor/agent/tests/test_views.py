"""
Tests de integración para las views del agente.

Cubre los endpoints REST del ConversationViewSet (CRUD + messages),
las funciones auxiliares ``_build_history`` y ``_make_agent``, y
verifica que no se realizan llamadas reales al LLM.
"""
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from agent.models import Conversation, Message
from agent.views import _agent_cache, _build_history, _make_agent, _MAX_HISTORY_MESSAGES


class ConversationCRUDTests(TestCase):
    """Tests CRUD para el endpoint /api/conversations/."""

    def setUp(self):
        """Inicializa el cliente API y crea una conversación de ejemplo."""
        self.client = APIClient()
        self.conversation = Conversation.objects.create(title="Test")

    # -- CREATE --

    def test_create_conversation_returns_201(self):
        """POST /api/conversations/ devuelve 201 y un UUID válido."""
        response = self.client.post("/api/conversations/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("id", response.data)

    def test_create_conversation_with_title(self):
        """POST /api/conversations/ con título lo persiste correctamente."""
        response = self.client.post(
            "/api/conversations/", {"title": "Mi conversación"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "Mi conversación")

    def test_create_conversation_empty_title(self):
        """POST /api/conversations/ sin título crea conversación con título vacío."""
        response = self.client.post("/api/conversations/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["title"], "")

    # -- LIST --

    def test_list_conversations(self):
        """GET /api/conversations/ devuelve la lista de conversaciones."""
        response = self.client.get("/api/conversations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # DRF con paginación devuelve dict con 'results'
        results = response.data.get("results", response.data)
        self.assertIsInstance(results, list)
        self.assertGreaterEqual(len(results), 1)

    def test_list_conversations_includes_message_count(self):
        """GET /api/conversations/ incluye message_count en cada elemento."""
        Message.objects.create(
            conversation=self.conversation, role=Message.Role.USER, content=[{"type": "text", "text": "hola"}]
        )
        response = self.client.get("/api/conversations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = response.data.get("results", response.data)
        conv_data = next(
            c for c in results if c["id"] == str(self.conversation.id)
        )
        self.assertEqual(conv_data["message_count"], 1)

    # -- RETRIEVE --

    def test_retrieve_conversation(self):
        """GET /api/conversations/{id}/ devuelve la conversación solicitada."""
        url = f"/api/conversations/{self.conversation.id}/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.conversation.id))
        self.assertEqual(response.data["title"], "Test")

    def test_retrieve_nonexistent_conversation(self):
        """GET /api/conversations/{id}/ con UUID inexistente devuelve 404."""
        url = "/api/conversations/00000000-0000-0000-0000-000000000000/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # -- DESTROY --

    def test_destroy_conversation(self):
        """DELETE /api/conversations/{id}/ elimina la conversación y devuelve 204."""
        url = f"/api/conversations/{self.conversation.id}/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Conversation.objects.filter(id=self.conversation.id).exists())

    def test_destroy_nonexistent_conversation(self):
        """DELETE /api/conversations/{id}/ con UUID inexistente devuelve 404."""
        url = "/api/conversations/00000000-0000-0000-0000-000000000000/"
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # -- MESSAGES --

    def test_messages_empty(self):
        """GET /api/conversations/{id}/messages/ devuelve lista vacía sin mensajes."""
        url = f"/api/conversations/{self.conversation.id}/messages/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_messages_returns_ordered_messages(self):
        """GET /api/conversations/{id}/messages/ devuelve mensajes ordenados por fecha."""
        Message.objects.create(
            conversation=self.conversation, role=Message.Role.USER, content=[{"type": "text", "text": "primero"}]
        )
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content=[{"type": "text", "text": "segundo"}],
        )
        url = f"/api/conversations/{self.conversation.id}/messages/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        # content es una lista de bloques (formato Anthropic/MCP)
        self.assertEqual(response.data[0]["content"], [{"type": "text", "text": "primero"}])
        self.assertEqual(response.data[1]["content"], [{"type": "text", "text": "segundo"}])


class BuildHistoryTests(TestCase):
    """Tests para la función ``_build_history``."""

    def setUp(self):
        """Crea una conversación vacía para los tests."""
        self.conversation = Conversation.objects.create(title="History test")

    def test_returns_empty_list_for_no_messages(self):
        """Conversación sin mensajes devuelve lista vacía."""
        result = _build_history(self.conversation)
        self.assertEqual(result, [])

    def test_truncates_to_max_messages(self):
        """Con más de 50 mensajes, devuelve solo los últimos 50."""
        total = 60
        for i in range(total):
            Message.objects.create(
                conversation=self.conversation,
                role=Message.Role.USER,
                content=f"Mensaje {i}",
            )
        result = _build_history(self.conversation)
        self.assertEqual(len(result), _MAX_HISTORY_MESSAGES)
        # Verifica que se quedaron los últimos 50 (del 10 al 59)
        self.assertEqual(result[0]["content"], "Mensaje 10")
        self.assertEqual(result[-1]["content"], "Mensaje 59")

    def test_respects_custom_max(self):
        """Acepta un max_messages personalizado."""
        for i in range(20):
            Message.objects.create(
                conversation=self.conversation,
                role=Message.Role.USER,
                content=f"Mensaje {i}",
            )
        result = _build_history(self.conversation, max_messages=5)
        self.assertEqual(len(result), 5)
        self.assertEqual(result[0]["content"], "Mensaje 15")

    def test_role_mapping_user(self):
        """Mensajes con role USER se mapean a 'user'."""
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content=[{"type": "text", "text": "Hola"}],
        )
        result = _build_history(self.conversation)
        self.assertEqual(result[0]["role"], "user")

    def test_role_mapping_tool_result(self):
        """Mensajes de tool_result con metadata role='tool' se mapean a 'tool'."""
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.SYSTEM,
            content=[{"type": "tool_result", "tool_name": "zoomTo", "content": {}, "success": True, "tool_call_id": "call_123"}],
            metadata={"role": "tool", "tool_call_id": "call_123", "tool_name": "zoomTo"},
        )
        result = _build_history(self.conversation)
        self.assertEqual(result[0]["role"], "tool")
        self.assertEqual(result[0]["tool_call_id"], "call_123")

    def test_role_mapping_assistant(self):
        """Mensajes con role ASSISTANT se mapean a 'assistant'."""
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content=[{"type": "text", "text": "respuesta"}],
        )
        result = _build_history(self.conversation)
        self.assertEqual(result[0]["role"], "assistant")

    def test_role_mapping_tool(self):
        """Mensajes con metadata role='tool' se remapean a 'tool' con tool_call_id."""
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.SYSTEM,
            content='{"tool": "zoomTo", "result": {}, "success": true}',
            metadata={
                "role": "tool",
                "tool_call_id": "call_123",
                "tool_name": "zoomTo",
            },
        )
        result = _build_history(self.conversation)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "tool")
        self.assertEqual(result[0]["tool_call_id"], "call_123")

    def test_metadata_tool_calls_included(self):
        """Mensajes con metadata.tool_calls incluyen el campo tool_calls."""
        tool_calls = [
            {"name": "zoomTo", "args": {"lat": 40.0, "lon": -3.0}, "id": "call_456"}
        ]
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content=[{"type": "text", "text": "Moviendo el mapa..."}],
            metadata={"tool_calls": tool_calls},
        )
        result = _build_history(self.conversation)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["role"], "assistant")
        self.assertEqual(result[0]["tool_calls"], tool_calls)

    def test_metadata_without_tool_calls_excluded(self):
        """Mensajes sin metadata.tool_calls no incluyen el campo tool_calls."""
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content="Texto normal",
            metadata={"sources": []},
        )
        result = _build_history(self.conversation)
        self.assertNotIn("tool_calls", result[0])

    def test_all_messages_within_limit_returned(self):
        """Si hay menos mensajes que el límite, se devuelven todos."""
        for i in range(10):
            Message.objects.create(
                conversation=self.conversation,
                role=Message.Role.USER,
                content=[{"type": "text", "text": f"Msg {i}"}],
            )
        result = _build_history(self.conversation)
        self.assertEqual(len(result), 10)


class MakeAgentCacheTests(TestCase):
    """Tests para la función ``_make_agent`` y su caché ``_agent_cache``."""

    def setUp(self):
        """Limpia la caché de agentes antes de cada test."""
        _agent_cache.clear()

    def tearDown(self):
        """Limpia la caché de agentes después de cada test."""
        _agent_cache.clear()

    @patch("agent.views.Agent")
    def test_same_params_return_same_object(self, mock_agent_cls):
        """Dos llamadas con los mismos parámetros devuelven el mismo objeto."""
        mock_agent_cls.return_value = MagicMock(name="agent_instance")

        agent1 = _make_agent("openai", "gpt-4o", "sk-test")
        agent2 = _make_agent("openai", "gpt-4o", "sk-test")

        self.assertIs(agent1, agent2)
        mock_agent_cls.assert_called_once()

    @patch("agent.views.Agent")
    def test_different_params_create_different_objects(self, mock_agent_cls):
        """Parámetros diferentes crean objetos distintos."""
        mock_agent_cls.side_effect = lambda **kw: MagicMock(name=f"agent_{kw}")

        agent1 = _make_agent("openai", "gpt-4o", "sk-test1")
        agent2 = _make_agent("gemini", "gemini-pro", "key-test2")

        self.assertIsNot(agent1, agent2)
        self.assertEqual(mock_agent_cls.call_count, 2)

    @patch("agent.views.Agent")
    def test_different_model_creates_new_agent(self, mock_agent_cls):
        """Cambiar solo el modelo crea un agente nuevo."""
        mock_agent_cls.side_effect = lambda **kw: MagicMock()

        agent1 = _make_agent("openai", "gpt-4o", "sk-test")
        agent2 = _make_agent("openai", "gpt-4o-mini", "sk-test")

        self.assertIsNot(agent1, agent2)
        self.assertEqual(mock_agent_cls.call_count, 2)

    @patch("agent.views.Agent")
    def test_different_api_key_creates_new_agent(self, mock_agent_cls):
        """Cambiar solo la API key crea un agente nuevo."""
        mock_agent_cls.side_effect = lambda **kw: MagicMock()

        agent1 = _make_agent("openai", "gpt-4o", "sk-key-1")
        agent2 = _make_agent("openai", "gpt-4o", "sk-key-2")

        self.assertIsNot(agent1, agent2)
        self.assertEqual(mock_agent_cls.call_count, 2)

    @patch("agent.views.Agent")
    def test_cache_is_populated(self, mock_agent_cls):
        """Tras llamar a _make_agent, la caché contiene la entrada."""
        mock_agent_cls.return_value = MagicMock()

        _make_agent("openai", "gpt-4o", "sk-test")

        cache_key = ("openai", "gpt-4o", "sk-test")
        self.assertIn(cache_key, _agent_cache)

    @patch("agent.views.Agent")
    def test_agent_constructed_with_correct_params(self, mock_agent_cls):
        """_make_agent pasa provider_name, model y api_key al constructor de Agent."""
        mock_agent_cls.return_value = MagicMock()

        _make_agent("gemini", "gemini-pro", "AIza-test")

        mock_agent_cls.assert_called_once_with(
            provider_name="gemini", model="gemini-pro", api_key="AIza-test"
        )


class AssistantResponseLayersTests(TestCase):
    """Tests para la propagación de layers GeoJSON en _assistant_response."""

    def setUp(self):
        self.conversation = Conversation.objects.create(title="Layers test")

    def test_layers_se_incluyen_en_respuesta(self):
        """Las capas GeoJSON de result.layers se añaden como bloques layer al content."""
        from agent.agent import AgentResponse
        from agent.views import _assistant_response

        geojson = {"type": "FeatureCollection", "features": []}
        result = AgentResponse.text(
            "Detección completada",
            layers=[{"type": "geojson", "source": geojson, "name": "Piscinas"}],
        )
        response = _assistant_response(self.conversation, result)
        content = response.data["content"]

        layer_blocks = [b for b in content if b.get("type") == "layer"]
        self.assertEqual(len(layer_blocks), 1)
        self.assertEqual(layer_blocks[0]["layer"]["name"], "Piscinas")
        self.assertEqual(layer_blocks[0]["layer"]["type"], "geojson")

    def test_sin_layers_no_hay_bloques_layer(self):
        """Sin layers, la respuesta no contiene bloques layer."""
        from agent.agent import AgentResponse
        from agent.views import _assistant_response

        result = AgentResponse.text("Respuesta normal")
        response = _assistant_response(self.conversation, result)
        content = response.data["content"]

        layer_blocks = [b for b in content if b.get("type") == "layer"]
        self.assertEqual(len(layer_blocks), 0)

    def test_multiples_layers(self):
        """Múltiples layers se añaden como bloques separados."""
        from agent.agent import AgentResponse
        from agent.views import _assistant_response

        result = AgentResponse.text(
            "Varias detecciones",
            layers=[
                {"type": "geojson", "source": {}, "name": "Piscinas"},
                {"type": "geojson", "source": {}, "name": "Edificios"},
            ],
        )
        response = _assistant_response(self.conversation, result)
        content = response.data["content"]

        layer_blocks = [b for b in content if b.get("type") == "layer"]
        self.assertEqual(len(layer_blocks), 2)
        names = {b["layer"]["name"] for b in layer_blocks}
        self.assertEqual(names, {"Piscinas", "Edificios"})


class StreamingChatTests(TestCase):
    """Tests para el endpoint chat con stream=true."""

    def setUp(self):
        self.client = APIClient()
        self.conversation = Conversation.objects.create(title="Stream test")

    @patch("agent.views._make_agent")
    def test_stream_true_devuelve_event_stream(self, mock_make_agent):
        """POST chat/ con stream=true devuelve content-type text/event-stream."""
        mock_agent = MagicMock()
        mock_agent.run_stream.return_value = iter([
            {"type": "text_delta", "text": "Hola"},
            {"type": "done"},
        ])
        mock_make_agent.return_value = mock_agent

        url = f"/api/conversations/{self.conversation.id}/chat/"
        response = self.client.post(url, {"content": "Test", "stream": True}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response["Content-Type"])

    @patch("agent.views._make_agent")
    def test_stream_true_contiene_eventos_sse(self, mock_make_agent):
        """La respuesta SSE contiene eventos text_delta y done."""
        mock_agent = MagicMock()
        mock_agent.run_stream.return_value = iter([
            {"type": "text_delta", "text": "Hola "},
            {"type": "text_delta", "text": "mundo"},
            {"type": "done"},
        ])
        mock_make_agent.return_value = mock_agent

        url = f"/api/conversations/{self.conversation.id}/chat/"
        response = self.client.post(url, {"content": "Test", "stream": True}, format="json")

        content = b"".join(response.streaming_content).decode("utf-8")
        self.assertIn("event: text_delta", content)
        self.assertIn('"text": "Hola "', content)
        self.assertIn("event: done", content)

    @patch("agent.views._make_agent")
    def test_stream_false_devuelve_json_normal(self, mock_make_agent):
        """POST chat/ con stream=false devuelve JSON como siempre."""
        from agent.agent import AgentResponse
        mock_agent = MagicMock()
        mock_agent.run.return_value = AgentResponse.text("Respuesta normal")
        mock_make_agent.return_value = mock_agent

        url = f"/api/conversations/{self.conversation.id}/chat/"
        response = self.client.post(url, {"content": "Test", "stream": False}, format="json")

        self.assertEqual(response.status_code, 201)
        self.assertIn("application/json", response["Content-Type"])

    @patch("agent.views._make_agent")
    def test_stream_persiste_mensaje_asistente(self, mock_make_agent):
        """El stream persiste el mensaje del asistente al terminar."""
        mock_agent = MagicMock()
        mock_agent.run_stream.return_value = iter([
            {"type": "text_delta", "text": "Texto completo"},
            {"type": "done"},
        ])
        mock_make_agent.return_value = mock_agent

        url = f"/api/conversations/{self.conversation.id}/chat/"
        response = self.client.post(url, {"content": "Test", "stream": True}, format="json")
        # Consumir el stream para que se persista
        b"".join(response.streaming_content)

        # Verificar que se persistieron 2 mensajes (user + assistant)
        msgs = list(self.conversation.messages.all())
        self.assertEqual(len(msgs), 2)
        self.assertEqual(msgs[0].role, "user")
        self.assertEqual(msgs[1].role, "assistant")


class ConversationByIdsTests(TestCase):
    """Tests para el endpoint POST conversations/by-ids/."""

    def setUp(self):
        self.client = APIClient()
        self.conv1 = Conversation.objects.create(title="Conv 1")
        self.conv2 = Conversation.objects.create(title="Conv 2")
        self.conv3 = Conversation.objects.create(title="Conv 3")

    def test_devuelve_solo_ids_pedidos(self):
        """Solo devuelve las conversaciones cuyos IDs se pasan."""
        url = "/api/conversations/by-ids/"
        response = self.client.post(
            url, {"ids": [str(self.conv1.id), str(self.conv3.id)]}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        ids_devueltos = {c["id"] for c in response.data}
        self.assertEqual(ids_devueltos, {str(self.conv1.id), str(self.conv3.id)})

    def test_ids_vacios_devuelve_lista_vacia(self):
        """Con lista vacía de IDs devuelve lista vacía."""
        response = self.client.post("/api/conversations/by-ids/", {"ids": []}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_sin_campo_ids_devuelve_lista_vacia(self):
        """Sin campo 'ids' devuelve lista vacía."""
        response = self.client.post("/api/conversations/by-ids/", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_id_inexistente_se_ignora(self):
        """IDs que no existen se ignoran sin error."""
        response = self.client.post(
            "/api/conversations/by-ids/",
            {"ids": [str(self.conv1.id), "00000000-0000-0000-0000-000000000000"]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], str(self.conv1.id))


class ConversationConfigTests(TestCase):
    """Tests para el endpoint GET conversation-config/."""

    def test_devuelve_ttl_y_max(self):
        """Devuelve ttl_hours y max_per_client."""
        client = APIClient()
        response = client.get("/api/conversation-config/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ttl_hours", response.data)
        self.assertIn("max_per_client", response.data)
        self.assertIsInstance(response.data["ttl_hours"], int)
        self.assertIsInstance(response.data["max_per_client"], int)


class LazyCleanupTests(TestCase):
    """Tests para la limpieza lazy de conversaciones expiradas."""

    def test_conversaciones_expiradas_se_borran(self):
        """Conversaciones con updated_at anterior al TTL se eliminan."""
        from agent.views import _lazy_cleanup, _last_cleanup_time
        import agent.views as views_module

        # Crear conversación expirada (forzar updated_at antiguo)
        conv = Conversation.objects.create(title="Expirada")
        Conversation.objects.filter(id=conv.id).update(
            updated_at=timezone.now() - timedelta(hours=999)
        )

        # Forzar que la limpieza se ejecute
        views_module._last_cleanup_time = 0.0
        _lazy_cleanup()

        self.assertFalse(Conversation.objects.filter(id=conv.id).exists())

    def test_conversaciones_recientes_no_se_borran(self):
        """Conversaciones recientes no se eliminan."""
        from agent.views import _lazy_cleanup
        import agent.views as views_module

        conv = Conversation.objects.create(title="Reciente")

        views_module._last_cleanup_time = 0.0
        _lazy_cleanup()

        self.assertTrue(Conversation.objects.filter(id=conv.id).exists())


class ToolResultEndpointTests(TestCase):
    """Tests para el endpoint POST tool-result/."""

    def setUp(self):
        self.client = APIClient()
        self.conversation = Conversation.objects.create(title="Tool result test")
        # Crear un mensaje previo del usuario y del asistente con tool_call
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content=[{"type": "text", "text": "Llévame a Madrid"}],
        )
        Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.ASSISTANT,
            content=[{"type": "text", "text": "Moviendo el mapa..."}],
            metadata={"tool_calls": [{"name": "geocodePlace", "args": {"q": "Madrid"}, "id": "call_1"}]},
        )

    def test_tool_result_con_geojson_url_devuelve_layer(self):
        """POST tool-result con geojsonURL devuelve respuesta layer directamente."""
        url = f"/api/conversations/{self.conversation.id}/tool-result/"
        data = {
            "tool_name": "geocodePlace",
            "tool_call_id": "call_1",
            "result": {"geojsonURL": "http://example.com/geo.json", "name": "Madrid"},
            "success": True,
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        content = response.data["content"]
        layer_blocks = [b for b in content if b.get("type") == "layer"]
        self.assertEqual(len(layer_blocks), 1)
        self.assertEqual(layer_blocks[0]["layer"]["url"], "http://example.com/geo.json")
        self.assertEqual(layer_blocks[0]["layer"]["name"], "Madrid")

    @patch("agent.views._make_agent")
    def test_tool_result_normal_delega_al_agent(self, mock_make_agent):
        """POST tool-result sin geojsonURL delega al Agent.process_tool_result."""
        from agent.agent import AgentResponse

        mock_agent = MagicMock()
        mock_agent.process_tool_result.return_value = AgentResponse.text(
            "El mapa se ha movido a Madrid correctamente."
        )
        mock_make_agent.return_value = mock_agent

        url = f"/api/conversations/{self.conversation.id}/tool-result/"
        data = {
            "tool_name": "zoomTo",
            "tool_call_id": "call_1",
            "result": {"success": True},
            "success": True,
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_agent.process_tool_result.assert_called_once()
        content = response.data["content"]
        text_blocks = [b for b in content if b.get("type") == "text"]
        self.assertTrue(any("Madrid" in b.get("text", "") for b in text_blocks))

    @patch("agent.views._make_agent")
    def test_tool_result_con_success_false(self, mock_make_agent):
        """POST tool-result con success=False sigue funcionando correctamente."""
        from agent.agent import AgentResponse

        mock_agent = MagicMock()
        mock_agent.process_tool_result.return_value = AgentResponse.text(
            "La herramienta falló, pero puedo intentar otra cosa."
        )
        mock_make_agent.return_value = mock_agent

        url = f"/api/conversations/{self.conversation.id}/tool-result/"
        data = {
            "tool_name": "zoomTo",
            "tool_call_id": "call_1",
            "result": {"error": "Permission denied"},
            "success": False,
        }
        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_agent.process_tool_result.assert_called_once()
