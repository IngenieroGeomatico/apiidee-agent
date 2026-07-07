"""Tests unitarios para el módulo ML de detección de objetos."""
import json
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from django.test import TestCase

from agent.ml.base import BaseDetector
from agent.ml.registry import (
    _detector_registry,
    detector,
    get_detector,
    get_detector_names,
    list_detectors,
)


# ─────────────────────────── Detector de prueba ───────────────────────────

class _DummyDetector(BaseDetector):
    """Detector ficticio para tests."""

    @property
    def name(self):
        return "dummy_detector"

    @property
    def label(self):
        return "Dummy"

    @property
    def description(self):
        return "Detector ficticio para tests"

    def detect(self, image, bbox, srs="EPSG:3857"):
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {
                    "detector": self.name,
                    "label": "Test",
                    "confidence": 0.99,
                },
            }],
        }


# ─────────────────────────── Tests BaseDetector ───────────────────────────

class BaseDetectorTest(TestCase):
    """Tests para la clase base BaseDetector."""

    def test_get_info_devuelve_dict_correcto(self):
        """get_info() devuelve name, label y description del detector."""
        det = _DummyDetector()
        info = det.get_info()
        self.assertEqual(info["name"], "dummy_detector")
        self.assertEqual(info["label"], "Dummy")
        self.assertEqual(info["description"], "Detector ficticio para tests")

    def test_detect_devuelve_feature_collection(self):
        """detect() devuelve un GeoJSON FeatureCollection válido."""
        det = _DummyDetector()
        bbox = {"minX": 0, "minY": 0, "maxX": 1, "maxY": 1}
        result = det.detect(image=None, bbox=bbox)
        self.assertEqual(result["type"], "FeatureCollection")
        self.assertGreater(len(result["features"]), 0)

    def test_feature_tiene_properties_requeridas(self):
        """Cada Feature debe incluir detector, label y confidence."""
        det = _DummyDetector()
        bbox = {"minX": 0, "minY": 0, "maxX": 1, "maxY": 1}
        result = det.detect(image=None, bbox=bbox)
        props = result["features"][0]["properties"]
        self.assertIn("detector", props)
        self.assertIn("label", props)
        self.assertIn("confidence", props)


# ─────────────────────────── Tests Registry ───────────────────────────────

class DetectorRegistryTest(TestCase):
    """Tests para el registry de detectores."""

    def setUp(self):
        """Guarda y limpia el estado del registry antes de cada test."""
        self._saved_registry = dict(_detector_registry)
        _detector_registry.clear()

    def tearDown(self):
        """Restaura el estado original del registry."""
        _detector_registry.clear()
        _detector_registry.update(self._saved_registry)

    def test_decorator_registra_detector(self):
        """El decorador @detector registra la instancia en el registry."""
        @detector
        class TestDet(BaseDetector):
            @property
            def name(self): return "test_det"
            @property
            def label(self): return "Test"
            @property
            def description(self): return "Test detector"
            def detect(self, image, bbox, srs="EPSG:3857"):
                return {"type": "FeatureCollection", "features": []}

        self.assertIn("test_det", _detector_registry)
        self.assertIsInstance(_detector_registry["test_det"], TestDet)

    def test_decorator_no_rompe_si_init_falla(self):
        """Si __init__ del detector falla, se registra warning pero no excepción."""
        @detector
        class BadDetector(BaseDetector):
            @property
            def name(self): return "bad"
            @property
            def label(self): return "Bad"
            @property
            def description(self): return "Falla al init"
            def __init__(self):
                raise RuntimeError("Modelo no encontrado")
            def detect(self, image, bbox, srs="EPSG:3857"):
                return {"type": "FeatureCollection", "features": []}

        self.assertNotIn("bad", _detector_registry)

    def test_get_detector_existente(self):
        """get_detector() devuelve el detector si existe."""
        instance = _DummyDetector()
        _detector_registry["dummy_detector"] = instance
        with patch("agent.ml.registry._discovered", True):
            result = get_detector("dummy_detector")
        self.assertIs(result, instance)

    def test_get_detector_inexistente(self):
        """get_detector() devuelve None si el detector no existe."""
        with patch("agent.ml.registry._discovered", True):
            result = get_detector("no_existe")
        self.assertIsNone(result)

    def test_list_detectors_formato(self):
        """list_detectors() devuelve lista de dicts con name, label, description."""
        instance = _DummyDetector()
        _detector_registry["dummy_detector"] = instance
        with patch("agent.ml.registry._discovered", True):
            result = list_detectors()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "dummy_detector")
        self.assertEqual(result[0]["label"], "Dummy")

    def test_get_detector_names(self):
        """get_detector_names() devuelve lista de nombres."""
        _detector_registry["det_a"] = _DummyDetector()
        _detector_registry["det_b"] = _DummyDetector()
        with patch("agent.ml.registry._discovered", True):
            names = get_detector_names()
        self.assertIn("det_a", names)
        self.assertIn("det_b", names)


