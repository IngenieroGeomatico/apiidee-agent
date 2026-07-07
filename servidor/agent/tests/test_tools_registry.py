"""
Tests unitarios para el registry de tools.

Cubren el registro programático de tools, la búsqueda por nombre,
el listado completo, el formato LangChain y la carga automática
de definiciones JSON desde el directorio definitions/.
"""
from django.test import TestCase

from agent.tools import registry


class ToolsRegistryTests(TestCase):
    """Suite de tests para el módulo agent.tools.registry."""

    def setUp(self):
        """Resetea el estado global del registry antes de cada test."""
        registry._tools_registry.clear()
        registry._loaded = False

    def tearDown(self):
        """Restaura el estado limpio del registry después de cada test."""
        registry._tools_registry.clear()
        registry._loaded = False

    # ------------------------------------------------------------------
    # register_tool / get_tool_by_name
    # ------------------------------------------------------------------

    def test_register_tool_y_get_tool_by_name(self):
        """register_tool() registra una tool y get_tool_by_name() la encuentra."""
        params = {"type": "object", "properties": {"x": {"type": "number"}}}
        registry.register_tool("miTool", "Descripción de prueba", params)

        tool = registry.get_tool_by_name("miTool")

        self.assertIsNotNone(tool)
        self.assertEqual(tool["name"], "miTool")
        self.assertEqual(tool["description"], "Descripción de prueba")
        self.assertEqual(tool["parameters"], params)

    def test_get_tool_by_name_devuelve_none_para_inexistente(self):
        """get_tool_by_name() devuelve None cuando la tool no existe."""
        result = registry.get_tool_by_name("tool_que_no_existe")
        self.assertIsNone(result)

    # ------------------------------------------------------------------
    # get_all_tools
    # ------------------------------------------------------------------

    def test_get_all_tools_devuelve_todas_las_registradas(self):
        """get_all_tools() devuelve una lista con todas las tools registradas."""
        registry.register_tool("toolA", "A", {"type": "object", "properties": {}})
        registry.register_tool("toolB", "B", {"type": "object", "properties": {}})

        # Marcar _loaded para evitar que _load_definitions añada las reales
        registry._loaded = True

        tools = registry.get_all_tools()

        nombres = {t["name"] for t in tools}
        self.assertIn("toolA", nombres)
        self.assertIn("toolB", nombres)
        self.assertEqual(len(tools), 2)

    # ------------------------------------------------------------------
    # get_langchain_tools
    # ------------------------------------------------------------------

    def test_get_langchain_tools_genera_formato_correcto(self):
        """get_langchain_tools() genera el formato esperado por LangChain bind_tools()."""
        params = {
            "type": "object",
            "properties": {"nivel": {"type": "integer"}},
            "required": ["nivel"],
        }
        registry.register_tool("setNivel", "Cambia el nivel", params)
        registry._loaded = True

        lc_tools = registry.get_langchain_tools()

        self.assertEqual(len(lc_tools), 1)
        tool = lc_tools[0]

        # Estructura de primer nivel
        self.assertEqual(tool["type"], "function")
        self.assertIn("function", tool)

        # Estructura de function
        fn = tool["function"]
        self.assertEqual(fn["name"], "setNivel")
        self.assertEqual(fn["description"], "Cambia el nivel")
        self.assertEqual(fn["parameters"], params)

    # ------------------------------------------------------------------
    # _load_definitions (ficheros JSON reales)
    # ------------------------------------------------------------------

    def test_load_definitions_carga_json_reales(self):
        """_load_definitions() carga los JSON de definitions/ (al menos getMapCenter y zoomTo)."""
        registry._load_definitions()

        self.assertTrue(registry._loaded)
        self.assertGreaterEqual(len(registry._tools_registry), 2)

        # Verificar tools concretas que deben existir
        center = registry._tools_registry.get("getMapCenter")
        self.assertIsNotNone(center, "getMapCenter debe existir en definitions/")
        self.assertIn("description", center)
        self.assertIn("parameters", center)

        zoom = registry._tools_registry.get("zoomTo")
        self.assertIsNotNone(zoom, "zoomTo debe existir en definitions/")
        self.assertIn("lat", zoom["parameters"]["properties"])
        self.assertIn("lon", zoom["parameters"]["properties"])

    def test_load_definitions_no_recarga_si_ya_cargado(self):
        """_load_definitions() no recarga si _loaded ya es True."""
        registry._loaded = True
        registry._load_definitions()

        # No debe haber cargado nada porque _loaded estaba en True
        self.assertEqual(len(registry._tools_registry), 0)
