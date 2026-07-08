"""Tests unitarios para la clase Agent y AgentResponse (agent.py).

Cubre inicialización de AgentResponse, formateo de contexto RAG,
construcción del system prompt, formateo de resultados MCP y
creación del Agent con dependencias mockeadas.
"""
import json

from django.test import TestCase
from unittest.mock import patch, MagicMock

from agent.agent import AgentResponse, Agent
from agent.prompts import SYSTEM_PROMPT


class AgentResponseDefaultsTest(TestCase):
    """Verifica la inicialización de AgentResponse con valores por defecto."""

    def test_inicializacion_defaults(self):
        """AgentResponse sin argumentos opcionales usa listas vacías y type='text'."""
        resp = AgentResponse.text("Hola")
        self.assertEqual(resp.content, [{"type": "text", "text": "Hola"}])
        self.assertEqual(resp.tool_calls, [])
        self.assertEqual(resp.sources, [])


class AgentResponseConToolCallsTest(TestCase):
    """Verifica AgentResponse cuando se incluyen tool_calls."""

    def test_con_tool_calls(self):
        """AgentResponse con tool_calls debe almacenarlos y marcar type='tool_call'."""
        tc = [{"name": "zoomTo", "args": {"lat": 40.4}, "id": "tc1"}]
        resp = AgentResponse.tool_call(
            text="Moviendo...",
            tool_calls=tc,
            sources=[{"source": "file.py"}],
        )
        # Verify that a tool_call block is present
        tool_blocks = [b for b in resp.content if b.get("type") == "tool_call"]
        self.assertEqual(len(tool_blocks), 1)
        self.assertEqual(tool_blocks[0]["toolCalls"], tc)
        self.assertEqual(resp.sources, [{"source": "file.py"}])


class FormatRagContextTest(TestCase):
    """Verifica Agent._format_rag_context() con y sin resultados."""

    def test_sin_resultados(self):
        """Sin resultados RAG debe devolver mensaje de 'no context'."""
        result = Agent._format_rag_context([])
        self.assertEqual(result, "No additional context available.")

    def test_con_resultados(self):
        """Con resultados RAG debe formatear cada chunk con su fuente."""
        chunks = [
            {"content": "código de ejemplo", "metadata": {"source": "map.js"}},
            {"content": "más código", "metadata": {"source": "layer.py"}},
        ]
        result = Agent._format_rag_context(chunks)

        self.assertIn("Relevant context from the API-IDEE codebase:", result)
        self.assertIn("--- Source 1: map.js ---", result)
        self.assertIn("código de ejemplo", result)
        self.assertIn("--- Source 2: layer.py ---", result)
        self.assertIn("más código", result)


class BuildSystemPromptTest(TestCase):
    """Verifica Agent._build_system_prompt() con y sin map_state."""

    def _make_agent(self):
        """Crea un Agent con todas las dependencias mockeadas."""
        with patch("agent.agent.SkillRegistry") as MockRegistry, \
             patch("agent.agent.get_llm_provider") as mock_llm, \
             patch("agent.agent.get_provider") as mock_prov, \
             patch("agent.agent.Agent._init_mcp") as mock_mcp:
            mock_mcp.return_value = None
            registry_instance = MagicMock()
            registry_instance.get_system_prompt.return_value = "Skills: navegación"
            MockRegistry.return_value = registry_instance
            mock_llm.return_value = MagicMock()
            agent = Agent()
        return agent

    def test_sin_map_state(self):
        """Sin map_state, el prompt debe contener contexto y skills pero no JSON de mapa."""
        agent = self._make_agent()
        rag_results = [
            {"content": "chunk1", "metadata": {"source": "src.js"}},
        ]
        prompt = agent._build_system_prompt(rag_results)

        self.assertIn("chunk1", prompt)
        self.assertIn("Skills: navegación", prompt)
        self.assertNotIn("Current map state", prompt)

    def test_con_map_state(self):
        """Con map_state, el prompt debe incluir el JSON del estado del mapa."""
        agent = self._make_agent()
        state = {"center": {"lat": 40.4, "lon": -3.7}, "zoom": 10}
        prompt = agent._build_system_prompt([], map_state=state)

        self.assertIn("Current map state", prompt)
        self.assertIn(json.dumps(state), prompt)


