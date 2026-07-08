"""
Agent — El cerebro de IA que orquesta herramientas, skills y RAG para responder mensajes del usuario.

Conceptos:
- Agent: Orquesta la conversación. Recibe mensajes, decide acciones, devuelve respuestas.
- Tool: Acción atómica que el agente puede invocar (ejecutada en el frontend, no aquí).
- Skill: Dominio de experiencia que agrupa herramientas + contexto especializado de prompt.
- MCP: Herramientas de servidores MCP externos se ejecutan en el servidor, no en el frontend.
"""
import json
import logging
from typing import Generator, Optional

from .llm.config import get_llm_provider, get_provider
from .prompts import SYSTEM_PROMPT
from .rag.retriever import retrieve_context
from .skills.base import SkillRegistry
from .tools.registry import get_langchain_tools
from .tools.executors import has_executor, get_executor

logger = logging.getLogger(__name__)


class AgentResponse:
    """Respuesta del agente — lista de content blocks (formato Anthropic/MCP).

    Attributes:
        content: Lista de bloques (text, tool_call, layer).
        sources: Metadatos RAG de las fuentes consultadas.
        layers: Capas GeoJSON generadas por herramientas del servidor
                (ej: detecciones ML).  Se propagan hasta la vista para
                incluirlas en la respuesta HTTP sin usar estado global.
    """

    def __init__(self, content: list, sources: list = None,
                 layers: list = None):
        self.content = content
        self.sources = sources or []
        self.layers = layers or []

    @classmethod
    def text(cls, text: str, sources: list = None,
             layers: list = None) -> "AgentResponse":
        return cls(
            content=[{"type": "text", "text": text}],
            sources=sources or [],
            layers=layers or [],
        )

    @classmethod
    def tool_call(cls, text: str, tool_calls: list,
                  sources: list = None,
                  layers: list = None) -> "AgentResponse":
        blocks = [{"type": "text", "text": text}]
        if tool_calls:
            blocks.append({"type": "tool_call", "toolCalls": tool_calls})
        return cls(content=blocks, sources=sources or [],
                   layers=layers or [])

    @property
    def text_content(self) -> str:
        texts = [b.get("text", "") for b in self.content if b.get("type") == "text"]
        return "\n".join(texts)

    @property
    def tool_calls(self) -> list:
        for b in self.content:
            if b.get("type") == "tool_call":
                return b.get("toolCalls", [])
        return []


