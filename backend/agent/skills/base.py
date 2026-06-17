"""
Skill — Domain expertise that groups tools + specialized prompt context.

A Skill teaches the agent HOW to use a set of tools for a specific domain
(e.g., navigation, layer management). It provides:
- A set of tool names the skill uses
- A system prompt addition that guides the LLM on when/how to use those tools
"""
from abc import ABC, abstractmethod
from typing import List


class BaseSkill(ABC):
    """Base class for all skills."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the skill."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of what the skill does."""
        pass

    @property
    @abstractmethod
    def tools(self) -> List[str]:
        """List of tool names this skill uses."""
        pass

    @property
    @abstractmethod
    def system_prompt_addition(self) -> str:
        """Additional system prompt text that guides the LLM for this skill."""
        pass


class SkillRegistry:
    """Registry that collects and manages all active skills."""

    _instance = None
    _skills: List[BaseSkill] = []

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._skills = []
        return cls._instance

    @classmethod
    def register(cls, skill: BaseSkill):
        """Register a skill instance."""
        # Avoid duplicates
        if not any(s.name == skill.name for s in cls._skills):
            cls._skills.append(skill)

    @classmethod
    def get_all(cls) -> List[BaseSkill]:
        return list(cls._skills)

    @classmethod
    def get_system_prompt(cls) -> str:
        """Combine all skill prompt additions into one string."""
        parts = []
        for skill in cls._skills:
            if skill.system_prompt_addition:
                parts.append(f"### Skill: {skill.name}\n{skill.system_prompt_addition}")
        return "\n\n".join(parts)

    @classmethod
    def get_tool_names(cls) -> List[str]:
        """Get union of all tool names from all skills."""
        names = set()
        for skill in cls._skills:
            names.update(skill.tools)
        return list(names)
