from .base import BaseSkill, SkillRegistry


class NavigationSkill(BaseSkill):
    """Skill for navigating the map, searching locations, and controlling the view."""

    @property
    def name(self) -> str:
        return "navigation"

    @property
    def description(self) -> str:
        return "Navigate the map, search locations, and control the view"

    @property
    def tools(self):
        return ["getMapCenter", "getCurrentZoom", "getMapExtent", "zoomTo", "setZoom"]

    @property
    def system_prompt_addition(self) -> str:
        return """When the user wants to navigate the map or find a location:
1. Use getMapCenter() to check current position if needed
2. Use zoomTo(lat, lon, zoom) to move the map to specific coordinates
3. Use setZoom(level) to change zoom level
4. Use getCurrentZoom() to check current zoom
5. Use getMapExtent() to understand current view bounds
Always confirm what you did after executing navigation tools."""


# Auto-register on import
SkillRegistry.register(NavigationSkill())
