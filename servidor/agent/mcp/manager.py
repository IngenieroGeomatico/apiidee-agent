import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .client import MCPClient

logger = logging.getLogger(__name__)


class MCPServerManager:
    """Manages multiple MCP server connections as a singleton.

    Initialized once at Django startup via apps.py.
    """

    _instance: Optional["MCPServerManager"] = None

    def __init__(self):
        self.servers: Dict[str, MCPClient] = {}
        self._mcp_tool_names: set = set()

    @classmethod
    def initialize(cls, config_path: Optional[Path] = None) -> "MCPServerManager":
        """Initialize (or return existing) singleton with server config."""
        if cls._instance is not None:
            return cls._instance

        instance = cls()

        if config_path and Path(config_path).exists():
            with open(config_path, encoding="utf-8") as f:
                servers_config = json.load(f)

            for cfg in servers_config:
                name = cfg.get("name", "unknown")
                url = cfg.get("url", "")
                timeout = cfg.get("timeout", 30)
                try:
                    client = MCPClient(name=name, url=url, timeout=timeout)
                    tools = client.list_tools()
                    for tool in tools:
                        instance._mcp_tool_names.add(tool["name"])
                    instance.servers[name] = client
                    logger.info(
                        "Connected to MCP server '%s' (%d tools)",
                        name, len(tools),
                    )
                except Exception as e:
                    logger.error(
                        "Failed to connect to MCP server '%s': %s", name, e
                    )

        cls._instance = instance
        return instance

    @classmethod
    def get_instance(cls) -> Optional["MCPServerManager"]:
        return cls._instance

    def get_all_tools(self) -> List[dict]:
        """Return all tools from all servers in standard format."""
        tools = []
        for client in self.servers.values():
            try:
                for tool in client.list_tools():
                    tools.append({
                        "name": tool["name"],
                        "description": tool.get("description", ""),
                        "parameters": tool.get(
                            "inputSchema",
                            {"type": "object", "properties": {}},
                        ),
                    })
            except Exception as e:
                logger.error("Error listing tools from %s: %s", client.name, e)
        return tools

    def execute_tool(self, tool_name: str, arguments: dict) -> Any:
        """Execute a tool on the appropriate MCP server."""
        if tool_name not in self._mcp_tool_names:
            raise ValueError(f"Tool '{tool_name}' is not an MCP tool")

        last_error = None
        for name, client in self.servers.items():
            try:
                return client.call_tool(tool_name, arguments)
            except Exception as e:
                last_error = e
                logger.debug(
                    "MCP tool '%s' failed on '%s': %s", tool_name, name, e
                )

        raise RuntimeError(
            f"Failed to execute MCP tool '{tool_name}' on any server: {last_error}"
        )

    def is_mcp_tool(self, tool_name: str) -> bool:
        """Check if a tool name is provided by any MCP server."""
        return tool_name in self._mcp_tool_names

    def is_connected(self) -> bool:
        """Whether at least one MCP server is connected."""
        return len(self.servers) > 0
