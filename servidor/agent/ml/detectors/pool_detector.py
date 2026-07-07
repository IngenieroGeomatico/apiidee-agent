"""
Detector de piscinas — Ejemplo de detector ML sobre imágenes aéreas.

Este fichero sirve como plantilla para integrar un modelo real de detección.
Actualmente contiene un placeholder que genera detecciones ficticias para
verificar que el pipeline completo funciona (WMS → modelo → GeoJSON → mapa).

Para integrar un modelo real:
  1. Exportar el modelo a ONNX (recomendado) o el formato que prefieras
  2. Colocar los pesos en ``servidor/ml_models/pool_detector.onnx``
  3. Reemplazar el método ``detect()`` con la inferencia real
  4. Ajustar ``_load_model()`` para cargar el formato correcto

Formatos soportados (ejemplos de carga):

    # ONNX (recomendado — ligero, sin PyTorch/TF)
    import onnxruntime as ort
    session = ort.InferenceSession("servidor/ml_models/pool_detector.onnx")

    # YOLOv8 (ultralytics)
    from ultralytics import YOLO
    model = YOLO("servidor/ml_models/pool_detector.pt")

    # PyTorch
    import torch
    model = torch.load("servidor/ml_models/pool_detector.pt")

    # TensorFlow Lite
    import tflite_runtime.interpreter as tflite
    interpreter = tflite.Interpreter("servidor/ml_models/pool_detector.tflite")
"""
import logging
from pathlib import Path
from typing import Any, Dict, List

from agent.ml.base import BaseDetector
from agent.ml.registry import detector

logger = logging.getLogger(__name__)

# Ruta donde se esperan los pesos del modelo
_MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ml_models"
_MODEL_PATH = _MODEL_DIR / "pool_detector.onnx"


