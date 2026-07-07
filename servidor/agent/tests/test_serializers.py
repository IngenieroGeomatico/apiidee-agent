from django.test import TestCase

from agent.models import Conversation, Message
from agent.serializers import (
    ChatInputSerializer,
    ConversationSerializer,
    MessageSerializer,
    ToolResultSerializer,
)


class ChatInputSerializerTest(TestCase):
    """Tests para el serializador de entrada del chat."""

    def test_content_requerido(self):
        """Verifica que el campo content es obligatorio."""
        serializer = ChatInputSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("content", serializer.errors)

    def test_content_valido(self):
        """Verifica que un content válido pasa la validación."""
        serializer = ChatInputSerializer(data={"content": "Hola mundo"})
        self.assertTrue(serializer.is_valid())

    def test_content_vacio_es_invalido(self):
        """Verifica que un content vacío no pasa la validación."""
        serializer = ChatInputSerializer(data={"content": ""})
        self.assertFalse(serializer.is_valid())
        self.assertIn("content", serializer.errors)

    def test_content_mayor_10000_chars_es_invalido(self):
        """Verifica que un content con más de 10000 caracteres es inválido."""
        contenido = "A" * 10001
        serializer = ChatInputSerializer(data={"content": contenido})
        self.assertFalse(serializer.is_valid())
        self.assertIn("content", serializer.errors)

    def test_content_exacto_10000_chars_es_valido(self):
        """Verifica que un content de exactamente 10000 caracteres es válido."""
        contenido = "A" * 10000
        serializer = ChatInputSerializer(data={"content": contenido})
        self.assertTrue(serializer.is_valid())

    def test_map_state_opcional(self):
        """Verifica que map_state es opcional y su valor por defecto es None."""
        serializer = ChatInputSerializer(data={"content": "Hola"})
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("map_state"))

    def test_provider_opcional(self):
        """Verifica que provider es opcional y su valor por defecto es None."""
        serializer = ChatInputSerializer(data={"content": "Hola"})
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("provider"))

    def test_model_opcional(self):
        """Verifica que model es opcional y su valor por defecto es None."""
        serializer = ChatInputSerializer(data={"content": "Hola"})
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("model"))

    def test_api_key_opcional(self):
        """Verifica que api_key es opcional y su valor por defecto es None."""
        serializer = ChatInputSerializer(data={"content": "Hola"})
        self.assertTrue(serializer.is_valid())
        self.assertIsNone(serializer.validated_data.get("api_key"))

    def test_todos_los_campos_opcionales(self):
        """Verifica que todos los campos opcionales se serializan correctamente."""
        data = {
            "content": "Llévame a Madrid",
            "map_state": {"center": {"lat": 40.4, "lon": -3.7}, "zoom": 5},
            "provider": "gemini",
            "model": "gemini-pro",
            "api_key": "AIza_test_key",
        }
        serializer = ChatInputSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["provider"], "gemini")
        self.assertEqual(serializer.validated_data["model"], "gemini-pro")


class ToolResultSerializerTest(TestCase):
    """Tests para el serializador de resultados de herramientas."""

    def test_tool_name_requerido(self):
        """Verifica que tool_name es obligatorio."""
        serializer = ToolResultSerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("tool_name", serializer.errors)

    def test_tool_name_valido(self):
        """Verifica que con tool_name válido pasa la validación."""
        serializer = ToolResultSerializer(data={"tool_name": "zoomTo"})
        self.assertTrue(serializer.is_valid())

    def test_result_opcional_default_dict(self):
        """Verifica que result es opcional y por defecto es un dict vacío."""
        serializer = ToolResultSerializer(data={"tool_name": "getMapCenter"})
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data.get("result"), {})

    def test_success_opcional_default_true(self):
        """Verifica que success es opcional y por defecto es True."""
        serializer = ToolResultSerializer(data={"tool_name": "zoomTo"})
        self.assertTrue(serializer.is_valid())
        self.assertTrue(serializer.validated_data.get("success"))

    def test_todos_los_campos(self):
        """Verifica la serialización con todos los campos proporcionados."""
        data = {
            "tool_name": "zoomTo",
            "tool_call_id": "call_abc123",
            "result": {"success": True, "center": {"lat": 40.4, "lon": -3.7}},
            "success": False,
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "sk-test",
        }
        serializer = ToolResultSerializer(data=data)
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data["tool_name"], "zoomTo")
        self.assertFalse(serializer.validated_data["success"])


class ConversationSerializerTest(TestCase):
    """Tests para el serializador de conversaciones."""

    def test_incluye_message_count(self):
        """Verifica que el serializador incluye el conteo de mensajes."""
        conv = Conversation.objects.create(title="Test conteo")
        Message.objects.create(
            conversation=conv, role=Message.Role.USER, content="Msg 1"
        )
        Message.objects.create(
            conversation=conv, role=Message.Role.ASSISTANT, content="Msg 2"
        )
        serializer = ConversationSerializer(conv)
        self.assertEqual(serializer.data["message_count"], 2)

    def test_message_count_cero_sin_mensajes(self):
        """Verifica que message_count es 0 cuando no hay mensajes."""
        conv = Conversation.objects.create(title="Sin mensajes")
        serializer = ConversationSerializer(conv)
        self.assertEqual(serializer.data["message_count"], 0)

    def test_campos_correctos(self):
        """Verifica que los campos del serializador son los esperados."""
        conv = Conversation.objects.create(title="Campos")
        serializer = ConversationSerializer(conv)
        campos_esperados = {"id", "title", "created_at", "updated_at", "message_count"}
        self.assertEqual(set(serializer.data.keys()), campos_esperados)

    def test_id_es_read_only(self):
        """Verifica que id, created_at y updated_at son de solo lectura."""
        campos_ro = ConversationSerializer.Meta.read_only_fields
        self.assertIn("id", campos_ro)
        self.assertIn("created_at", campos_ro)
        self.assertIn("updated_at", campos_ro)


class MessageSerializerTest(TestCase):
    """Tests para el serializador de mensajes."""

    def setUp(self):
        """Crea una conversación y un mensaje de prueba."""
        self.conversation = Conversation.objects.create(title="Test serializer")
        self.message = Message.objects.create(
            conversation=self.conversation,
            role=Message.Role.USER,
            content=[{"type": "text", "text": "Contenido de prueba"}],
            metadata={"key": "value"},
        )

    def test_campos_correctos(self):
        """Verifica que los campos del serializador son los esperados."""
        serializer = MessageSerializer(self.message)
        campos_esperados = {"id", "role", "content", "created_at", "metadata"}
        self.assertEqual(set(serializer.data.keys()), campos_esperados)

    def test_id_es_read_only(self):
        """Verifica que id y created_at son de solo lectura."""
        campos_ro = MessageSerializer.Meta.read_only_fields
        self.assertIn("id", campos_ro)
        self.assertIn("created_at", campos_ro)

    def test_contenido_serializado(self):
        """Verifica que el contenido se serializa correctamente."""
        serializer = MessageSerializer(self.message)
        self.assertEqual(serializer.data["content"], [{"type": "text", "text": "Contenido de prueba"}])
        self.assertEqual(serializer.data["role"], "user")
        self.assertEqual(serializer.data["metadata"], {"key": "value"})
