"""
Agent — The AI brain that orchestrates tools, skills, and RAG to respond to user messages.

Concepts:
- Agent: Orchestrates the conversation. Receives messages, decides actions, returns responses.
- Tool: An atomic action the agent can invoke (executed on the frontend, not here).
- Skill: A domain expertise that groups tools + specialized prompt context.
- MCP: Tools from external MCP servers are executed server-side, not on the frontend.
"""
import json
import logging
from typing import Optional

from .llm.config import get_llm_provider, get_provider
from .prompts import SYSTEM_PROMPT
from .rag.retriever import retrieve_context
from .skills.base import SkillRegistry
from .tools.registry import get_langchain_tools

logger = logging.getLogger(__name__)


class AgentResponse:
    """Response from the agent — either text or a tool call request."""

    def __init__(self, content: str, response_type: str = "text",
                 tool_calls: list = None, sources: list = None):
        self.content = content
        self.type = response_type  # "text" or "tool_call"
        self.tool_calls = tool_calls or []
        self.sources = sources or []


class Agent:
    """
    The AI agent that powers the API-IDEE assistant.

    Responsibilities:
    - Build the system prompt from skills + RAG context + map state
    - Call the LLM with available tools
    - Execute MCP tools server-side in a loop
    - Return either a text response or map tool call instructions
    """

    def __init__(self, provider_name: Optional[str] = None,
                 model: Optional[str] = None,
                 api_key: Optional[str] = None):
        self.skill_registry = SkillRegistry()
        self.provider = self._init_provider(provider_name, model, api_key)
        self.mcp_manager = self._init_mcp()

    @staticmethod
    def _init_mcp():
        from agent.mcp.manager import MCPServerManager
        return MCPServerManager.get_instance()

    def _init_provider(self, provider_name, model, api_key):
        if provider_name and model:
            return get_provider(provider_name, model, api_key=api_key)
        from django.conf import settings
        if settings.LLM_PROVIDERS:
            first = settings.LLM_PROVIDERS[0]
            return get_provider(
                provider_name or first["name"],
                model or first.get("default_model", ""),
                api_key=api_key,
            )
        return get_llm_provider()

    def run(self, user_message: str, history: list,
            map_state: Optional[dict] = None) -> AgentResponse:
        """
        Process a user message and return a response.

        MCP tools are executed server-side in a loop; only map tools
        are returned as tool_call for the frontend to execute.
        """
        rag_results = retrieve_context(query=user_message)
        system_prompt = self._build_system_prompt(rag_results, map_state)
        llm_messages = [{"role": "system", "content": system_prompt}, *history]
        return self._run_llm_loop(llm_messages, rag_results)

    def process_tool_result(self, tool_name: str, tool_result: dict,
                            success: bool, history: list) -> AgentResponse:
        """
        Process a tool execution result and generate a follow-up response.

        Unlike run(), this does NOT include map state.
        MCP tools are still handled inline if the LLM requests them.
        """
        last_user_content = ""
        for msg in reversed(history):
            if msg.get("role") == "user":
                last_user_content = msg["content"]
                break

        rag_results = retrieve_context(query=last_user_content) if last_user_content else []
        system_prompt = self._build_system_prompt(rag_results)
        llm_messages = [{"role": "system", "content": system_prompt}, *history]
        return self._run_llm_loop(llm_messages, rag_results)

    def _run_llm_loop(self, llm_messages: list, rag_results: list,
                      max_iterations: int = 5) -> AgentResponse:
        """
        Call the LLM in a loop, executing MCP tools inline.

        - If the LLM returns only map tools → return them as tool_call.
        - If the LLM returns MCP tools → execute them, feed results back, loop.
        - If the LLM returns text → return as text.
        """
        tools = get_langchain_tools()

        for iteration in range(max_iterations):
            response = self.provider.chat(
                llm_messages,
                tools=tools if tools else None,
            )

            if not response.has_tool_calls:
                return self._build_response(response, rag_results)

            mcp_calls = [
                tc for tc in response.tool_calls
                if self.mcp_manager and self.mcp_manager.is_mcp_tool(tc["name"])
            ]
            map_calls = [
                tc for tc in response.tool_calls
                if not (self.mcp_manager and self.mcp_manager.is_mcp_tool(tc["name"]))
            ]

            if not mcp_calls:
                return AgentResponse(
                    content=response.content or "Ejecutando acción en el mapa...",
                    response_type="tool_call",
                    tool_calls=map_calls,
                    sources=[chunk["metadata"] for chunk in rag_results] if rag_results else [],
                )

            for tc in mcp_calls:
                try:
                    result = self.mcp_manager.execute_tool(tc["name"], tc["args"])
                    formatted = self._format_mcp_result(result)
                    logger.info("MCP tool '%s' executed successfully", tc["name"])
                except Exception as e:
                    logger.exception("MCP tool '%s' failed", tc["name"])
                    formatted = json.dumps({"error": str(e)}, ensure_ascii=False)

                llm_messages.append({
                    "role": "assistant",
                    "content": response.content or "",
                    "tool_calls": [tc],
                })
                llm_messages.append({
                    "role": "tool",
                    "content": formatted,
                    "tool_call_id": tc["id"],
                })

        logger.warning("MCP iteration limit (%d) reached", max_iterations)
        return AgentResponse(
            content="Se alcanzó el límite de iteraciones de herramientas MCP.",
            response_type="text",
        )

    @staticmethod
    def _format_mcp_result(result) -> str:
        """Convert MCP result (content array) to a plain string for the LLM."""
        if isinstance(result, dict) and "content" in result:
            texts = []
            for item in result["content"]:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif isinstance(item, str):
                    texts.append(item)
                else:
                    texts.append(json.dumps(item, ensure_ascii=False))
            return "\n".join(texts)
        return json.dumps(result, ensure_ascii=False)

    def _build_response(self, response, rag_results):
        sources = [chunk["metadata"] for chunk in rag_results] if rag_results else []
        return AgentResponse(
            content=response.content,
            response_type="text",
            sources=sources,
        )

    def _build_system_prompt(self, rag_results: list,
                             map_state: Optional[dict] = None) -> str:
        """Assemble the full system prompt from RAG, skills, and map state."""
        context_text = self._format_rag_context(rag_results)
        skills_context = self.skill_registry.get_system_prompt()

        prompt = SYSTEM_PROMPT.format(
            context=context_text,
            skills_context=skills_context,
        )

        if map_state:
            prompt += f"\n\nCurrent map state: {json.dumps(map_state)}"

        return prompt

    @staticmethod
    def _format_rag_context(rag_results: list) -> str:
        if not rag_results:
            return "No additional context available."
        parts = ["Relevant context from the API-IDEE codebase:\n"]
        for i, chunk in enumerate(rag_results, 1):
            source = chunk["metadata"].get("source", "unknown")
            parts.append(f"--- Source {i}: {source} ---")
            parts.append(chunk["content"])
            parts.append("")
        return "\n".join(parts)
