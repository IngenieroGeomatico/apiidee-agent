from typing import Dict, List, Optional

_tools_registry: Dict[str, dict] = {}


def register_tool(name: str, description: str, parameters: dict):
    """Register a tool with its schema."""
    _tools_registry[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
    }


def get_all_tools() -> List[dict]:
    return list(_tools_registry.values())


def get_tool_by_name(name: str) -> Optional[dict]:
    return _tools_registry.get(name)


def get_langchain_tools():
    """Convert registered tools to LangChain tool format for bind_tools()."""
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
