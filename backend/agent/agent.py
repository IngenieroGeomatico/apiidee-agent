"""
Agent — The AI brain that orchestrates tools, skills, and RAG to respond to user messages.

Concepts:
- Agent: Orchestrates the conversation. Receives messages, decides actions, returns responses.
- Tool: An atomic action the agent can invoke (executed on the frontend, not here).
- Skill: A domain expertise that groups tools + specialized prompt context.
"""
import json
from typing import Optional

from .llm.config import get_llm_provider
from .prompts import SYSTEM_PROMPT
from .rag.retriever import retrieve_context
from .skills.base import SkillRegistry
from .tools.registry import get_langchain_tools


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
    - Return either a text response or tool call instructions

    The Agent does NOT handle HTTP, persistence, or serialization.
    That's the view's job.
    """

    def __init__(self):
        self.provider = get_llm_provider()
        self.skill_registry = SkillRegistry()

    def run(self, user_message: str, history: list,
            map_state: Optional[dict] = None) -> AgentResponse:
        """
        Process a user message and return a response.

        Args:
            user_message: The user's input text
            history: List of message dicts with 'role', 'content', and optional metadata
            map_state: Optional current state of the map (center, zoom, layers)

        Returns:
            AgentResponse with either text content or tool_call instructions
        """
        # 1. Retrieve RAG context
        rag_results = retrieve_context(query=user_message)

        # 2. Build system prompt
        system_prompt = self._build_system_prompt(rag_results, map_state)

        # 3. Build message list for LLM
        llm_messages = [{"role": "system", "content": system_prompt}]
        llm_messages.extend(history)

        # 4. Get available tools from skills
        tools = get_langchain_tools()

        # 5. Call LLM
        response = self.provider.chat(llm_messages, tools=tools if tools else None)

        # 6. Build response
        sources = [chunk["metadata"] for chunk in rag_results] if rag_results else []

        if response.has_tool_calls:
            return AgentResponse(
                content=response.content or "Ejecutando acción en el mapa...",
                response_type="tool_call",
                tool_calls=response.tool_calls,
                sources=sources,
            )

        return AgentResponse(
            content=response.content,
            response_type="text",
            sources=sources,
        )

    def process_tool_result(self, tool_name: str, tool_result: dict,
                            success: bool, history: list) -> AgentResponse:
        """
        Process a tool execution result and generate a follow-up response.

        Args:
            tool_name: Name of the tool that was executed
            tool_result: Result returned by the tool
            success: Whether the tool execution succeeded
            history: Full conversation history including the tool result message

        Returns:
            AgentResponse with the agent's interpretation of the tool result
        """
        # Find last user message for RAG context
        last_user_content = ""
        for msg in reversed(history):
            if msg.get("role") == "user":
                last_user_content = msg["content"]
                break

        rag_results = retrieve_context(query=last_user_content) if last_user_content else []
        system_prompt = self._build_system_prompt(rag_results)

        llm_messages = [{"role": "system", "content": system_prompt}]
        llm_messages.extend(history)

        # Call LLM without tools to get final interpretation
        response = self.provider.chat(llm_messages)
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
