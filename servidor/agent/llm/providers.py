from __future__ import annotations

from typing import Generator, Optional

from django.conf import settings


class ChatResponse:
    """Respuesta del LLM que puede contener texto y/o llamadas a herramientas."""

    def __init__(self, content: str = "", tool_calls: Optional[list] = None):
        """Inicializa una respuesta con contenido textual y/o llamadas a herramientas."""
        self.content = content
        self.tool_calls = tool_calls or []

    @property
    def has_tool_calls(self):
        """Indica si la respuesta incluye al menos una llamada a herramienta."""
        return len(self.tool_calls) > 0


class BaseLLMProvider:
    """Proveedor base para modelos de lenguaje.

    Las subclases solo necesitan inicializar ``self.llm`` con un objeto
    LangChain compatible (ChatOpenAI, ChatGoogleGenerativeAI, etc.).
    Los métodos ``chat()`` y ``stream()`` son comunes a todos los proveedores.
    """

    llm = None  # Las subclases lo inicializan en __init__

    def chat(self, messages: list[dict], tools: Optional[list] = None) -> ChatResponse:
        """Envía mensajes al LLM y devuelve una ChatResponse con texto y/o tool calls."""
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

    def stream(self, messages: list[dict],
               tools: Optional[list] = None) -> Generator[ChatResponse, None, None]:
        """Envía mensajes al LLM y hace yield de ChatResponse incrementales.

        Cada chunk contiene solo el delta de texto (``content``).  Si el LLM
        decide invocar tools, el último chunk contendrá ``tool_calls`` con
        la lista completa (los tool calls no se streamean parcialmente).

        Yields:
            ChatResponse con ``content`` incremental y/o ``tool_calls``.
        """
        lc_messages = [self._convert_message(m) for m in messages]

        llm = self.llm
        if tools:
            llm = self.llm.bind_tools(tools)

        accumulated_tool_calls = []
        for chunk in llm.stream(lc_messages):
            # Acumular tool calls si llegan en chunks
            if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                for tc_chunk in chunk.tool_call_chunks:
                    self._accumulate_tool_call(accumulated_tool_calls, tc_chunk)

            # Emitir delta de texto si hay contenido
            text = chunk.content if isinstance(chunk.content, str) else ""
            if text:
                yield ChatResponse(content=text)

        # Emitir tool calls acumulados al final (si los hay)
        if accumulated_tool_calls:
            self._finalize_tool_call_args(accumulated_tool_calls)
            finalized = [
                {"name": tc["name"], "args": tc["args"], "id": tc.get("id", "")}
                for tc in accumulated_tool_calls
                if tc.get("name")
            ]
            if finalized:
                yield ChatResponse(content="", tool_calls=finalized)

    @staticmethod
    def _accumulate_tool_call(accumulated: list, tc_chunk: dict):
        """Acumula fragmentos de tool_call en una lista de tool calls completos."""
        idx = tc_chunk.get("index", 0)
        # Extender lista si es necesario
        while len(accumulated) <= idx:
            accumulated.append({"name": "", "args": "", "id": ""})
        tc = accumulated[idx]
        if tc_chunk.get("name"):
            tc["name"] = tc_chunk["name"]
        if tc_chunk.get("id"):
            tc["id"] = tc_chunk["id"]
        # Los args llegan como fragmentos de JSON string
        args_fragment = tc_chunk.get("args", "")
        if args_fragment:
            tc["args"] = (tc.get("args", "") or "") + args_fragment

    @staticmethod
    def _finalize_tool_call_args(accumulated: list):
        """Parsea los args acumulados (JSON string) a dict."""
        import json
        for tc in accumulated:
            if isinstance(tc.get("args"), str) and tc["args"]:
                try:
                    tc["args"] = json.loads(tc["args"])
                except (json.JSONDecodeError, TypeError):
                    tc["args"] = {}

    @staticmethod
    def _convert_message(msg: dict):
        """Convierte un dict de mensaje al formato LangChain correspondiente."""
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
    """Proveedor genérico para cualquier endpoint compatible con la API de OpenAI."""

    def __init__(self, base_url: str, api_key: str, model: str):
        """Configura el cliente LLM apuntando a una URL compatible con OpenAI."""
        from langchain_openai import ChatOpenAI

        self.model = model
        self.llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=0.1,
        )


class OpenAIProvider(BaseLLMProvider):
    """Proveedor para la API oficial de OpenAI."""

    def __init__(self):
        """Inicializa el cliente de OpenAI con la API key y modelo configurados."""
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is not set in environment variables.")

        from langchain_openai import ChatOpenAI

        self.llm = ChatOpenAI(
            model=settings.LLM_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.1,
        )

class GeminiProvider(BaseLLMProvider):
    """Proveedor para Gemini (Google Generative AI)."""

    def __init__(self):
        """Inicializa el cliente de Gemini con la API key y modelo configurados."""
        if not settings.GOOGLE_API_KEY:
            raise ValueError("GOOGLE_API_KEY is not set in environment variables.")

        from langchain_google_genai import ChatGoogleGenerativeAI

        self.llm = ChatGoogleGenerativeAI(
            model=settings.LLM_MODEL,
            google_api_key=settings.GOOGLE_API_KEY,
            temperature=0.1,
        )

