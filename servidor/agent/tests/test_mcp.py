"""Tests unitarios para el cliente y manager MCP (mcp/client.py, mcp/manager.py).

Cubre MCPClient (list_tools, call_tool, errores HTTP/JSON-RPC/timeout)
y MCPServerManager (singleton, initialize, get_all_tools, execute_tool,
is_mcp_tool, is_connected).
"""
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase

from agent.mcp.client import MCPClient
from agent.mcp.manager import MCPServerManager


class MCPClientListToolsTest(TestCase):
    """Verifica MCPClient.list_tools() con respuesta mockeada."""

    @patch("agent.mcp.client.requests.post")
    def test_list_tools_devuelve_herramientas(self, mock_post):
        """list_tools() devuelve la lista de herramientas del servidor MCP."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {"name": "get_weather", "description": "Obtener clima"},
                    {"name": "search_db", "description": "Buscar en BD"},
                ]
            },
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = MCPClient(name="test-server", url="http://localhost:8001")
        tools = client.list_tools()

        self.assertEqual(len(tools), 2)
        self.assertEqual(tools[0]["name"], "get_weather")
        self.assertEqual(tools[1]["name"], "search_db")
        mock_post.assert_called_once()


class MCPClientCallToolTest(TestCase):
    """Verifica MCPClient.call_tool() con respuesta mockeada."""

    @patch("agent.mcp.client.requests.post")
    def test_call_tool_devuelve_resultado(self, mock_post):
        """call_tool() devuelve el resultado de la ejecución de la herramienta."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"temperature": 22, "city": "Madrid"},
        }
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        client = MCPClient(name="test-server", url="http://localhost:8001")
        result = client.call_tool("get_weather", {"city": "Madrid"})

        self.assertEqual(result["temperature"], 22)
        self.assertEqual(result["city"], "Madrid")