@detector
class PoolDetector(BaseDetector):
    """Detecta piscinas en imágenes aéreas/satélite.

    Cuando el modelo real esté disponible, reemplazar ``_load_model()``
    y ``detect()`` con la lógica de inferencia correspondiente.
    """

    @property
    def name(self) -> str:
        return "pool_detector"

    @property
    def label(self) -> str:
        return "Piscinas"

    @property
    def description(self) -> str:
        return (
            "Detecta piscinas en imágenes aéreas u ortofotografías. "
            "Recibe una imagen de la zona del mapa y devuelve un GeoJSON "
            "con los polígonos de las piscinas encontradas."
        )

    def __init__(self):
        """Carga el modelo una sola vez. Si no existe, funciona en modo demo."""
        self.model = self._load_model()

    def _load_model(self):
        """Carga los pesos del modelo desde disco.

        Devuelve None si el fichero no existe (modo demo con detecciones
        ficticias para probar el pipeline).
        """
        if not _MODEL_PATH.exists():
            logger.warning(
                "Modelo de piscinas no encontrado en %s. "
                "Funcionando en modo demo (detecciones ficticias). "
                "Coloca el modelo en esa ruta para activar la detección real.",
                _MODEL_PATH,
            )
            return None

        # ── Descomentar según el formato del modelo ──────────────────
        #
        # ONNX:
        # import onnxruntime as ort
        # return ort.InferenceSession(str(_MODEL_PATH))
        #
        # YOLOv8:
        # from ultralytics import YOLO
        # return YOLO(str(_MODEL_PATH))
        #
        # PyTorch:
        # import torch
        # return torch.load(str(_MODEL_PATH), map_location="cpu")
        # ─────────────────────────────────────────────────────────────

        logger.info("Modelo de piscinas cargado desde %s", _MODEL_PATH)
        return None  # Reemplazar con la carga real

    def detect(self, image: Any, bbox: Dict, srs: str = "EPSG:3857") -> Dict:
        """Ejecuta la detección de piscinas sobre la imagen.

        Args:
            image: Imagen PIL.Image.Image en modo RGB.
            bbox: Extensión geográfica ``{minX, minY, maxX, maxY}``.
            srs: Sistema de referencia del bbox.

        Returns:
            GeoJSON FeatureCollection con los polígonos detectados.
        """
        if self.model is None:
            return self._demo_detection(bbox, srs)

        # ── Inferencia real (reemplazar este bloque) ─────────────────
        #
        # Ejemplo con ONNX:
        #   import numpy as np
        #   img_array = np.array(image)
        #   # Preprocesar según lo que espere el modelo
        #   input_tensor = self._preprocess(img_array)
        #   outputs = self.model.run(None, {"input": input_tensor})
        #   detections = self._postprocess(outputs, bbox, srs)
        #   return self._detections_to_geojson(detections, bbox, srs)
        #
        # Ejemplo con YOLOv8:
        #   results = self.model(image)
        #   return self._yolo_to_geojson(results, bbox, srs)
        # ─────────────────────────────────────────────────────────────

        return self._demo_detection(bbox, srs)

    def _demo_detection(self, bbox: Dict, srs: str) -> Dict:
        """Genera detecciones ficticias para probar el pipeline sin modelo real.

        Crea 3 'piscinas' distribuidas en el bbox para verificar que el
        flujo completo funciona: WMS → detección → GeoJSON → mapa.
        """
        min_x, min_y = bbox["minX"], bbox["minY"]
        max_x, max_y = bbox["maxX"], bbox["maxY"]
        dx = (max_x - min_x) / 4
        dy = (max_y - min_y) / 4

        features = []
        demo_pools = [
            (min_x + dx, min_y + dy, 0.95),
            (min_x + 2 * dx, min_y + 2 * dy, 0.87),
            (min_x + 3 * dx, min_y + 3 * dy, 0.78),
        ]

        pool_w = dx * 0.3
        pool_h = dy * 0.2

        for cx, cy, confidence in demo_pools:
            polygon = [
                [cx - pool_w, cy - pool_h],
                [cx + pool_w, cy - pool_h],
                [cx + pool_w, cy + pool_h],
                [cx - pool_w, cy + pool_h],
                [cx - pool_w, cy - pool_h],
            ]
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [polygon],
                },
                "properties": {
                    "detector": self.name,
                    "label": "Piscina (demo)",
                    "confidence": confidence,
                },
            })

        logger.info(
            "Modo demo: generadas %d detecciones ficticias en bbox %s",
            len(features), bbox,
        )

        return {
            "type": "FeatureCollection",
            "features": features,
        }

    # ── Helpers para cuando integres el modelo real ──────────────────

    @staticmethod
    def _pixel_to_geo(px: float, py: float, img_w: int, img_h: int,
                      bbox: Dict) -> tuple:
        """Convierte coordenadas píxel a coordenadas geográficas.

        Args:
            px, py: Posición en píxeles (origen arriba-izquierda).
            img_w, img_h: Dimensiones de la imagen.
            bbox: Extensión geográfica de la imagen.

        Returns:
            Tupla (x_geo, y_geo) en el SRS del bbox.
        """
        x_geo = bbox["minX"] + (px / img_w) * (bbox["maxX"] - bbox["minX"])
        y_geo = bbox["maxY"] - (py / img_h) * (bbox["maxY"] - bbox["minY"])
        return x_geo, y_geo

    @staticmethod
    def _bbox_to_polygon(x1: float, y1: float, x2: float, y2: float,
                         img_w: int, img_h: int, bbox: Dict) -> List:
        """Convierte un bounding box en píxeles a un polígono GeoJSON.

        Args:
            x1, y1, x2, y2: Coordenadas del bbox en píxeles.
            img_w, img_h: Dimensiones de la imagen.
            bbox: Extensión geográfica.

        Returns:
            Lista de coordenadas para un polígono GeoJSON (anillo cerrado).
        """
        geo_x1, geo_y1 = PoolDetector._pixel_to_geo(x1, y1, img_w, img_h, bbox)
        geo_x2, geo_y2 = PoolDetector._pixel_to_geo(x2, y2, img_w, img_h, bbox)
        return [
            [geo_x1, geo_y1],
            [geo_x2, geo_y1],
            [geo_x2, geo_y2],
            [geo_x1, geo_y2],
            [geo_x1, geo_y1],
        ]
