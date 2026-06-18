from django.apps import AppConfig


class AgentConfig(AppConfig):
    """Configuración de la aplicación Django 'agent'."""
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent'

    def ready(self):
        """Inicializa el registro de herramientas y habilidades al arrancar la aplicación."""
        # Trigger auto-discovery of tool and skill definitions
        from agent.tools.registry import get_all_tools
        from agent.skills.base import SkillRegistry

        get_all_tools()          # loads tools/definitions/*.json
        SkillRegistry.get_all()  # loads skills/definitions/*.yaml
