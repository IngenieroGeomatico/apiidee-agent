import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from agent.ml.base import BaseDetector
from agent.ml.registry import detector

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).resolve().parent.parent.parent.parent / "ml_models"
_MODEL_PATH = _MODEL_DIR / "pool_seg.onnx"

_CONFIDENCE_THRESHOLD = 0.25
_IOU_THRESHOLD = 0.45
_INPUT_SIZE = 640
_NM = 32

_transformer_cache: Dict[str, Any] = {}


@detector
class PoolSegDetector(BaseDetector):

    @property
    def name(self) -> str:
        return "pool_seg_detector"

    @property
    def label(self) -> str:
        return "Piscinas (segmentación)"

    @property
    def description(self) -> str:
        return (
            "Detecta piscinas en imágenes aéreas con segmentación de instancias. "
            "Usa un modelo YOLO11n-seg fine-tuned para siluetas precisas de piscinas. "
            "Devuelve contornos exactos además de las cajas delimitadoras."
        )

    def __init__(self):
        self.model = self._load_seg_model()
        if self.model is None:
            logger.warning("pool_seg.onnx no disponible, usando fallback PoolDetector")
            self._fallback = self._create_fallback()
        else:
            self._fallback = None

    def _load_seg_model(self):
        if not _MODEL_PATH.exists():
            return None
        import onnxruntime as ort
        session = ort.InferenceSession(
            str(_MODEL_PATH),
            providers=["CPUExecutionProvider"],
        )
        logger.info("Modelo pool_seg.onnx cargado desde %s", _MODEL_PATH)
        return session

    def _create_fallback(self):
        from agent.ml.detectors.pool_detector import PoolDetector
        return PoolDetector()

    def detect(self, image: Any, bbox: Dict, srs: str = "EPSG:3857") -> Dict:
        if self.model is None and self._fallback is not None:
            logger.info("Usando PoolDetector como fallback")
            return self._fallback.detect(image, bbox, srs)

        img_array = np.array(image.convert("RGB"))
        orig_h, orig_w = img_array.shape[:2]

        input_tensor, scale, pad = self._preprocess(img_array)
        outputs = self.model.run(None, {self.model.get_inputs()[0].name: input_tensor})
        boxes = self._postprocess_seg(outputs, orig_w, orig_h, scale, pad)

        if not boxes:
            logger.info("pool_seg sin detecciones, fallback PoolDetector")
            if self._fallback is not None:
                return self._fallback.detect(image, bbox, srs)
            return {"type": "FeatureCollection", "features": []}

        geojson = self._boxes_to_geojson(boxes, img_array, orig_w, orig_h, bbox, srs)
        return self._reproject_geojson(geojson, srs)

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

    def _postprocess_seg(
        self, outputs: List[np.ndarray],
        orig_w: int, orig_h: int,
        scale: float, pad: Tuple[int, int],
    ) -> List[Dict]:
        output0 = outputs[0][0]
        protos = outputs[1][0]

        nc = output0.shape[0] - 4 - _NM
        dets = output0.T

        candidates = []
        for det in dets:
            scores = det[4:4 + nc]
            max_score = float(scores.max())
            if max_score < _CONFIDENCE_THRESHOLD:
                continue

            class_id = int(scores.argmax())
            cx, cy, w, h_box = float(det[0]), float(det[1]), float(det[2]), float(det[3])

            x1 = (cx - w / 2 - pad[0]) / scale
            y1 = (cy - h_box / 2 - pad[1]) / scale
            x2 = (cx + w / 2 - pad[0]) / scale
            y2 = (cy + h_box / 2 - pad[1]) / scale
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(orig_w, x2)
            y2 = min(orig_h, y2)

            if x2 - x1 < 2 or y2 - y1 < 2:
                continue

            mask_coeffs = det[4 + nc:4 + nc + _NM]

            candidates.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "confidence": max_score,
                "class_id": class_id,
                "mask_coeffs": mask_coeffs,
            })

        keep = self._nms(candidates)

        for box in keep:
            polygon = self._decode_mask_to_polygon(box, protos, orig_w, orig_h, scale, pad)
            box["mask_poly"] = polygon

        return keep

    def _decode_mask_to_polygon(
        self, box: Dict, protos: np.ndarray,
        orig_w: int, orig_h: int,
        scale: float, pad: Tuple[int, int],
    ) -> Optional[List]:
        import cv2
        mask_coeffs = box["mask_coeffs"]

        protos_flat = protos.reshape(_NM, -1)
        mask_160 = np.dot(mask_coeffs, protos_flat)
        mask_160 = 1.0 / (1.0 + np.exp(-mask_160))
        mask_160 = mask_160.reshape(160, 160)

        mask_640 = cv2.resize(mask_160, (640, 640), interpolation=cv2.INTER_LINEAR)

        px, py = pad
        nw = int(orig_w * scale)
        nh = int(orig_h * scale)
        mask_cropped = mask_640[py:py + nh, px:px + nw]

        mask_full = cv2.resize(mask_cropped, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
        mask_bin = (mask_full > 0.5).astype(np.uint8) * 255

        margin = 20
        x1 = max(0, int(box["x1"]) - margin)
        y1 = max(0, int(box["y1"]) - margin)
        x2 = min(orig_w, int(box["x2"]) + margin)
        y2 = min(orig_h, int(box["y2"]) + margin)

        crop = mask_bin[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        contours, _ = cv2.findContours(crop, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        best = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(best, True)
        if peri == 0:
            return None
        epsilon = 0.025 * peri
        approx = cv2.approxPolyDP(best, epsilon, True)

        offset = np.array([x1, y1])
        return (approx.reshape(-1, 2) + offset).tolist()

    @staticmethod
    def _nms(boxes: List[Dict]) -> List[Dict]:
        if not boxes:
            return []
        boxes.sort(key=lambda b: b["confidence"], reverse=True)
        keep = []
        while boxes:
            best = boxes.pop(0)
            keep.append(best)
            boxes = [b for b in boxes if PoolSegDetector._iou(b, best) < _IOU_THRESHOLD]
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

    def _boxes_to_geojson(
        self, boxes: List[Dict], img: np.ndarray, img_w: int, img_h: int,
        bbox: Dict, srs: str,
    ) -> Dict:
        features = []
        for box in boxes:
            x1, y1, x2, y2 = box["x1"], box["y1"], box["x2"], box["y2"]
            conf = round(box["confidence"], 3)

            bbox_poly = self._bbox_to_polygon(x1, y1, x2, y2, img_w, img_h, bbox)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [bbox_poly]},
                "properties": {
                    "detector": self.name,
                    "label": "bbox",
                    "model": "YOLO11n-seg (ONNX)",
                    "confidence": conf,
                },
            })

            polygon_px = box.get("mask_poly")
            if polygon_px and len(polygon_px) >= 3:
                polygon_px.append(polygon_px[0])
                contour_poly = [
                    PoolSegDetector._pixel_to_geo(px, py, img_w, img_h, bbox)
                    for px, py in polygon_px
                ]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "Polygon", "coordinates": [contour_poly]},
                    "properties": {
                        "detector": self.name,
                        "label": "contour",
                        "model": "YOLO11n-seg (ONNX)",
                        "confidence": conf,
                    },
                })

        logger.info(
            "PoolSegDetector: %d features en bbox %s", len(features), bbox,
        )
        return {"type": "FeatureCollection", "features": features}

    @staticmethod
    def _reproject_geojson(geojson: Dict, from_srs: str) -> Dict:
        if from_srs.upper() not in ("EPSG:4326", "EPSG:4269", "WGS84"):
            for feat in geojson.get("features", []):
                geom = feat.get("geometry", {})
                PoolSegDetector._reproject_geometry(geom, from_srs)
        return geojson

    @staticmethod
    def _reproject_geometry(geom: Dict, from_srs: str):
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])
        if gtype == "Polygon":
            geom["coordinates"] = [
                [PoolSegDetector._to_wgs84(x, y, from_srs) for x, y in ring]
                for ring in coords
            ]
        elif gtype == "MultiPolygon":
            geom["coordinates"] = [
                [[PoolSegDetector._to_wgs84(x, y, from_srs) for x, y in ring] for ring in poly]
                for poly in coords
            ]
        elif gtype == "Point":
            if len(coords) >= 2:
                geom["coordinates"] = PoolSegDetector._to_wgs84(coords[0], coords[1], from_srs)
        elif gtype in ("MultiPoint", "LineString"):
            geom["coordinates"] = [PoolSegDetector._to_wgs84(x, y, from_srs) for x, y in coords]
        elif gtype == "MultiLineString":
            geom["coordinates"] = [
                [PoolSegDetector._to_wgs84(x, y, from_srs) for x, y in segment]
                for segment in coords
            ]

    @classmethod
    def _get_transformer(cls, from_srs: str):
        key = from_srs.upper()
        if key not in _transformer_cache:
            from pyproj import Transformer
            _transformer_cache[key] = Transformer.from_crs(from_srs, "EPSG:4326", always_xy=True)
        return _transformer_cache[key]

    @classmethod
    def _to_wgs84(cls, x: float, y: float, from_srs: str) -> list:
        if from_srs.upper() in ("EPSG:4326", "EPSG:4269", "WGS84"):
            return [x, y]
        tx = cls._get_transformer(from_srs)
        lon, lat = tx.transform(x, y)
        return [lon, lat]

    @staticmethod
    def _pixel_to_geo(px: float, py: float, img_w: int, img_h: int, bbox: Dict) -> list:
        x_geo = bbox["minX"] + (px / img_w) * (bbox["maxX"] - bbox["minX"])
        y_geo = bbox["maxY"] - (py / img_h) * (bbox["maxY"] - bbox["minY"])
        return [x_geo, y_geo]

    @staticmethod
    def _bbox_to_polygon(x1: float, y1: float, x2: float, y2: float,
                         img_w: int, img_h: int, bbox: Dict) -> List:
        return [
            PoolSegDetector._pixel_to_geo(x1, y1, img_w, img_h, bbox),
            PoolSegDetector._pixel_to_geo(x2, y1, img_w, img_h, bbox),
            PoolSegDetector._pixel_to_geo(x2, y2, img_w, img_h, bbox),
            PoolSegDetector._pixel_to_geo(x1, y2, img_w, img_h, bbox),
            PoolSegDetector._pixel_to_geo(x1, y1, img_w, img_h, bbox),
        ]
