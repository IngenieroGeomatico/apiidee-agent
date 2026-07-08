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


class OpenAICompatibleProviderInitTest(TestCase):
    """Verifica OpenAICompatibleProvider.__init__ crea ChatOpenAI con parámetros correctos."""

    @patch("agent.llm.providers.ChatOpenAI", create=True)
    def test_init_crea_chatopenai(self, MockChatOpenAI):
        """OpenAICompatibleProvider.__init__ crea ChatOpenAI con base_url, api_key y model."""
        # Patcheamos el import dentro del módulo
        with patch("agent.llm.providers.OpenAICompatibleProvider.__init__", wraps=None) as _:
            pass

        # Importar y patchear directamente
        from agent.llm.providers import OpenAICompatibleProvider
        with patch("langchain_openai.ChatOpenAI") as MockChat:
            mock_instance = MagicMock()
            MockChat.return_value = mock_instance

            provider = OpenAICompatibleProvider(
                base_url="https://api.groq.com/openai/v1",
                api_key="gsk-test-key",
                model="llama-3.1-70b",
            )

            MockChat.assert_called_once_with(
                model="llama-3.1-70b",
                api_key="gsk-test-key",
                base_url="https://api.groq.com/openai/v1",
                temperature=0.1,
            )
            self.assertEqual(provider.model, "llama-3.1-70b")
            self.assertIs(provider.llm, mock_instance)


class GeminiProviderInitTest(TestCase):
    """Verifica GeminiProvider.__init__ crea ChatGoogleGenerativeAI."""

    @patch("agent.llm.providers.settings")
    def test_init_crea_chat_google(self, mock_settings):
        """GeminiProvider.__init__ crea ChatGoogleGenerativeAI con la API key de settings."""
        import sys
        import types

        mock_settings.GOOGLE_API_KEY = "AIza-test-key"
        mock_settings.LLM_MODEL = "gemini-pro"

        # Crear módulo fake para langchain_google_genai si no existe
        mock_chat_cls = MagicMock()
        mock_instance = MagicMock()
        mock_chat_cls.return_value = mock_instance

        fake_module = types.ModuleType("langchain_google_genai")
        fake_module.ChatGoogleGenerativeAI = mock_chat_cls
        was_present = "langchain_google_genai" in sys.modules
        sys.modules["langchain_google_genai"] = fake_module

        try:
            # Forzar re-importación limpia del import dentro de __init__
            from agent.llm.providers import GeminiProvider
            provider = GeminiProvider()

            mock_chat_cls.assert_called_once_with(
                model="gemini-pro",
                google_api_key="AIza-test-key",
                temperature=0.1,
            )
            self.assertIs(provider.llm, mock_instance)
        finally:
            if not was_present:
                del sys.modules["langchain_google_genai"]


class OpenAIProviderInitTest(TestCase):
    """Verifica OpenAIProvider.__init__ lanza ValueError sin API key."""

    @patch("agent.llm.providers.settings")
    def test_sin_api_key_lanza_value_error(self, mock_settings):
        """OpenAIProvider.__init__ lanza ValueError cuando OPENAI_API_KEY está vacía."""
        mock_settings.OPENAI_API_KEY = ""

        from agent.llm.providers import OpenAIProvider
        with self.assertRaises(ValueError) as ctx:
            OpenAIProvider()
        self.assertIn("OPENAI_API_KEY", str(ctx.exception))


class GetProviderTest(TestCase):
    """Verifica get_provider() busca y crea proveedores por nombre."""

    @patch("agent.llm.config.settings")
    @patch("agent.llm.config.OpenAICompatibleProvider")
    def test_encuentra_proveedor_por_nombre(self, MockProvider, mock_settings):
        """get_provider() busca el proveedor en LLM_PROVIDERS y crea OpenAICompatibleProvider."""
        mock_settings.LLM_PROVIDERS = [
            {"name": "groq", "base_url": "https://api.groq.com/openai/v1",
             "api_key": "gsk-default", "default_model": "llama-3.1-70b"},
        ]
        mock_instance = MagicMock()
        MockProvider.return_value = mock_instance

        from agent.llm.config import get_provider
        result = get_provider("groq", "llama-3.1-70b")

        MockProvider.assert_called_once_with(
            base_url="https://api.groq.com/openai/v1",
            api_key="gsk-default",
            model="llama-3.1-70b",
        )
        self.assertIs(result, mock_instance)

    @patch("agent.llm.config.settings")
    def test_proveedor_desconocido_lanza_value_error(self, mock_settings):
        """get_provider() lanza ValueError para un proveedor no configurado."""
        mock_settings.LLM_PROVIDERS = [
            {"name": "groq", "base_url": "https://api.groq.com/openai/v1",
             "api_key": "gsk-test", "default_model": "llama"},
        ]

        from agent.llm.config import get_provider
        with self.assertRaises(ValueError) as ctx:
            get_provider("unknown_provider", "model-x")
        self.assertIn("Unknown provider", str(ctx.exception))


class GetLlmProviderFallbackTest(TestCase):
    """Verifica get_llm_provider() con fallback al proveedor legacy."""

    @patch("agent.llm.config.settings")
    @patch("agent.llm.config.GeminiProvider")
    def test_fallback_a_proveedor_legacy(self, MockGemini, mock_settings):
        """get_llm_provider() usa el registro legacy cuando LLM_PROVIDERS está vacío."""
        mock_settings.LLM_PROVIDERS = []
        mock_settings.LLM_PROVIDER = "gemini"
        mock_instance = MagicMock()
        MockGemini.return_value = mock_instance

        from agent.llm.config import get_llm_provider
        result = get_llm_provider()

        MockGemini.assert_called_once()
        self.assertIs(result, mock_instance)
