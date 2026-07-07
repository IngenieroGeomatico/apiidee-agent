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
