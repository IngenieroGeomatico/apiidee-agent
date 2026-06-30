import json
import logging
from typing import Any, List, Optional

import requests

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for a single MCP server using JSON-RPC over HTTP."""

    def __init__(self, name: str, url: str, timeout: int = 30):
        self.name = name
        self.url = url.rstrip("/")
        self.timeout = timeout
        self._request_id = 0

    def _request(self, method: str, params: Optional[dict] = None) -> dict:
        self._request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
        }
        if params:
            payload["params"] = params

        resp = requests.post(
            self.url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(
                f"MCP error from '{self.name}': code={data['error'].get('code')}, "
                f"message={data['error'].get('message')}"
            )

        return data.get("result", {})

    def list_tools(self) -> List[dict]:
        """List all tools available from this MCP server."""
        result = self._request("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> Any:
        """Call a tool on this MCP server and return its result."""
        result = self._request("tools/call", {
            "name": name,
            "arguments": arguments,
        })
        return result
