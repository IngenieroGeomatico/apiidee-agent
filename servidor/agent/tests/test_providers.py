"""Tests unitarios para los proveedores LLM (providers.py).

Cubre ChatResponse, BaseLLMProvider._convert_message y
BaseLLMProvider.chat() con mocks (sin llamadas a APIs reales).
"""
from django.test import TestCase
from unittest.mock import MagicMock, patch

from agent.llm.providers import ChatResponse, BaseLLMProvider


class ChatResponseSinToolCallsTest(TestCase):
    """Verifica ChatResponse cuando no hay tool_calls."""

    def test_has_tool_calls_es_false(self):
        """Una respuesta sin tool_calls debe indicar has_tool_calls=False."""
        resp = ChatResponse(content="Hola mundo")
        self.assertFalse(resp.has_tool_calls)
        self.assertEqual(resp.content, "Hola mundo")
        self.assertEqual(resp.tool_calls, [])


class ChatResponseConToolCallsTest(TestCase):
    """Verifica ChatResponse cuando hay tool_calls."""

    def test_has_tool_calls_es_true(self):
        """Una respuesta con tool_calls debe indicar has_tool_calls=True."""
        calls = [{"name": "zoomTo", "args": {"lat": 40.0}, "id": "tc1"}]
        resp = ChatResponse(content="Moviendo...", tool_calls=calls)
        self.assertTrue(resp.has_tool_calls)
        self.assertEqual(len(resp.tool_calls), 1)
        self.assertEqual(resp.tool_calls[0]["name"], "zoomTo")


class ConvertMessageTest(TestCase):
    """Verifica _convert_message para cada rol posible."""

    def test_system_message(self):
        """Un mensaje con role='system' debe convertirse a SystemMessage."""
        from langchain_core.messages import SystemMessage
        msg = {"role": "system", "content": "Eres un asistente."}
        result = BaseLLMProvider._convert_message(msg)
        self.assertIsInstance(result, SystemMessage)
        self.assertEqual(result.content, "Eres un asistente.")

    def test_user_message(self):
        """Un mensaje con role='user' debe convertirse a HumanMessage."""
        from langchain_core.messages import HumanMessage
        msg = {"role": "user", "content": "Hola"}
        result = BaseLLMProvider._convert_message(msg)
        self.assertIsInstance(result, HumanMessage)
        self.assertEqual(result.content, "Hola")

    def test_assistant_message(self):
        """Un mensaje con role='assistant' sin tool_calls → AIMessage."""
        from langchain_core.messages import AIMessage
        msg = {"role": "assistant", "content": "Respuesta"}
        result = BaseLLMProvider._convert_message(msg)
        self.assertIsInstance(result, AIMessage)
        self.assertEqual(result.content, "Respuesta")

    def test_assistant_con_tool_calls(self):
        """Un mensaje assistant con tool_calls debe incluirlos en AIMessage."""
        from langchain_core.messages import AIMessage
        tc = [{"name": "zoomTo", "args": {"lat": 40}, "id": "tc1"}]
        msg = {"role": "assistant", "content": "", "tool_calls": tc}
        result = BaseLLMProvider._convert_message(msg)
        self.assertIsInstance(result, AIMessage)
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0]["name"], "zoomTo")
        self.assertEqual(result.tool_calls[0]["args"], {"lat": 40})
        self.assertEqual(result.tool_calls[0]["id"], "tc1")

    def test_tool_message(self):
        """Un mensaje con role='tool' debe convertirse a ToolMessage."""
        from langchain_core.messages import ToolMessage
        msg = {"role": "tool", "content": '{"ok": true}', "tool_call_id": "tc1"}
        result = BaseLLMProvider._convert_message(msg)
        self.assertIsInstance(result, ToolMessage)
        self.assertEqual(result.tool_call_id, "tc1")


class BaseLLMProviderChatTest(TestCase):
    """Verifica BaseLLMProvider.chat() con mock del LLM subyacente."""

    def _make_provider(self):
        """Crea un BaseLLMProvider con self.llm mockeado."""
        provider = BaseLLMProvider()
        provider.llm = MagicMock()
        return provider

    def test_chat_sin_tool_calls(self):
        """Respuesta del LLM sin tool_calls devuelve ChatResponse con texto."""
        provider = self._make_provider()

        mock_response = MagicMock()
        mock_response.content = "Madrid es la capital."
        mock_response.tool_calls = []
        provider.llm.invoke.return_value = mock_response

        messages = [{"role": "user", "content": "¿Qué es Madrid?"}]
        result = provider.chat(messages)

        self.assertIsInstance(result, ChatResponse)
        self.assertEqual(result.content, "Madrid es la capital.")
        self.assertFalse(result.has_tool_calls)
        provider.llm.invoke.assert_called_once()

    def test_chat_con_tool_calls(self):
        """Respuesta del LLM con tool_calls devuelve ChatResponse con herramientas."""
        provider = self._make_provider()

        mock_response = MagicMock()
        mock_response.content = "Moviendo el mapa..."
        mock_response.tool_calls = [
            {"name": "zoomTo", "args": {"lat": 40.4, "lon": -3.7}, "id": "call_1"}
        ]
        provider.llm.invoke.return_value = mock_response

        messages = [{"role": "user", "content": "Llévame a Madrid"}]
        result = provider.chat(messages)

        self.assertIsInstance(result, ChatResponse)
        self.assertTrue(result.has_tool_calls)
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0]["name"], "zoomTo")
        self.assertEqual(result.tool_calls[0]["id"], "call_1")

    def test_chat_con_tools_llama_bind_tools(self):
        """Cuando se pasan tools, debe llamar a bind_tools en el LLM."""
        provider = self._make_provider()

        mock_bound = MagicMock()
        mock_response = MagicMock()
        mock_response.content = "Ok"
        mock_response.tool_calls = []
        mock_bound.invoke.return_value = mock_response
        provider.llm.bind_tools.return_value = mock_bound

        tools = [{"name": "zoomTo", "description": "Zoom", "parameters": {}}]
        messages = [{"role": "user", "content": "Hola"}]
        result = provider.chat(messages, tools=tools)

        provider.llm.bind_tools.assert_called_once_with(tools)
        mock_bound.invoke.assert_called_once()
        self.assertEqual(result.content, "Ok")