# ─────────────────────────── Tests Inference ──────────────────────────────

class RunDetectionTest(TestCase):
    """Tests para el pipeline de inferencia run_detection()."""

    def test_detector_no_encontrado(self):
        """Si el detector no existe, devuelve JSON con error y lista de disponibles."""
        with patch("agent.ml.registry._discovered", True), \
             patch("agent.ml.registry._detector_registry", {}):
            from agent.ml.inference import run_detection
            result = run_detection("inexistente", {"minX": 0, "minY": 0, "maxX": 1, "maxY": 1})

        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("inexistente", data["error"])

    @patch("agent.ml.inference.fetch_wms_image")
    def test_pipeline_completo_con_detector_dummy(self, mock_fetch):
        """El pipeline completo descarga imagen, ejecuta detector y devuelve GeoJSON."""
        mock_image = MagicMock()
        mock_fetch.return_value = mock_image

        instance = _DummyDetector()
        with patch("agent.ml.registry._discovered", True), \
             patch("agent.ml.registry._detector_registry", {"dummy_detector": instance}):
            from agent.ml.inference import run_detection
            result = run_detection(
                "dummy_detector",
                {"minX": -3.7, "minY": 40.4, "maxX": -3.6, "maxY": 40.5},
            )

        data = json.loads(result)
        self.assertEqual(data["type"], "FeatureCollection")
        self.assertGreater(len(data["features"]), 0)
        mock_fetch.assert_called_once()

    @patch("agent.ml.inference.fetch_wms_image", side_effect=Exception("WMS caído"))
    def test_error_descargando_imagen(self, mock_fetch):
        """Si la descarga WMS falla, devuelve JSON con el error."""
        instance = _DummyDetector()
        with patch("agent.ml.registry._discovered", True), \
             patch("agent.ml.registry._detector_registry", {"dummy_detector": instance}):
            from agent.ml.inference import run_detection
            result = run_detection(
                "dummy_detector",
                {"minX": 0, "minY": 0, "maxX": 1, "maxY": 1},
            )

        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("WMS caído", data["error"])

    @patch("agent.ml.inference.fetch_wms_image")
    def test_error_en_detector(self, mock_fetch):
        """Si el detector lanza excepción, devuelve JSON con el error."""
        mock_fetch.return_value = MagicMock()

        class _FailingDetector(BaseDetector):
            @property
            def name(self): return "failing"
            @property
            def label(self): return "Failing"
            @property
            def description(self): return "Falla siempre"
            def detect(self, image, bbox, srs="EPSG:3857"):
                raise RuntimeError("Error de inferencia")

        instance = _FailingDetector()
        with patch("agent.ml.registry._discovered", True), \
             patch("agent.ml.registry._detector_registry", {"failing": instance}):
            from agent.ml.inference import run_detection
            result = run_detection(
                "failing",
                {"minX": 0, "minY": 0, "maxX": 1, "maxY": 1},
            )

        data = json.loads(result)
        self.assertIn("error", data)
        self.assertIn("Error de inferencia", data["error"])


