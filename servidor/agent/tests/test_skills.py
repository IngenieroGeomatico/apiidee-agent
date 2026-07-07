"""
Tests unitarios para el registry de skills.

Cubren la clase YamlSkill (inicialización, copia de tools) y el
singleton SkillRegistry (unicidad, registro sin duplicados,
generación de system prompt y carga de definiciones YAML reales).
"""
from django.test import TestCase

from agent.skills.base import SkillRegistry, YamlSkill


class YamlSkillTests(TestCase):
    """Tests para la clase YamlSkill."""

    def test_inicializacion_desde_dict(self):
        """YamlSkill se inicializa correctamente a partir de un diccionario."""
        data = {
            "name": "mi_skill",
            "description": "Skill de prueba",
            "tools": ["toolA", "toolB"],
            "prompt": "Instrucciones de prueba",
        }

        skill = YamlSkill(data)

        self.assertEqual(skill.name, "mi_skill")
        self.assertEqual(skill.description, "Skill de prueba")
        self.assertEqual(skill.tools, ["toolA", "toolB"])
        self.assertEqual(skill.system_prompt_addition, "Instrucciones de prueba")

    def test_tools_devuelve_copia_no_referencia(self):
        """YamlSkill.tools devuelve una copia de la lista, no la referencia interna."""
        data = {
            "name": "copia_test",
            "tools": ["toolX"],
        }

        skill = YamlSkill(data)
        tools_a = skill.tools
        tools_b = skill.tools

        # Son listas iguales pero objetos distintos
        self.assertEqual(tools_a, tools_b)
        self.assertIsNot(tools_a, tools_b)

        # Modificar la copia no afecta al skill
        tools_a.append("toolExtra")
        self.assertNotIn("toolExtra", skill.tools)


class SkillRegistryTests(TestCase):
    """Tests para el singleton SkillRegistry."""

    def setUp(self):
        """Resetea el singleton del SkillRegistry antes de cada test."""
        SkillRegistry._instance = None
        SkillRegistry._skills = []
        SkillRegistry._loaded = False

    def tearDown(self):
        """Restaura el singleton del SkillRegistry después de cada test."""
        SkillRegistry._instance = None
        SkillRegistry._skills = []
        SkillRegistry._loaded = False

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    def test_skill_registry_es_singleton(self):
        """SkillRegistry siempre devuelve la misma instancia."""
        a = SkillRegistry()
        b = SkillRegistry()
        self.assertIs(a, b)

    # ------------------------------------------------------------------
    # get_system_prompt
    # ------------------------------------------------------------------

    def test_get_system_prompt_formato_correcto(self):
        """get_system_prompt() genera texto con formato '### Skill: nombre'."""
        skill = YamlSkill({
            "name": "nav_test",
            "prompt": "Usa getMapCenter primero.",
        })
        SkillRegistry._loaded = True
        SkillRegistry.register(skill)

        prompt = SkillRegistry.get_system_prompt()

        self.assertIn("### Skill: nav_test", prompt)
        self.assertIn("Usa getMapCenter primero.", prompt)

    # ------------------------------------------------------------------
    # register (no duplica)
    # ------------------------------------------------------------------

    def test_register_no_duplica_skills_con_mismo_nombre(self):
        """register() no añade un skill si ya existe uno con el mismo nombre."""
        SkillRegistry._loaded = True

        skill_v1 = YamlSkill({"name": "dup", "prompt": "v1"})
        skill_v2 = YamlSkill({"name": "dup", "prompt": "v2"})

        SkillRegistry.register(skill_v1)
        SkillRegistry.register(skill_v2)

        todos = SkillRegistry.get_all()
        nombres = [s.name for s in todos]
        self.assertEqual(nombres.count("dup"), 1)

        # Se mantiene el primero registrado
        self.assertEqual(todos[0].system_prompt_addition, "v1")

    # ------------------------------------------------------------------
    # get_all con definiciones YAML reales
    # ------------------------------------------------------------------

    def test_get_all_carga_definitions_yaml_reales(self):
        """get_all() carga las definitions YAML reales (navigation, layer_management)."""
        skills = SkillRegistry.get_all()

        nombres = [s.name for s in skills]
        self.assertIn("navigation", nombres, "El skill 'navigation' debe existir en definitions/")
        self.assertIn("layer_management", nombres, "El skill 'layer_management' debe existir en definitions/")

        # Cada skill cargado debe tener tools y prompt
        for skill in skills:
            self.assertTrue(len(skill.tools) > 0, f"El skill '{skill.name}' debe tener al menos una tool")
            self.assertTrue(len(skill.system_prompt_addition) > 0, f"El skill '{skill.name}' debe tener prompt")