class FormatMcpResultTest(TestCase):
    """Verifica Agent._format_mcp_result() con distintos formatos."""

    def test_dict_con_content_array(self):
        """Un dict con 'content' array de tipo text debe unirse con newlines."""
        result = {
            "content": [
                {"type": "text", "text": "Línea 1"},
                {"type": "text", "text": "Línea 2"},
            ]
        }
        formatted = Agent._format_mcp_result(result)
        self.assertEqual(formatted, "Línea 1\nLínea 2")

    def test_dict_sin_content_key(self):
        """Un dict sin clave 'content' debe serializarse como JSON."""
        result = {"status": "ok", "data": 42}
        formatted = Agent._format_mcp_result(result)
        parsed = json.loads(formatted)
        self.assertEqual(parsed["status"], "ok")
        self.assertEqual(parsed["data"], 42)


class AgentResponseLayersTest(TestCase):
    """Verifica que AgentResponse propaga layers correctamente."""

    def test_text_con_layers(self):
        """AgentResponse.text() acepta y almacena layers."""
        layers = [{"type": "geojson", "source": {}, "name": "Detecciones"}]
        resp = AgentResponse.text("Ok", layers=layers)
        self.assertEqual(resp.layers, layers)

    def test_text_sin_layers(self):
        """AgentResponse.text() sin layers usa lista vacía."""
        resp = AgentResponse.text("Ok")
        self.assertEqual(resp.layers, [])

    def test_tool_call_con_layers(self):
        """AgentResponse.tool_call() acepta y almacena layers."""
        layers = [{"type": "geojson", "source": {}, "name": "Piscinas"}]
        tc = [{"name": "zoomTo", "args": {}, "id": "tc1"}]
        resp = AgentResponse.tool_call("Moviendo...", tool_calls=tc, layers=layers)
        self.assertEqual(resp.layers, layers)

    def test_init_con_layers(self):
        """AgentResponse constructor acepta layers directamente."""
        layers = [{"type": "geojson", "source": {"type": "FeatureCollection"}, "name": "Test"}]
        resp = AgentResponse(content=[], layers=layers)
        self.assertEqual(resp.layers, layers)


class ClassifyToolCallsTest(TestCase):
    """Verifica Agent._classify_tool_calls() separa server, MCP y map."""

    def _make_agent(self):
        with patch("agent.agent.SkillRegistry") as MockRegistry, \
             patch("agent.agent.get_llm_provider") as mock_llm, \
             patch("agent.agent.Agent._init_mcp") as mock_mcp:
            mock_mcp.return_value = MagicMock()
            mock_mcp.return_value.is_mcp_tool.side_effect = lambda n: n == "mcp_tool"
            MockRegistry.return_value = MagicMock()
            mock_llm.return_value = MagicMock()
            agent = Agent()
        return agent

    @patch("agent.agent.has_executor", side_effect=lambda n: n == "fetchWebPage")
    def test_clasifica_server_mcp_y_map(self, _mock_exec):
        """Clasifica correctamente tools de servidor, MCP y mapa."""
        agent = self._make_agent()
        tool_calls = [
            {"name": "fetchWebPage", "args": {}, "id": "1"},
            {"name": "mcp_tool", "args": {}, "id": "2"},
            {"name": "zoomTo", "args": {}, "id": "3"},
        ]
        server, mcp, map_calls = agent._classify_tool_calls(tool_calls)
        self.assertEqual(len(server), 1)
        self.assertEqual(server[0]["name"], "fetchWebPage")
        self.assertEqual(len(mcp), 1)
        self.assertEqual(mcp[0]["name"], "mcp_tool")
        self.assertEqual(len(map_calls), 1)
        self.assertEqual(map_calls[0]["name"], "zoomTo")

    @patch("agent.agent.has_executor", return_value=False)
    def test_sin_executor_ni_mcp_son_map(self, _mock_exec):
        """Tools sin executor ni MCP se clasifican como map."""
        agent = self._make_agent()
        agent.mcp_manager.is_mcp_tool.return_value = False
        tool_calls = [{"name": "addLayer", "args": {}, "id": "1"}]
        server, mcp, map_calls = agent._classify_tool_calls(tool_calls)
        self.assertEqual(len(server), 0)
        self.assertEqual(len(mcp), 0)
        self.assertEqual(len(map_calls), 1)


