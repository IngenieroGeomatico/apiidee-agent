"""
Tool Registry — Auto-discovers tool definitions from JSON files.

Tools are defined as JSON files in tools/definitions/*.json.
Each file contains: name, description, and parameters (JSON Schema).

To add a new tool: create a new .json file in tools/definitions/.
No Python code changes needed.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_tools_registry: Dict[str, dict] = {}
_loaded = False

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"


def _load_definitions():
    """Scan definitions/ directory and load all .json tool files."""
    global _loaded
    if _loaded:
        return

    if not DEFINITIONS_DIR.is_dir():
        logger.warning("Tool definitions directory not found: %s", DEFINITIONS_DIR)
        _loaded = True
        return

    for json_file in sorted(DEFINITIONS_DIR.glob("*.json")):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                definition = json.load(f)

            name = definition.get("name")
            if not name:
                logger.warning("Tool definition missing 'name': %s", json_file.name)
                continue

            _tools_registry[name] = {
                "name": name,
                "description": definition.get("description", ""),
                "parameters": definition.get("parameters", {"type": "object", "properties": {}}),
            }
            logger.debug("Loaded tool: %s (from %s)", name, json_file.name)

        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load tool definition %s: %s", json_file.name, exc)

    logger.info("Loaded %d tool definitions", len(_tools_registry))
    _loaded = True


def register_tool(name: str, description: str, parameters: dict):
    """Register a tool programmatically (for custom tools not defined in JSON)."""
    _tools_registry[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
    }


def get_all_tools() -> List[dict]:
    """Devuelve todas las herramientas registradas, cargando definiciones si es necesario."""
    _load_definitions()
    return list(_tools_registry.values())


def get_tool_by_name(name: str) -> Optional[dict]:
    """Busca y devuelve una herramienta por su nombre, o None si no existe."""
    _load_definitions()
    return _tools_registry.get(name)


def get_langchain_tools():
    """Convert registered tools to LangChain tool format for bind_tools()."""
    _load_definitions()
    tools = []
    for t in _tools_registry.values():
        tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        })
    return tools