# ─────────────────────────── Tests PoolDetector ───────────────────────────

class PoolDetectorDemoTest(TestCase):
    """Tests para el detector de piscinas en modo demo."""

    def test_demo_genera_feature_collection(self):
        """En modo demo (sin modelo), genera un FeatureCollection con detecciones ficticias."""
        from agent.ml.detectors.pool_detector import PoolDetector

        det = PoolDetector()
        bbox = {"minX": -400000, "minY": 4800000, "maxX": -390000, "maxY": 4810000}
        result = det.detect(image=None, bbox=bbox)

        self.assertEqual(result["type"], "FeatureCollection")
        self.assertEqual(len(result["features"]), 3)

    def test_demo_features_tienen_geometria_polygon(self):
        """Las detecciones demo son polígonos."""
        from agent.ml.detectors.pool_detector import PoolDetector

        det = PoolDetector()
        bbox = {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100}
        result = det.detect(image=None, bbox=bbox)

        for feature in result["features"]:
            self.assertEqual(feature["geometry"]["type"], "Polygon")

    def test_demo_properties_incluyen_confidence(self):
        """Las detecciones demo incluyen confidence entre 0 y 1."""
        from agent.ml.detectors.pool_detector import PoolDetector

        det = PoolDetector()
        bbox = {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100}
        result = det.detect(image=None, bbox=bbox)

        for feature in result["features"]:
            conf = feature["properties"]["confidence"]
            self.assertGreaterEqual(conf, 0)
            self.assertLessEqual(conf, 1)

    def test_info_detector(self):
        """get_info() devuelve datos correctos del detector de piscinas."""
        from agent.ml.detectors.pool_detector import PoolDetector

        det = PoolDetector()
        info = det.get_info()
        self.assertEqual(info["name"], "pool_detector")
        self.assertEqual(info["label"], "Piscinas")
        self.assertIn("piscinas", info["description"].lower())

    def test_pixel_to_geo_esquina_superior_izquierda(self):
        """_pixel_to_geo(0, 0) devuelve la esquina superior-izquierda del bbox."""
        from agent.ml.detectors.pool_detector import PoolDetector

        bbox = {"minX": 10, "minY": 20, "maxX": 30, "maxY": 40}
        x, y = PoolDetector._pixel_to_geo(0, 0, 100, 100, bbox)
        self.assertAlmostEqual(x, 10.0)
        self.assertAlmostEqual(y, 40.0)

    def test_pixel_to_geo_esquina_inferior_derecha(self):
        """_pixel_to_geo(W, H) devuelve la esquina inferior-derecha del bbox."""
        from agent.ml.detectors.pool_detector import PoolDetector

        bbox = {"minX": 10, "minY": 20, "maxX": 30, "maxY": 40}
        x, y = PoolDetector._pixel_to_geo(100, 100, 100, 100, bbox)
        self.assertAlmostEqual(x, 30.0)
        self.assertAlmostEqual(y, 20.0)

    def test_bbox_to_polygon_devuelve_anillo_cerrado(self):
        """_bbox_to_polygon() devuelve 5 puntos (anillo cerrado GeoJSON)."""
        from agent.ml.detectors.pool_detector import PoolDetector

        bbox = {"minX": 0, "minY": 0, "maxX": 100, "maxY": 100}
        polygon = PoolDetector._bbox_to_polygon(10, 10, 50, 50, 100, 100, bbox)
        self.assertEqual(len(polygon), 5)
        self.assertEqual(polygon[0], polygon[-1])


# ─────────────────────────── Tests Executors ML ───────────────────────────

class ExecutorsMLTest(TestCase):
    """Tests para los tool executors de detección ML."""

    def test_list_detectors_executor_registrado(self):
        """El executor listDetectors está registrado."""
        from agent.tools.executors import has_executor
        self.assertTrue(has_executor("listDetectors"))

    def test_detect_objects_executor_registrado(self):
        """El executor detectObjects está registrado."""
        from agent.tools.executors import has_executor
        self.assertTrue(has_executor("detectObjects"))
