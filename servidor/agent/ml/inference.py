"""
Pipeline de inferencia — Descarga imagen WMS y ejecuta un detector.

Este módulo conecta el sistema de tools del agente con los detectores ML:
  1. Recibe un bbox y un nombre de detector
  2. Descarga la imagen de la zona via WMS (ortofoto PNOA por defecto)
  3. Ejecuta el detector sobre la imagen
  4. Devuelve GeoJSON con las detecciones

Uso desde un tool executor::

    from agent.ml.inference import run_detection
    result = run_detection("pool_detector", bbox, srs="EPSG:3857")
"""
import io
import json
import logging
from typing import Dict, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

# WMS por defecto: ortofoto PNOA (toda España, alta resolución)
_DEFAULT_WMS_URL = "https://www.ign.es/wms-inspire/pnoa-ma"
_DEFAULT_WMS_LAYER = "OI.OrthoimageCoverage"

# Tamaño de imagen a solicitar al WMS (píxeles)
_DEFAULT_IMAGE_WIDTH = 2048
_DEFAULT_IMAGE_HEIGHT = 2048


def fetch_wms_image(
    bbox: Dict,
    srs: str = "EPSG:3857",
    wms_url: str = _DEFAULT_WMS_URL,
    layer: str = _DEFAULT_WMS_LAYER,
    width: int = _DEFAULT_IMAGE_WIDTH,
    height: int = _DEFAULT_IMAGE_HEIGHT,
):
    """Descarga una imagen de un servicio WMS para la zona indicada.

    Args:
        bbox: Extensión geográfica ``{minX, minY, maxX, maxY}``.
        srs: Sistema de referencia del bbox.
        wms_url: URL base del servicio WMS.
        layer: Nombre de la capa WMS.
        width: Ancho de la imagen solicitada en píxeles.
        height: Alto de la imagen solicitada en píxeles.

    Returns:
        ``PIL.Image.Image`` en modo RGB.

    Raises:
        ImportError: Si Pillow no está instalado.
        Exception: Si la descarga WMS falla.
    """
    from PIL import Image

    bbox_str = f"{bbox['minX']},{bbox['minY']},{bbox['maxX']},{bbox['maxY']}"
    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "BBOX": bbox_str,
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "SRS": srs,
        "FORMAT": "image/png",
        "STYLES": "",
    }
    url = f"{wms_url}?{urlencode(params)}"
    logger.warning("WMS REQUEST: bbox=%s srs=%s size=%sx%s url=%s", bbox_str, srs, width, height, url)

    req = Request(url, headers={"User-Agent": "APIIDEEAgent/1.0"})
    with urlopen(req, timeout=30) as resp:
        content_type = resp.headers.get("Content-Type", "")
        data = resp.read()

    # El WMS puede devolver XML de error en vez de imagen
    if "image" not in content_type:
        body_preview = data[:500].decode("utf-8", errors="ignore")
        logger.error(
            "WMS no devolvió imagen (Content-Type: %s). Respuesta: %s",
            content_type, body_preview,
        )
        raise RuntimeError(
            f"El servicio WMS devolvió {content_type} en vez de imagen. "
            f"Puede que el bbox o el SRS no sean válidos."
        )

    image = Image.open(io.BytesIO(data)).convert("RGB")
    logger.info("Imagen descargada: %dx%d px", image.width, image.height)
    return image


def run_detection(
    detector_name: str,
    bbox: Dict,
    srs: str = "EPSG:3857",
    wms_url: Optional[str] = None,
    wms_layer: Optional[str] = None,
    image_width: int = _DEFAULT_IMAGE_WIDTH,
    image_height: int = _DEFAULT_IMAGE_HEIGHT,
) -> str:
    """Ejecuta un detector ML sobre la zona indicada y devuelve GeoJSON.

    Pipeline completo:
      1. Busca el detector en el registry
      2. Descarga la imagen de la zona via WMS
      3. Ejecuta el detector
      4. Devuelve el GeoJSON como string

    Args:
        detector_name: Nombre del detector registrado (ej: ``pool_detector``).
        bbox: Extensión geográfica ``{minX, minY, maxX, maxY}``.
        srs: Sistema de referencia del bbox.
        wms_url: URL del WMS (por defecto PNOA).
        wms_layer: Capa del WMS (por defecto ortofoto PNOA).
        image_width: Ancho de la imagen en píxeles.
        image_height: Alto de la imagen en píxeles.

    Returns:
        String con el GeoJSON FeatureCollection de las detecciones, o
        un JSON de error si algo falla.
    """
    from .registry import get_detector, list_detectors

    logger.info("run_detection: detector=%s, bbox=%s, srs=%s, wms=%s, size=%dx%d",
                detector_name, bbox, srs, wms_url or "PNOA", image_width, image_height)

    # 1. Buscar detector
    det = get_detector(detector_name)
    if det is None:
        available = [d["name"] for d in list_detectors()]
        return json.dumps({
            "error": f"Detector '{detector_name}' no encontrado.",
            "disponibles": available,
        }, ensure_ascii=False)

    # 2. Descargar imagen
    try:
        image = fetch_wms_image(
            bbox=bbox,
            srs=srs,
            wms_url=wms_url or _DEFAULT_WMS_URL,
            layer=wms_layer or _DEFAULT_WMS_LAYER,
            width=image_width,
            height=image_height,
        )
    except ImportError:
        return json.dumps({
            "error": "Pillow no está instalado. Ejecuta: pip install Pillow",
        }, ensure_ascii=False)
    except Exception as exc:
        logger.exception("Error descargando imagen WMS")
        return json.dumps({
            "error": f"Error descargando imagen WMS: {exc}",
        }, ensure_ascii=False)

    # 3. Ejecutar detector
    try:
        geojson = det.detect(image=image, bbox=bbox, srs=srs)
        n_features = len(geojson.get("features", []))
        logger.info(
            "Detector '%s' encontró %d objetos en bbox %s",
            detector_name, n_features, bbox,
        )
    except Exception as exc:
        logger.exception("Error en detector '%s'", detector_name)
        return json.dumps({
            "error": f"Error ejecutando detector '{detector_name}': {exc}",
        }, ensure_ascii=False)

    # 4. Devolver GeoJSON
    return json.dumps(geojson, ensure_ascii=False)
