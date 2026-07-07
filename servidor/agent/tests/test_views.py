"""
Tests de integración para las views del agente.

Cubre los endpoints REST del ConversationViewSet (CRUD + messages),
las funciones auxiliares ``_build_history`` y ``_make_agent``, y
verifica que no se realizan llamadas reales al LLM.
"""
from unittest.mock import MagicMock, patch

from django.test import TestCase
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
        self.assertEqual(response.data[0]["content"], "primero")
        self.assertEqual(response.data[1]["content"], "segundo")


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
            role=Message.Role.SYSTEM,
            content=[{"type": "tool_result", "tool_name": "zoomTo", "content": {}, "success": true, "tool_call_id": "call_123"}],
            metadata={"role": "tool", "tool_call_id": "call_123", "tool_name": "zoomTo"},
        )
        result = _build_history(self.conversation)
        self.assertEqual(result[0]["role"], "user")

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
