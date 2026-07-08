import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AgentConfig(AppConfig):
    """Configuración de la aplicación Django 'agent'.

    ``ready()`` centraliza la inicialización de todos los registros
    (tools, skills, MCP, detectores ML) para que ocurra una sola vez
    al arrancar el servidor y no de forma lazy con flags ``_loaded``.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent'

    def ready(self):
        """Inicializa todos los registros al arrancar."""
        self._ensure_ml_models()
        self._load_tools()
        self._load_skills()
        self._load_mcp()
        self._load_ml_detectors()

    @staticmethod
    def _ensure_ml_models():
        """Auto-descarga modelos ML si faltan (solo una vez)."""
        try:
            from ml_models.utils.download import ensure_models
            ensure_models()
        except Exception:
            logger.warning(
                "No se pudieron verificar modelos ML. "
                "Ejecuta: python -m ml_models.utils.download",
            )

    @staticmethod
    def _load_tools():
        """Carga definiciones de herramientas desde tools/definitions/*.json."""
        from agent.tools.registry import get_all_tools
        get_all_tools()

    @staticmethod
    def _load_skills():
        """Carga definiciones de skills desde skills/definitions/*.yaml."""
        from agent.skills.base import SkillRegistry
        SkillRegistry.get_all()

    @staticmethod
    def _load_mcp():
        """Conecta a servidores MCP y registra sus herramientas."""
        from django.conf import settings
        mcp_path = getattr(settings, 'MCP_SERVERS_PATH', None)
        if mcp_path:
            from agent.mcp.manager import MCPServerManager
            from agent.tools.registry import register_mcp_tools
            MCPServerManager.initialize(mcp_path)
            register_mcp_tools()

    @staticmethod
    def _load_ml_detectors():
        """Descubre e instancia todos los detectores ML registrados."""
        try:
            from agent.ml.registry import list_detectors
            detectors = list_detectors()
            if detectors:
                logger.info("Loaded %d ML detectors", len(detectors))
        except Exception:
            logger.warning("No se pudieron cargar los detectores ML.")
