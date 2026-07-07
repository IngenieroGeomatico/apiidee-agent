"""
Descarga modelos ML necesarios si no existen en ml_models/.
Se ejecuta automáticamente al arrancar Django.
"""
import logging
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_DIR = Path(__file__).resolve().parent

_MODELS = {
    "pool_detector.onnx": {
        "url": "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8n.onnx",
        "description": "YOLOv8n (~6 MB) para detección de piscinas",
        "size_mb": 6.2,
    },
}


def download(url: str, dest: Path, desc: str = "") -> bool:
    import sys
    dest.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Descargando %s (%s) desde %s ...", dest.name, desc, url)
    try:
        def report(block, blocksize, totalsize):
            downloaded = block * blocksize / (1024 * 1024)
            total = totalsize / (1024 * 1024) if totalsize > 0 else 0
            if total:
                pct = min(100, downloaded / total * 100)
                print(f"  {downloaded:.1f}/{total:.1f} MB ({pct:.0f}%)", end="\r")
            else:
                print(f"  {downloaded:.1f} MB", end="\r")

        urllib.request.urlretrieve(url, dest, reporthook=report)
        print()
        mb = dest.stat().st_size / (1024 * 1024)
        logger.info("Descargado %s (%.1f MB)", dest.name, mb)
        return True
    except Exception as exc:
        logger.error("Error descargando %s: %s", dest.name, exc)
        if dest.exists():
            dest.unlink()
        return False


def download_missing():
    downloaded = []
    for filename, info in _MODELS.items():
        dest = _MODEL_DIR / filename
        if dest.exists():
            continue
        if download(info["url"], dest, info["description"]):
            downloaded.append(filename)
    return downloaded


def ensure_models():
    missing = [f for f in _MODELS if not (_MODEL_DIR / f).exists()]
    if not missing:
        return
    logger.info("Modelos ML faltantes: %s. Descargando...", missing)
    downloaded = download_missing()
    if downloaded:
        logger.info("Modelos descargados: %s", downloaded)
    else:
        logger.warning("No se pudo descargar ningún modelo. Los detectores funcionarán en modo reducido.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    ensure_models()
