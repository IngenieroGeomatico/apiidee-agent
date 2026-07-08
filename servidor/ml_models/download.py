"""
Descarga modelos ML necesarios si no existen en ml_models/.

Flujo para modelos que requieren conversión a ONNX:
  1. Descarga el fichero .pt (PyTorch / Ultralytics)
  2. Convierte a ONNX con ``ultralytics`` (pip install ultralytics)
  3. Borra el .pt intermedio

Se ejecuta automáticamente al arrancar Django (via apps.py) y también
se puede lanzar manualmente::

    python -m ml_models.download
"""
import logging
import subprocess
import sys
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).resolve().parent

# ── Registro de modelos ─────────────────────────────────────────────
#
# Cada entrada describe un modelo ONNX final que el detector espera.
#
#   onnx_file  : nombre del fichero ONNX resultante
#   pt_url     : URL directa al fichero .pt (PyTorch)
#   description: texto informativo para los logs
#   imgsz      : tamaño de imagen de entrada para la exportación ONNX

_MODELS = {
    "pool_detector.onnx": {
        "pt_url": (
            "https://raw.githubusercontent.com/yourkln/"
            "pool-detection/master/best.pt"
        ),
        "description": "YOLOv11n (~5 MB) fine-tuned para detección de piscinas",
        "imgsz": 640,
    },
}


# ── Helpers ──────────────────────────────────────────────────────────

def _download_file(url: str, dest: Path, desc: str = "") -> bool:
    """Descarga un fichero con barra de progreso."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Descargando %s (%s) desde %s ...", dest.name, desc, url)
    try:
        def _report(block, blocksize, totalsize):
            downloaded = block * blocksize / (1024 * 1024)
            total = totalsize / (1024 * 1024) if totalsize > 0 else 0
            if total:
                pct = min(100, downloaded / total * 100)
                print(f"  {downloaded:.1f}/{total:.1f} MB ({pct:.0f}%)", end="\r")
            else:
                print(f"  {downloaded:.1f} MB", end="\r")

        urllib.request.urlretrieve(url, dest, reporthook=_report)
        print()
        mb = dest.stat().st_size / (1024 * 1024)
        logger.info("Descargado %s (%.1f MB)", dest.name, mb)
        return True
    except Exception as exc:
        logger.error("Error descargando %s: %s", dest.name, exc)
        if dest.exists():
            dest.unlink()
        return False


def _ensure_ultralytics() -> bool:
    """Instala ``ultralytics`` si no está disponible (necesario para exportar a ONNX)."""
    try:
        import ultralytics  # noqa: F401
        return True
    except ImportError:
        pass
    logger.info("Instalando ultralytics (necesario para convertir .pt → ONNX)...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "ultralytics"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("ultralytics instalado correctamente")
        return True
    except Exception as exc:
        logger.error("No se pudo instalar ultralytics: %s", exc)
        return False


def _convert_pt_to_onnx(pt_path: Path, onnx_path: Path, imgsz: int = 640) -> bool:
    """Convierte un modelo .pt de Ultralytics a ONNX.

    Usa un subproceso para evitar contaminar el proceso principal con
    las dependencias pesadas de PyTorch/Ultralytics.
    """
    logger.info("Convirtiendo %s → %s (imgsz=%d)...", pt_path.name, onnx_path.name, imgsz)
    script = (
        f"from ultralytics import YOLO; "
        f"m = YOLO(r'{pt_path}'); "
        f"m.export(format='onnx', imgsz={imgsz}, simplify=True)"
    )
    try:
        subprocess.check_call(
            [sys.executable, "-c", script],
            cwd=str(pt_path.parent),
            timeout=300,
        )
    except Exception as exc:
        logger.error("Error convirtiendo a ONNX: %s", exc)
        return False

    # Ultralytics genera el ONNX junto al .pt con el mismo nombre base
    generated = pt_path.with_suffix(".onnx")
    if not generated.exists():
        logger.error("No se encontró el fichero ONNX generado: %s", generated)
        return False

    if generated != onnx_path:
        generated.rename(onnx_path)

    mb = onnx_path.stat().st_size / (1024 * 1024)
    logger.info("ONNX generado: %s (%.1f MB)", onnx_path.name, mb)
    return True


# ── API pública ──────────────────────────────────────────────────────

def download_and_convert(onnx_filename: str, info: dict) -> bool:
    """Descarga un .pt, lo convierte a ONNX y limpia el .pt intermedio."""
    onnx_path = _MODEL_DIR / onnx_filename
    pt_path = _MODEL_DIR / onnx_path.stem.replace(".", "_temp_") + ".pt"

    # 1. Descargar .pt
    if not _download_file(info["pt_url"], pt_path, info["description"]):
        return False

    # 2. Asegurar que ultralytics está disponible
    if not _ensure_ultralytics():
        pt_path.unlink(missing_ok=True)
        return False

    # 3. Convertir a ONNX
    success = _convert_pt_to_onnx(pt_path, onnx_path, imgsz=info.get("imgsz", 640))

    # 4. Limpiar .pt intermedio
    pt_path.unlink(missing_ok=True)

    return success


def ensure_models():
    """Descarga y convierte modelos faltantes.  Se llama al arrancar Django."""
    missing = [f for f in _MODELS if not (_MODEL_DIR / f).exists()]
    if not missing:
        return

    logger.info("Modelos ML faltantes: %s. Descargando y convirtiendo...", missing)
    converted = []
    for filename in missing:
        if download_and_convert(filename, _MODELS[filename]):
            converted.append(filename)

    if converted:
        logger.info("Modelos listos: %s", converted)
    else:
        logger.warning(
            "No se pudo preparar ningún modelo. "
            "Los detectores funcionarán en modo reducido (OpenCV)."
        )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ensure_models()