class Agent:
    """
    El agente de IA que impulsa el asistente API-IDEE.

    Responsabilidades:
    - Construir el prompt del sistema a partir de skills + contexto RAG + estado del mapa
    - Llamar al LLM con las herramientas disponibles
    - Ejecutar herramientas MCP en el servidor en un bucle
    - Devolver una respuesta de texto o instrucciones de tool call del mapa
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
        Procesa un mensaje del usuario y devuelve una respuesta.

        Las herramientas MCP se ejecutan en el servidor en un bucle; solo las herramientas
        del mapa se devuelven como tool_call para que el frontend las ejecute.
        """
        rag_results = retrieve_context(query=user_message)
        system_prompt = self._build_system_prompt(rag_results, map_state)
        llm_messages = [{"role": "system", "content": system_prompt}, *history]
        return self._run_llm_loop(llm_messages, rag_results)

    def run_stream(self, user_message: str, history: list,
                   map_state: Optional[dict] = None) -> Generator[dict, None, None]:
        """
        Procesa un mensaje del usuario y hace yield de eventos SSE.

        Eventos emitidos (formato dict):
          - ``{"type": "text_delta", "text": "..."}``  — fragmento de texto
          - ``{"type": "tool_call", "toolCalls": [...]}`` — tool calls del mapa
          - ``{"type": "sources", "sources": [...]}`` — fuentes RAG
          - ``{"type": "layer", "layer": {...}}`` — capa GeoJSON (detecciones ML)
          - ``{"type": "done"}`` — fin del stream

        Las herramientas server-side y MCP se ejecutan en línea (sin
        streamear). Solo el texto de la respuesta final se streamea.
        """
        rag_results = retrieve_context(query=user_message)
        system_prompt = self._build_system_prompt(rag_results, map_state)
        llm_messages = [{"role": "system", "content": system_prompt}, *history]
        sources = [chunk["metadata"] for chunk in rag_results] if rag_results else []

        yield from self._stream_llm_loop(llm_messages, sources)

    def _stream_llm_loop(self, llm_messages: list, sources: list,
                         max_iterations: int = 5) -> Generator[dict, None, None]:
        """Bucle de streaming: ejecuta tools server/MCP en línea, streamea texto."""
        tools = get_langchain_tools()
        layers: list[dict] = []

        for _iteration in range(max_iterations):
            # Intentar streamear primero
            accumulated_text = ""
            accumulated_tool_calls = []
            has_tool_calls = False

            for chunk in self.provider.stream(llm_messages, tools=tools if tools else None):
                if chunk.has_tool_calls:
                    has_tool_calls = True
                    accumulated_tool_calls = chunk.tool_calls
                elif chunk.content:
                    accumulated_text += chunk.content
                    yield {"type": "text_delta", "text": chunk.content}

            if not has_tool_calls:
                # Solo texto — emitir metadata y terminar
                if sources:
                    yield {"type": "sources", "sources": sources}
                for layer in layers:
                    yield {"type": "layer", "layer": layer}
                yield {"type": "done"}
                return

            # Hay tool calls — clasificar y ejecutar
            server_calls, mcp_calls, map_calls = self._classify_tool_calls(
                accumulated_tool_calls,
            )

            if server_calls or mcp_calls:
                # Ejecutar server/MCP tools en línea (sin streamear)
                for tc in server_calls:
                    formatted = self._execute_server_tool(tc, layers)
                    self._append_tool_messages(llm_messages, type("R", (), {"content": accumulated_text})(), tc, formatted)
                    self._collect_geojson_layer(formatted, layers)

                for tc in mcp_calls:
                    formatted = self._execute_mcp_tool(tc)
                    self._append_tool_messages(llm_messages, type("R", (), {"content": accumulated_text})(), tc, formatted)

                if map_calls:
                    yield {"type": "tool_call", "toolCalls": map_calls}
                    if sources:
                        yield {"type": "sources", "sources": sources}
                    for layer in layers:
                        yield {"type": "layer", "layer": layer}
                    yield {"type": "done"}
                    return
                # Continuar loop para que el LLM procese los resultados
            else:
                # Solo map calls — emitir y terminar
                yield {"type": "tool_call", "toolCalls": map_calls}
                if sources:
                    yield {"type": "sources", "sources": sources}
                for layer in layers:
                    yield {"type": "layer", "layer": layer}
                yield {"type": "done"}
                return

        logger.warning("Stream: MCP iteration limit (%d) reached", max_iterations)
        yield {"type": "text_delta", "text": "Se alcanzó el límite de iteraciones."}
        yield {"type": "done"}

    def process_tool_result(self, tool_name: str, tool_result: dict,
                            success: bool, history: list) -> AgentResponse:
        """
        Procesa el resultado de una ejecución de herramienta y genera una respuesta de seguimiento.

        A diferencia de run(), esto NO incluye el estado del mapa.
        Las herramientas MCP aún se manejan en línea si el LLM las solicita.
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
        Llama al LLM en un bucle, ejecutando herramientas del servidor/MCP en línea.

        - Si el LLM devuelve solo herramientas del mapa → devolverlas como tool_call.
        - Si el LLM devuelve herramientas server/MCP → ejecutarlas, retroalimentar resultados, repetir.
        - Si el LLM devuelve texto → devolver como texto.

        Los resultados de herramientas del servidor que contengan GeoJSON
        (FeatureCollection) se acumulan en ``layers`` y se incluyen en la
        respuesta final para que la vista los envíe al frontend.
        """
        tools = get_langchain_tools()
        sources = [chunk["metadata"] for chunk in rag_results] if rag_results else []
        layers: list[dict] = []

        for _iteration in range(max_iterations):
            response = self.provider.chat(
                llm_messages,
                tools=tools if tools else None,
            )

            if not response.has_tool_calls:
                return self._build_response(response, sources, layers)

            server_calls, mcp_calls, map_calls = self._classify_tool_calls(
                response.tool_calls,
            )

            if server_calls or mcp_calls:
                for tc in server_calls:
                    formatted = self._execute_server_tool(tc, layers)
                    self._append_tool_messages(llm_messages, response, tc, formatted)
                    self._collect_geojson_layer(formatted, layers)

                for tc in mcp_calls:
                    formatted = self._execute_mcp_tool(tc)
                    self._append_tool_messages(llm_messages, response, tc, formatted)

                if map_calls:
                    return AgentResponse.tool_call(
                        text=response.content or "Ejecutando acción en el mapa...",
                        tool_calls=map_calls,
                        sources=sources,
                        layers=layers,
                    )
            else:
                return AgentResponse.tool_call(
                    text=response.content or "Ejecutando acción en el mapa...",
                    tool_calls=map_calls,
                    sources=sources,
                    layers=layers,
                )

        logger.warning("MCP iteration limit (%d) reached", max_iterations)
        return AgentResponse.text(
            "Se alcanzó el límite de iteraciones de herramientas MCP.",
        )

    def _classify_tool_calls(self, tool_calls: list) -> tuple[list, list, list]:
        """Clasifica tool calls en server-side, MCP y map (frontend)."""
        server_calls = []
        mcp_calls = []
        map_calls = []
        for tc in tool_calls:
            if has_executor(tc["name"]):
                server_calls.append(tc)
            elif self.mcp_manager and self.mcp_manager.is_mcp_tool(tc["name"]):
                mcp_calls.append(tc)
            else:
                map_calls.append(tc)
        return server_calls, mcp_calls, map_calls

    @staticmethod
    def _execute_server_tool(tc: dict, layers: list = None) -> str:
        """Ejecuta una herramienta del servidor y devuelve el resultado formateado.

        Si el resultado contiene una clave ``_layers``, los elementos se extraen
        y se añaden a *layers* (modificable in-situ) para que no lleguen al LLM.
        """
        try:
            executor = get_executor(tc["name"])
            result = executor(**tc["args"])
            if layers is not None and isinstance(result, dict) and "_layers" in result:
                extra = result.pop("_layers")
                if isinstance(extra, list):
                    layers.extend(extra)
            formatted = (
                json.dumps({"result": result}, ensure_ascii=False)
                if not isinstance(result, str) else result
            )
            logger.info("Server tool '%s' executed successfully", tc["name"])
            return formatted
        except Exception as e:
            logger.exception("Server tool '%s' failed", tc["name"])
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    def _execute_mcp_tool(self, tc: dict) -> str:
        """Ejecuta una herramienta MCP y devuelve el resultado formateado."""
        try:
            result = self.mcp_manager.execute_tool(tc["name"], tc["args"])
            formatted = self._format_mcp_result(result)
            logger.info("MCP tool '%s' executed successfully", tc["name"])
            return formatted
        except Exception as e:
            logger.exception("MCP tool '%s' failed", tc["name"])
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    @staticmethod
    def _append_tool_messages(llm_messages: list, response, tc: dict,
                              formatted: str):
        """Añade los mensajes de asistente + resultado de herramienta al historial."""
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

    @staticmethod
    def _collect_geojson_layer(tool_result: str, layers: list[dict]):
        """Si el resultado de una herramienta es un GeoJSON FeatureCollection, lo acumula en layers.

        Si las features tienen label ``"bbox"`` o ``"contour"``, las separa en dos
        capas distintas (``AGENT_MRE_Piscinas`` y ``AGENT_Piscinas``).  En caso
        contrario usa el label de la primera feature como nombre de capa (comportamiento
        anterior).
        """
        try:
            parsed = json.loads(tool_result)
            if isinstance(parsed, dict):
                if parsed.get("type") == "FeatureCollection":
                    features = parsed.get("features", [])

                    # Agrupar features por label
                    groups: dict[str, list] = {}
                    for f in features:
                        lbl = f.get("properties", {}).get("label", "")
                        groups.setdefault(lbl, []).append(f)

                    # Si hay los labels conocidos "bbox"/"contour", separar en dos capas fijas
                    LAYER_NAMES = {"bbox": "AGENT_MRE_Piscinas", "contour": "AGENT_Piscinas"}
                    CONTOUR_STYLE = {
                        "polygon": {
                            "fill": {
                                "color": "#90CAF9",
                                "opacity": 0.5,
                            },
                            "stroke": {
                                "color": "#0D47A1",
                                "width": 3,
                            },
                        },
                    }
                    if any(lbl in LAYER_NAMES for lbl in groups):
                        for lbl, group_features in groups.items():
                            if lbl in LAYER_NAMES and group_features:
                                layer = {
                                    "type": "geojson",
                                    "source": {
                                        "type": "FeatureCollection",
                                        "features": group_features,
                                    },
                                    "name": LAYER_NAMES[lbl],
                                }
                                if lbl == "contour":
                                    layer["style"] = CONTOUR_STYLE
                                layers.append(layer)
                                logger.info(
                                    "Layer GeoJSON '%s': %d features",
                                    LAYER_NAMES[lbl], len(group_features),
                                )
                    else:
                        # Comportamiento anterior: capa única con el label de la primera feature
                        label = "Detecciones"
                        if features and features[0].get("properties", {}).get("label"):
                            label = features[0]["properties"]["label"] + " detectados"
                        layers.append({
                            "type": "geojson",
                            "source": parsed,
                            "name": label,
                        })
                        logger.info(
                            "Layer GeoJSON recolectado: %d features, label='%s'",
                            len(features), label,
                        )
                else:
                    logger.debug(
                        "Tool result no es FeatureCollection (type=%s)",
                        parsed.get("type") if isinstance(parsed, dict) else type(parsed).__name__,
                    )
        except (json.JSONDecodeError, TypeError) as exc:
            logger.debug("Tool result no es JSON válido para layer: %s", exc)

    @staticmethod
    def _format_mcp_result(result) -> str:
        """Convierte el resultado MCP (array de contenido) a una cadena simple para el LLM."""
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

    def _build_response(self, response, sources: list,
                        layers: list = None):
        return AgentResponse.text(
            response.content,
            sources=sources,
            layers=layers or [],
        )

    def _build_system_prompt(self, rag_results: list,
                             map_state: Optional[dict] = None) -> str:
        """Ensambla el prompt del sistema completo a partir de RAG, skills y estado del mapa."""
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
