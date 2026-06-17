from .base import BaseSkill, SkillRegistry


class LayerManagementSkill(BaseSkill):
    """Skill for managing map layers — add, remove, and list WMS/WMTS/WFS layers."""

    @property
    def name(self) -> str:
        return "layer_management"

    @property
    def description(self) -> str:
        return "Manage map layers - add, remove, and list WMS/WMTS/WFS layers"

    @property
    def tools(self):
        return ["listActiveLayers", "addWMSLayer", "removeLayer"]

    @property
    def system_prompt_addition(self) -> str:
        return """When the user wants to manage map layers:
1. Use listActiveLayers() to see what's currently on the map
2. Use addWMSLayer(url, name) to add a new WMS layer
3. Use removeLayer(name) to remove a layer by name
Always list layers first before removing to confirm the correct layer name.
When adding layers, ask for the WMS URL and layer name if not provided."""


# Auto-register on import
SkillRegistry.register(LayerManagementSkill())
