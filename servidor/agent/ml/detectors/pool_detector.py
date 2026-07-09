"""
Detector de piscinas sobre imágenes aéreas con ONNX.

Usa un modelo YOLOv11n fine-tuned para piscinas, exportado a ONNX (~5 MB).
El modelo procede de https://github.com/yourkln/pool-detection y fue
entrenado específicamente con imágenes aéreas de piscinas (1 clase).
Corre con onnxruntime (sin PyTorch, sin ultralytics en producción).
Si el modelo ONNX no está disponible, usa un fallback de segmentación
por color con OpenCV.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from agent.ml.base import BaseDetector
from agent.ml.registry import detector

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ml_models"
_MODEL_PATH = _MODEL_DIR / "pool_detector.onnx"

_CONFIDENCE_THRESHOLD = 0.25
_IOU_THRESHOLD = 0.45
_INPUT_SIZE = 640


@detector
class PoolDetector(BaseDetector):

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
        self.model = self._load_model()

    def _load_model(self):
        if not _MODEL_PATH.exists():
            logger.warning(
                "Modelo ONNX no encontrado en %s. "
                "Ejecuta: python -m ml_models.utils.download",
                _MODEL_PATH,
            )
            return None
        import onnxruntime as ort
        session = ort.InferenceSession(
            str(_MODEL_PATH),
            providers=["CPUExecutionProvider"],
        )
        logger.info("Modelo ONNX cargado desde %s", _MODEL_PATH)
        return session

    def detect(self, image: Any, bbox: Dict, srs: str = "EPSG:3857") -> Dict:
        if self.model is None:
            geojson = self._segment_pools_opencv(image, bbox, srs)
            return self._reproject_geojson(geojson, srs)

        img_array = np.array(image.convert("RGB"))
        orig_h, orig_w = img_array.shape[:2]

        input_tensor, scale, pad = self._preprocess(img_array)
        outputs = self.model.run(None, {self.model.get_inputs()[0].name: input_tensor})
        boxes = self._postprocess(outputs[0], orig_w, orig_h, scale, pad)

        if not boxes:
            logger.info("ONNX sin detecciones, fallback a segmentación por color")
            geojson = self._segment_pools_opencv(image, bbox, srs)
            return self._reproject_geojson(geojson, srs)

        geojson = self._boxes_to_geojson(boxes, img_array, orig_w, orig_h, bbox, srs)
        return self._reproject_geojson(geojson, srs)

    # ── Preprocesado / Postprocesado YOLO ONNX (v8/v11) ────────────

    def _preprocess(self, img: np.ndarray) -> Tuple[np.ndarray, float, Tuple[int, int]]:
        h, w = img.shape[:2]
        scale = min(_INPUT_SIZE / w, _INPUT_SIZE / h)
        nw, nh = int(w * scale), int(h * scale)
        from PIL import Image as PILImage
        pil_img = PILImage.fromarray(img)
        resized = np.array(pil_img.resize((nw, nh), PILImage.BILINEAR))
        canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), 114, dtype=np.uint8)
        pad_x = (_INPUT_SIZE - nw) // 2
        pad_y = (_INPUT_SIZE - nh) // 2
        canvas[pad_y:pad_y + nh, pad_x:pad_x + nw] = resized
        input_tensor = canvas.transpose(2, 0, 1).astype(np.float32) / 255.0
        input_tensor = input_tensor[np.newaxis, :]
        return input_tensor, scale, (pad_x, pad_y)

    def _postprocess(
        self, output: np.ndarray, orig_w: int, orig_h: int,
        scale: float, pad: Tuple[int, int],
    ) -> List[Dict]:
        output = output.squeeze()
        if output.ndim == 2:
            output = output.transpose()

        boxes = []
        for det in output:
            scores = det[4:]
            max_score = float(scores.max())
            if max_score < _CONFIDENCE_THRESHOLD:
                continue

            cx, cy, w, h = float(det[0]), float(det[1]), float(det[2]), float(det[3])
            x1 = (cx - w / 2 - pad[0]) / scale
            y1 = (cy - h / 2 - pad[1]) / scale
            x2 = (cx + w / 2 - pad[0]) / scale
            y2 = (cy + h / 2 - pad[1]) / scale
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(orig_w, x2)
            y2 = min(orig_h, y2)
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue

            boxes.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "confidence": max_score,
                "class_id": int(scores.argmax()),
            })

        boxes = self._nms(boxes)
        return boxes

    @staticmethod
    def _nms(boxes: List[Dict]) -> List[Dict]:
        if not boxes:
            return []
        boxes.sort(key=lambda b: b["confidence"], reverse=True)
        keep = []
        while boxes:
            best = boxes.pop(0)
            keep.append(best)
            boxes = [b for b in boxes if PoolDetector._iou(b, best) < _IOU_THRESHOLD]
        return keep

    @staticmethod
    def _iou(a: Dict, b: Dict) -> float:
        x1, y1 = max(a["x1"], b["x1"]), max(a["y1"], b["y1"])
        x2, y2 = min(a["x2"], b["x2"]), min(a["y2"], b["y2"])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (a["x2"] - a["x1"]) * (a["y2"] - a["y1"])
        area_b = (b["x2"] - b["x1"]) * (b["y2"] - b["y1"])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0

    # ── Segmentación por color (pipeline yourkln/pool-detection) ────

    @staticmethod
    def _detect_pool_contours(roi: np.ndarray, min_area: int = 200,
                              max_area: int = 30000) -> List[np.ndarray]:
        """Detecta contornos de piscinas en un ROI.

        Pipeline:
          1. Edge-preserving filter (suaviza ruido, conserva bordes)
          2. Segmentación HSV azul/turquesa (rango amplio para sombras y reflejos)
          3. Morphology: opening 3x3 ×2 (eliminar ruido) + closing 3x3 ×5 (cerrar huecos)
          4. Contornos filtrados por área + suavizado moderado (epsilon 0.01)

        Ref: https://github.com/yourkln/pool-detection (adaptado)
        """
        import cv2
        filtered = cv2.edgePreservingFilter(roi, flags=1, sigma_s=60, sigma_r=0.4)
        hsv = cv2.cvtColor(filtered, cv2.COLOR_RGB2HSV)

        # Rango HSV equilibrado: captura variaciones de azul sin coger verde/gris
        lower_blue = np.array([78, 50, 70])
        upper_blue = np.array([125, 255, 255])
        mask = cv2.inRange(hsv, lower_blue, upper_blue)

        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=4)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)

        result = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if min_area < area < max_area:
                peri = cv2.arcLength(cnt, True)
                if peri == 0:
                    continue
                epsilon = 0.005 * peri
                smoothed = cv2.approxPolyDP(cnt, epsilon, True)
                result.append(smoothed)
        return result

    def _segment_pools_opencv(self, image: Any, bbox: Dict, srs: str) -> Dict:
        """Fallback sin modelo ONNX: segmenta piscinas por color en la imagen completa."""
        img = np.array(image.convert("RGB"))
        img_h, img_w = img.shape[:2]

        import cv2
        contours = self._detect_pool_contours(img)
        features = []

        for cnt in contours:
            area = cv2.contourArea(cnt)
            peri = cv2.arcLength(cnt, True)
            confidence = min(0.90, round(area / (img_h * img_w * 0.05), 3))

            # Contorno real
            geo_poly = [
                PoolDetector._pixel_to_geo(pt[0][0], pt[0][1], img_w, img_h, bbox)
                for pt in cnt
            ]
            if len(geo_poly) < 3:
                continue
            geo_poly.append(geo_poly[0])

            # Bounding box
            x, y, w, h = cv2.boundingRect(cnt)
            bbox_geo = self._bbox_to_polygon(x, y, x + w, y + h, img_w, img_h, bbox)

            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [bbox_geo]},
                "properties": {
                    "detector": self.name,
                    "label": "bbox",
                    "model": "Segmentación por color (OpenCV)",
                    "confidence": confidence,
                },
            })
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [geo_poly]},
                "properties": {
                    "detector": self.name,
                    "label": "contour",
                    "model": "Segmentación por color (OpenCV)",
                    "confidence": confidence,
                },
            })

        logger.info(
            "OpenCV: detectadas %d piscinas en bbox %s", len(features) // 2, bbox,
        )
        return {"type": "FeatureCollection", "features": features}

    # ── Refinado de contornos con OpenCV (pipeline yourkln) ─────────

    _ENLARGEMENT_FACTOR = 0.3  # Ampliar bbox 30% como hace yourkln

    def _refine_box_contour(self, img: np.ndarray, box: Dict) -> List:
        """Refina una detección YOLO extrayendo el contorno real de la piscina.

        Pipeline (yourkln/pool-detection):
          1. Ampliar el bbox un 30% para capturar la piscina completa
          2. Aplicar ``_detect_pool_contours`` al ROI ampliado
          3. Devolver los puntos del contorno en coordenadas de imagen completa
        """
        img_h, img_w = img.shape[:2]
        x1, y1, x2, y2 = int(box["x1"]), int(box["y1"]), int(box["x2"]), int(box["y2"])

        # Ampliar bbox 30% (como yourkln)
        w, h = x2 - x1, y2 - y1
        dx = int(w * self._ENLARGEMENT_FACTOR)
        dy = int(h * self._ENLARGEMENT_FACTOR)
        x1e = max(0, x1 - dx)
        y1e = max(0, y1 - dy)
        x2e = min(img_w, x2 + dx)
        y2e = min(img_h, y2 + dy)

        roi = img[y1e:y2e, x1e:x2e]
        if roi.size == 0:
            return None

        contours = self._detect_pool_contours(roi)
        if not contours:
            return None

        # Devolver todos los contornos ajustados a coordenadas de imagen completa
        all_points = []
        for cnt in contours:
            pts = cnt.reshape(-1, 2)
            pts = pts + np.array([x1e, y1e])
            all_points.extend(pts.tolist())

        return all_points if all_points else None

    # ── Conversión a GeoJSON ────────────────────────────────────────

    def _boxes_to_geojson(
        self, boxes: List[Dict], img: np.ndarray, img_w: int, img_h: int,
        bbox: Dict, srs: str,
    ) -> Dict:
        features = []
        for box in boxes:
            x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
            conf = round(box["confidence"], 3)

            # 1. Feature Bounding Box (etiqueta "bbox")
            bbox_poly = self._bbox_to_polygon(x1, y1, x2, y2, img_w, img_h, bbox)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [bbox_poly]},
                "properties": {
                    "detector": self.name,
                    "label": "bbox",
                    "model": "YOLOv11n (ONNX)",
                    "confidence": conf,
                },
            })

            # 2. Feature Contorno real (etiqueta "contour")
            polygon_px = self._refine_box_contour(img, box)
            if polygon_px and len(polygon_px) >= 3:
                polygon_px.append(polygon_px[0])
                contour_poly = [
                    PoolDetector._pixel_to_geo(px, py, img_w, img_h, bbox)
                    for px, py in polygon_px
                ]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [contour_poly]},
                    "properties": {
                        "detector": self.name,
                        "label": "contour",
                        "model": "YOLOv11n (ONNX)",
                        "confidence": conf,
                    },
                })

        logger.info(
            "ONNX: %d detecciones en bbox %s", len(features), bbox,
        )
        return {"type": "FeatureCollection", "features": features}

    # ── Reproyección GeoJSON → EPSG:4326 ───────────────────────────

    @staticmethod
    def _reproject_geojson(geojson: Dict, from_srs: str) -> Dict:
        if from_srs.upper() not in ("EPSG:4326", "EPSG:4269", "WGS84"):
            features = geojson.get("features", [])
            for feat in features:
                geom = feat.get("geometry", {})
                PoolDetector._reproject_geometry(geom, from_srs)

        return geojson

    @staticmethod
    def _reproject_geometry(geom: Dict, from_srs: str):
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])

        if gtype == "Polygon":
            geom["coordinates"] = [
                [PoolDetector._to_wgs84(x, y, from_srs) for x, y in ring]
                for ring in coords
            ]
        elif gtype == "MultiPolygon":
            geom["coordinates"] = [
                [[PoolDetector._to_wgs84(x, y, from_srs) for x, y in ring] for ring in poly]
                for poly in coords
            ]
        elif gtype == "Point":
            if len(coords) >= 2:
                geom["coordinates"] = PoolDetector._to_wgs84(coords[0], coords[1], from_srs)
        elif gtype == "MultiPoint" or gtype == "LineString":
            geom["coordinates"] = [PoolDetector._to_wgs84(x, y, from_srs) for x, y in coords]
        elif gtype == "MultiLineString":
            geom["coordinates"] = [
                [PoolDetector._to_wgs84(x, y, from_srs) for x, y in segment]
                for segment in coords
            ]

    _transformer_cache: Dict[str, Any] = {}

    @classmethod
    def _get_transformer(cls, from_srs: str) -> Any:
        key = from_srs.upper()
        if key not in cls._transformer_cache:
            from pyproj import Transformer
            cls._transformer_cache[key] = Transformer.from_crs(from_srs, "EPSG:4326", always_xy=True)
        return cls._transformer_cache[key]

    @classmethod
    def _to_wgs84(cls, x: float, y: float, from_srs: str) -> list:
        if from_srs.upper() in ("EPSG:4326", "EPSG:4269", "WGS84"):
            return [x, y]
        tx = cls._get_transformer(from_srs)
        lon, lat = tx.transform(x, y)
        return [lon, lat]

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _pixel_to_geo(px: float, py: float, img_w: int, img_h: int,
                      bbox: Dict) -> list:
        x_geo = bbox["minX"] + (px / img_w) * (bbox["maxX"] - bbox["minX"])
        y_geo = bbox["maxY"] - (py / img_h) * (bbox["maxY"] - bbox["minY"])
        return [x_geo, y_geo]

    @staticmethod
    def _bbox_to_polygon(x1: float, y1: float, x2: float, y2: float,
                         img_w: int, img_h: int, bbox: Dict) -> List:
        return [
            PoolDetector._pixel_to_geo(x1, y1, img_w, img_h, bbox),
            PoolDetector._pixel_to_geo(x2, y1, img_w, img_h, bbox),
            PoolDetector._pixel_to_geo(x2, y2, img_w, img_h, bbox),
            PoolDetector._pixel_to_geo(x1, y2, img_w, img_h, bbox),
            PoolDetector._pixel_to_geo(x1, y1, img_w, img_h, bbox),
        ]
