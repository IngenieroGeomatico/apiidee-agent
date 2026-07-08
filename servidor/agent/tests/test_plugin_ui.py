from pathlib import Path
import unittest

class ChatAgentPluginTest(unittest.TestCase):
    """Comprueba que el plugin contiene los elementos de selector de proveedor y modelo."""
    def test_provider_and_model_select_present(self):
        plugin_path = Path(__file__).resolve().parents[3] / "plugin" / "chatagent.js"
        self.assertTrue(plugin_path.is_file(), f"No se encontró {plugin_path}")
        content = plugin_path.read_text(encoding="utf-8")
        self.assertIn('id="chatagent-provider-select"', content)
        self.assertIn('id="chatagent-model-select"', content)
