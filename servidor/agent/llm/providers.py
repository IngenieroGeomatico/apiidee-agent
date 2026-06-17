from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from django.conf import settings


class ChatResponse:
    """Represents either a text response or a tool call."""

    def __init__(self, content: str = "", tool_calls: Optional[list] = None):
        self.content = content
        self.tool_calls = tool_calls or []

    @property
    def has_tool_calls(self):
        return len(self.tool_calls) > 0


class BaseLLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: List[Dict], tools: Optional[List] = None) -> ChatResponse:
        pass

    @staticmethod
    def _convert_message(msg: dict):
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        role = msg["role"]
        content = msg["content"]
        if role == "system":
            return SystemMessage(content=content)
        elif role == "user":
            return HumanMessage(content=content)
        elif role == "assistant":
            if msg.get("tool_calls"):
                return AIMessage(content=content, tool_calls=msg["tool_calls"])
            return AIMessage(content=content)
        elif role == "tool":
            return ToolMessage(content=content, tool_call_id=msg.get("tool_call_id", ""))
        return HumanMessage(content=content)


class OpenAICompatibleProvider(BaseLLMProvider):
    """Generic provider for any OpenAI-compatible API endpoint."""

    def __init__(self, base_url: str, api_key: str, model: str):
        from langchain_openai import ChatOpenAI

        self.model = model
        self.llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.1,
        )

    def chat(self, messages, tools=None):
        lc_messages = [self._convert_message(m) for m in messages]

        llm = self.llm
        if tools:
            llm = self.llm.bind_tools(tools)

        response = llm.invoke(lc_messages)

        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = [
                {"name": tc["name"], "args": tc["args"], "id": tc.get("id", "")}
                for tc in response.tool_calls
            ]
            return ChatResponse(content=response.content or "", tool_calls=tool_calls)

        return ChatResponse(content=response.content)


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables.")

        from langchain_openai import ChatOpenAI

        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.1,
        )

    def chat(self, messages, tools=None):
        lc_messages = [self._convert_message(m) for m in messages]

        llm = self.llm
        if tools:
            llm = self.llm.bind_tools(tools)

        response = llm.invoke(lc_messages)

        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = [
                {"name": tc["name"], "args": tc["args"], "id": tc.get("id", "")}
                for tc in response.tool_calls
            ]
            return ChatResponse(content=response.content or "", tool_calls=tool_calls)

        return ChatResponse(content=response.content)


class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is not set in environment variables.")

        from langchain_google_genai import ChatGoogleGenerativeAI

        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.1,
        )

    def chat(self, messages, tools=None):
        lc_messages = [self._convert_message(m) for m in messages]

        llm = self.llm
        if tools:
            llm = self.llm.bind_tools(tools)

        response = llm.invoke(lc_messages)

        if hasattr(response, "tool_calls") and response.tool_calls:
            tool_calls = [
                {"name": tc["name"], "args": tc["args"], "id": tc.get("id", "")}
                for tc in response.tool_calls
            ]
            return ChatResponse(content=response.content or "", tool_calls=tool_calls)

        return ChatResponse(content=response.content)