class ExecuteServerToolTest(TestCase):
    """Verifica Agent._execute_server_tool()."""

    @patch("agent.agent.get_executor")
    def test_ejecuta_tool_correctamente(self, mock_get_exec):
        """Ejecuta el executor y devuelve resultado formateado."""
        mock_get_exec.return_value = lambda **kw: {"status": "ok"}
        tc = {"name": "fetchWebPage", "args": {"url": "http://test.com"}, "id": "1"}
        result = Agent._execute_server_tool(tc)
        parsed = json.loads(result)
        self.assertEqual(parsed["result"]["status"], "ok")

    @patch("agent.agent.get_executor")
    def test_resultado_string_se_devuelve_directo(self, mock_get_exec):
        """Si el executor devuelve string, se devuelve directamente (sin wrappear en JSON)."""
        mock_get_exec.return_value = lambda **kw: "texto plano"
        tc = {"name": "fetchWebPage", "args": {}, "id": "1"}
        result = Agent._execute_server_tool(tc)
        self.assertEqual(result, "texto plano")

    @patch("agent.agent.get_executor", side_effect=Exception("boom"))
    def test_error_devuelve_json_con_error(self, _mock):
        """Si el executor falla, devuelve JSON con el error."""
        tc = {"name": "badTool", "args": {}, "id": "1"}
        result = Agent._execute_server_tool(tc)
        parsed = json.loads(result)
        self.assertIn("error", parsed)
        self.assertIn("boom", parsed["error"])


class CollectGeojsonLayerTest(TestCase):
    """Verifica Agent._collect_geojson_layer()."""

    def test_featurecollection_se_acumula(self):
        """Un FeatureCollection válido se añade a la lista de layers."""
        geojson = {
            "type": "FeatureCollection",
            "features": [{"properties": {"label": "Piscina"}}],
        }
        layers = []
        Agent._collect_geojson_layer(json.dumps(geojson), layers)
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0]["name"], "Piscina detectados")
        self.assertEqual(layers[0]["type"], "geojson")

    def test_json_no_featurecollection_se_ignora(self):
        """Un JSON que no es FeatureCollection no se acumula."""
        layers = []
        Agent._collect_geojson_layer(json.dumps({"status": "ok"}), layers)
        self.assertEqual(len(layers), 0)

    def test_string_no_json_se_ignora(self):
        """Un string que no es JSON válido no se acumula."""
        layers = []
        Agent._collect_geojson_layer("texto plano", layers)
        self.assertEqual(len(layers), 0)

    def test_featurecollection_sin_label_usa_default(self):
        """FeatureCollection sin label en features usa 'Detecciones'."""
        geojson = {"type": "FeatureCollection", "features": [{"properties": {}}]}
        layers = []
        Agent._collect_geojson_layer(json.dumps(geojson), layers)
        self.assertEqual(layers[0]["name"], "Detecciones")


class AppendToolMessagesTest(TestCase):
    """Verifica Agent._append_tool_messages()."""

    def test_append_dos_mensajes(self):
        """Añade un mensaje assistant y uno tool al historial."""
        messages = []
        response = MagicMock()
        response.content = "Ejecutando..."
        tc = {"name": "zoomTo", "args": {}, "id": "tc1"}
        Agent._append_tool_messages(messages, response, tc, '{"ok": true}')
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[0]["role"], "assistant")
        self.assertEqual(messages[0]["tool_calls"], [tc])
        self.assertEqual(messages[1]["role"], "tool")
        self.assertEqual(messages[1]["tool_call_id"], "tc1")
        self.assertEqual(messages[1]["content"], '{"ok": true}')


