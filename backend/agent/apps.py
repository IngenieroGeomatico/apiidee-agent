from django.apps import AppConfig


class AgentConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent'

    def ready(self):
        # Import tools and skills to trigger registration
        import agent.tools.map_tools  # noqa: F401
        import agent.skills.navigation  # noqa: F401
        import agent.skills.layer_management  # noqa: F401
