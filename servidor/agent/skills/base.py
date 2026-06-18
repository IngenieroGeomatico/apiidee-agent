"""
Skill Registry — Auto-discovers skill definitions from YAML files.

Skills are defined as YAML files in skills/definitions/*.yaml.
Each file contains: name, description, tools (list), and prompt (text).

To add a new skill: create a new .yaml file in skills/definitions/.
No Python code changes needed.

For advanced skills that need custom logic, extend BaseSkill and register manually.
"""
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

DEFINITIONS_DIR = Path(__file__).resolve().parent / "definitions"


class BaseSkill(ABC):
    """Base class for all skills. Extend this for custom skills with logic."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre único de la habilidad."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Descripción breve de lo que hace la habilidad."""
        pass

    @property
    @abstractmethod
    def tools(self) -> List[str]:
        """Lista de nombres de herramientas que esta habilidad utiliza."""
        pass

    @property
    @abstractmethod
    def system_prompt_addition(self) -> str:
        """Texto adicional para el prompt del sistema que define el comportamiento de la habilidad."""
        pass


class YamlSkill(BaseSkill):
    """A skill loaded from a YAML definition file."""

    def __init__(self, data: dict):
        """Inicializa una habilidad a partir de un diccionario con los datos del YAML."""
        self._name = data["name"]
        self._description = data.get("description", "")
        self._tools = data.get("tools", [])
        self._prompt = data.get("prompt", "")

    @property
    def name(self):
        """Nombre único de la habilidad."""
        return self._name

    @property
    def description(self):
        """Descripción breve de lo que hace la habilidad."""
        return self._description

    @property
    def tools(self):
        """Lista de nombres de herramientas que esta habilidad utiliza."""
        return list(self._tools)

    @property
    def system_prompt_addition(self):
        """Texto adicional para el prompt del sistema que define el comportamiento de la habilidad."""
        return self._prompt


class SkillRegistry:
    """Singleton registry that collects and manages all active skills."""

    _instance = None
    _skills: List[BaseSkill] = []
    _loaded = False

    def __new__(cls):
        """Crea o devuelve la única instancia del singleton."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._skills = []
            cls._loaded = False
        return cls._instance

    @classmethod
    def _load_definitions(cls):
        """Scan definitions/ directory and load all .yaml skill files."""
        if cls._loaded:
            return

        if not DEFINITIONS_DIR.is_dir():
            logger.warning("Skill definitions directory not found: %s", DEFINITIONS_DIR)
            cls._loaded = True
            return

        try:
            import yaml
        except ImportError:
            logger.error("PyYAML not installed. Cannot load YAML skill definitions.")
            cls._loaded = True
            return

        for yaml_file in sorted(DEFINITIONS_DIR.glob("*.yaml")):
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)

                if not data or not data.get("name"):
                    logger.warning("Skill definition missing 'name': %s", yaml_file.name)
                    continue

                skill = YamlSkill(data)
                if not any(s.name == skill.name for s in cls._skills):
                    cls._skills.append(skill)
                    logger.debug("Loaded skill: %s (from %s)", skill.name, yaml_file.name)

            except Exception as exc:
                logger.error("Failed to load skill definition %s: %s", yaml_file.name, exc)

        logger.info("Loaded %d skill definitions", len(cls._skills))
        cls._loaded = True

    @classmethod
    def register(cls, skill: BaseSkill):
        """Register a skill programmatically (for custom skills not defined in YAML)."""
        if not any(s.name == skill.name for s in cls._skills):
            cls._skills.append(skill)

    @classmethod
    def get_all(cls) -> List[BaseSkill]:
        """Devuelve todas las habilidades registradas, cargando definiciones si es necesario."""
        cls._load_definitions()
        return list(cls._skills)

    @classmethod
    def get_system_prompt(cls) -> str:
        """Combine all skill prompt additions into one string."""
        cls._load_definitions()
        parts = []
        for skill in cls._skills:
            if skill.system_prompt_addition:
                parts.append(f"### Skill: {skill.name}\n{skill.system_prompt_addition}")
        return "\n\n".join(parts)


