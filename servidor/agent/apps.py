from django.apps import AppConfig


class AgentConfig(AppConfig):
    """Configuración de la aplicación Django 'agent'."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent'

    def ready(self):
        """Inicializa el registro de herramientas, habilidades y MCP al arrancar."""
        from django.conf import settings

        # Auto-descargar modelos ML si faltan (solo una vez)
        try:
            from ml_models.download import ensure_models
            ensure_models()
        except Exception:
            import logging
            logging.getLogger(__name__).warning(
                "No se pudieron verificar modelos ML. "
                "Ejecuta: python -m ml_models.download",
            )

        from agent.tools.registry import get_all_tools, register_mcp_tools
        from agent.skills.base import SkillRegistry

        get_all_tools()          # loads tools/definitions/*.json
        SkillRegistry.get_all()  # loads skills/definitions/*.yaml

        # Initialize MCP connections and register their tools
        mcp_path = getattr(settings, 'MCP_SERVERS_PATH', None)
        if mcp_path:
            from agent.mcp.manager import MCPServerManager
            MCPServerManager.initialize(mcp_path)
            register_mcp_tools()