class MCPClientErrorsTest(TestCase):
    """Verifica el manejo de errores en MCPClient."""

    @patch("agent.mcp.client.requests.post")
    def test_http_error_lanza_excepcion(self, mock_post):
        """Un error HTTP (raise_for_status) lanza requests.HTTPError."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.side_effect = requests.HTTPError("500 Server Error")
        mock_post.return_value = mock_resp

        client = MCPClient(name="test-server", url="http://localhost:8001")
        with self.assertRaises(requests.HTTPError):
            client.list_tools()

    @patch("agent.mcp.client.requests.post")
    def test_jsonrpc_error_lanza_runtime_error(self, mock_post):
        """Un error JSON-RPC en la respuesta lanza RuntimeError."""
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32601, "message": "Method not found"},
        }
        mock_post.return_value = mock_resp

        client = MCPClient(name="test-server", url="http://localhost:8001")
        with self.assertRaises(RuntimeError) as ctx:
            client.call_tool("unknown_tool", {})
        self.assertIn("Method not found", str(ctx.exception))

    @patch("agent.mcp.client.requests.post")
    def test_timeout_lanza_excepcion(self, mock_post):
        """Un timeout en la petición HTTP lanza requests.Timeout."""
        mock_post.side_effect = requests.Timeout("Connection timed out")

        client = MCPClient(name="test-server", url="http://localhost:8001", timeout=5)
        with self.assertRaises(requests.Timeout):
            client.list_tools()


class MCPServerManagerInitializeTest(TestCase):
    """Verifica MCPServerManager.initialize() con clientes mockeados."""

    def setUp(self):
        """Resetea el singleton antes de cada test."""
        MCPServerManager._instance = None

    def tearDown(self):
        """Resetea el singleton después de cada test."""
        MCPServerManager._instance = None

    @patch("agent.mcp.manager.MCPClient")
    def test_initialize_conecta_servidores(self, MockClient):
        """initialize() crea clientes y descubre herramientas de cada servidor."""
        import tempfile
        import json
        import os

        mock_client = MagicMock()
        mock_client.list_tools.return_value = [
            {"name": "tool_a", "description": "Tool A"},
            {"name": "tool_b", "description": "Tool B"},
        ]
        MockClient.return_value = mock_client

        config = [{"name": "srv1", "url": "http://localhost:9000", "timeout": 10}]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(config, f)
            config_path = f.name

        try:
            manager = MCPServerManager.initialize(config_path=config_path)
            self.assertIn("srv1", manager.servers)
            self.assertTrue(manager.is_mcp_tool("tool_a"))
            self.assertTrue(manager.is_mcp_tool("tool_b"))
            self.assertTrue(manager.is_connected())
        finally:
            os.unlink(config_path)


class MCPServerManagerGetAllToolsTest(TestCase):
    """Verifica MCPServerManager.get_all_tools()."""

    def setUp(self):
        MCPServerManager._instance = None

    def tearDown(self):
        MCPServerManager._instance = None

    def test_get_all_tools_devuelve_herramientas_de_todos_los_servidores(self):
        """get_all_tools() agrega herramientas de todos los servidores conectados."""
        manager = MCPServerManager()

        client1 = MagicMock()
        client1.name = "srv1"
        client1.list_tools.return_value = [
            {"name": "tool_a", "description": "Desc A", "inputSchema": {"type": "object", "properties": {}}},
        ]
        client2 = MagicMock()
        client2.name = "srv2"
        client2.list_tools.return_value = [
            {"name": "tool_b", "description": "Desc B"},
        ]
        manager.servers = {"srv1": client1, "srv2": client2}

        tools = manager.get_all_tools()
        self.assertEqual(len(tools), 2)
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"tool_a", "tool_b"})
        # tool_a tiene inputSchema explícito
        tool_a = next(t for t in tools if t["name"] == "tool_a")
        self.assertEqual(tool_a["parameters"]["type"], "object")
        # tool_b usa schema por defecto
        tool_b = next(t for t in tools if t["name"] == "tool_b")
        self.assertEqual(tool_b["parameters"]["type"], "object")


class MCPServerManagerExecuteToolTest(TestCase):
    """Verifica MCPServerManager.execute_tool()."""

    def setUp(self):
        MCPServerManager._instance = None

    def tearDown(self):
        MCPServerManager._instance = None

    def test_execute_tool_devuelve_resultado(self):
        """execute_tool() intenta servidores y devuelve el resultado del primero que funcione."""
        manager = MCPServerManager()
        manager._mcp_tool_names = {"my_tool"}

        client = MagicMock()
        client.call_tool.return_value = {"status": "ok", "data": 42}
        manager.servers = {"srv1": client}

        result = manager.execute_tool("my_tool", {"param": "value"})
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"], 42)
        client.call_tool.assert_called_once_with("my_tool", {"param": "value"})

    def test_execute_tool_todos_fallan_lanza_runtime_error(self):
        """execute_tool() lanza RuntimeError si todos los servidores fallan."""
        manager = MCPServerManager()
        manager._mcp_tool_names = {"failing_tool"}

        client1 = MagicMock()
        client1.call_tool.side_effect = RuntimeError("srv1 down")
        client2 = MagicMock()
        client2.call_tool.side_effect = RuntimeError("srv2 down")
        manager.servers = {"srv1": client1, "srv2": client2}

        with self.assertRaises(RuntimeError) as ctx:
            manager.execute_tool("failing_tool", {})
        self.assertIn("Failed to execute MCP tool", str(ctx.exception))


class MCPServerManagerIsMcpToolTest(TestCase):
    """Verifica MCPServerManager.is_mcp_tool() e is_connected()."""

    def setUp(self):
        MCPServerManager._instance = None

    def tearDown(self):
        MCPServerManager._instance = None

    def test_is_mcp_tool_true_y_false(self):
        """is_mcp_tool() devuelve True para tools registradas y False para las demás."""
        manager = MCPServerManager()
        manager._mcp_tool_names = {"tool_x", "tool_y"}

        self.assertTrue(manager.is_mcp_tool("tool_x"))
        self.assertTrue(manager.is_mcp_tool("tool_y"))
        self.assertFalse(manager.is_mcp_tool("tool_z"))
        self.assertFalse(manager.is_mcp_tool("zoomTo"))

    def test_is_connected_true_con_servidores(self):
        """is_connected() devuelve True cuando hay servidores registrados."""
        manager = MCPServerManager()
        manager.servers = {"srv1": MagicMock()}
        self.assertTrue(manager.is_connected())

    def test_is_connected_false_sin_servidores(self):
        """is_connected() devuelve False cuando no hay servidores."""
        manager = MCPServerManager()
        self.assertFalse(manager.is_connected())