class AgentInitTest(TestCase):
    """Verifica que Agent.__init__ se puede crear con dependencias mockeadas."""

    @patch("agent.agent.Agent._init_mcp")
    @patch("agent.agent.SkillRegistry")
    @patch("agent.agent.get_llm_provider")
    def test_init_con_mocks(self, mock_llm, MockRegistry, mock_mcp):
        """Agent debe inicializarse correctamente con provider, registry y mcp mockeados."""
        mock_llm.return_value = MagicMock()
        MockRegistry.return_value = MagicMock()
        mock_mcp.return_value = None

        agent = Agent()

        self.assertIsNotNone(agent.provider)
        self.assertIsNotNone(agent.skill_registry)
        self.assertIsNone(agent.mcp_manager)


class ProviderStreamTest(TestCase):
    """Verifica BaseLLMProvider.stream() con mock del LLM."""

    def _make_provider(self):
        from agent.llm.providers import BaseLLMProvider
        provider = BaseLLMProvider()
        provider.llm = MagicMock()
        return provider

    def test_stream_texto_simple(self):
        """stream() yield chunks de texto incremental."""
        from agent.llm.providers import BaseLLMProvider

        provider = self._make_provider()
        chunk1 = MagicMock(content="Hola ", tool_call_chunks=[])
        chunk2 = MagicMock(content="mundo", tool_call_chunks=[])
        provider.llm.stream.return_value = [chunk1, chunk2]

        chunks = list(provider.stream([{"role": "user", "content": "Hi"}]))
        texts = [c.content for c in chunks]
        self.assertEqual(texts, ["Hola ", "mundo"])
        self.assertFalse(any(c.has_tool_calls for c in chunks))

    def test_stream_con_tool_calls(self):
        """stream() acumula tool_calls y los emite al final."""
        from agent.llm.providers import BaseLLMProvider

        provider = self._make_provider()
        chunk1 = MagicMock(content="", tool_call_chunks=[
            {"index": 0, "name": "zoomTo", "id": "tc1", "args": '{"lat":'}
        ])
        chunk2 = MagicMock(content="", tool_call_chunks=[
            {"index": 0, "name": "", "id": "", "args": ' 40.4}'}
        ])
        # Simulate hasattr for tool_call_chunks
        provider.llm.stream.return_value = [chunk1, chunk2]

        chunks = list(provider.stream([{"role": "user", "content": "zoom"}]))
        tool_chunks = [c for c in chunks if c.has_tool_calls]
        self.assertEqual(len(tool_chunks), 1)
        self.assertEqual(tool_chunks[0].tool_calls[0]["name"], "zoomTo")
        self.assertEqual(tool_chunks[0].tool_calls[0]["args"]["lat"], 40.4)


class RunStreamTest(TestCase):
    """Verifica Agent.run_stream() emite eventos SSE correctos."""

    def _make_agent(self):
        with patch("agent.agent.SkillRegistry") as MockRegistry, \
             patch("agent.agent.get_llm_provider") as mock_llm, \
             patch("agent.agent.Agent._init_mcp") as mock_mcp, \
             patch("agent.agent.retrieve_context") as mock_rag:
            mock_mcp.return_value = None
            MockRegistry.return_value = MagicMock()
            mock_llm.return_value = MagicMock()
            mock_rag.return_value = []
            agent = Agent()
        return agent

    @patch("agent.agent.retrieve_context", return_value=[])
    @patch("agent.agent.get_langchain_tools", return_value=[])
    def test_stream_texto_emite_deltas_y_done(self, _tools, _rag):
        """run_stream() emite text_delta para cada chunk y done al final."""
        from agent.llm.providers import ChatResponse

        agent = self._make_agent()
        agent.provider.stream = MagicMock(return_value=iter([
            ChatResponse(content="Hola "),
            ChatResponse(content="mundo"),
        ]))

        events = list(agent.run_stream("test", []))
        types = [e["type"] for e in events]
        self.assertIn("text_delta", types)
        self.assertEqual(types[-1], "done")
        text_events = [e for e in events if e["type"] == "text_delta"]
        full_text = "".join(e["text"] for e in text_events)
        self.assertEqual(full_text, "Hola mundo")
