"""
Registry de detectores ML — Auto-descubre y gestiona detectores registrados.

Uso:

    from agent.ml.registry import detector, get_detector, list_detectors

    @detector
    class MiDetector(BaseDetector):
        ...

    # Obtener un detector por nombre
    det = get_detector("mi_detector")

    # Listar todos los disponibles
    todos = list_detectors()
"""
import logging
from typing import Dict, List, Optional

from .base import BaseDetector

logger = logging.getLogger(__name__)

_detector_registry: Dict[str, BaseDetector] = {}
_discovered = False


def detector(cls):
    """Decorador de clase para registrar un detector automáticamente.

    Instancia la clase y la registra en el registry global.
    Si la instanciación falla (ej: modelo no encontrado), registra un
    warning pero no interrumpe el arranque del servidor.

    Uso::

        @detector
        class PoolDetector(BaseDetector):
            name = "pool_detector"
            ...
    """
    try:
        instance = cls()
        _detector_registry[instance.name] = instance
        logger.info("Detector registrado: %s (%s)", instance.name, instance.label)
    except Exception as exc:
        logger.warning(
            "No se pudo registrar el detector %s: %s. "
            "Probablemente faltan los pesos del modelo.",
            cls.__name__, exc,
        )
    return cls


def _discover_detectors():
    """Importa todos los módulos en ``detectors/`` para activar los decoradores ``@detector``.

    Se ejecuta una sola vez (lazy) la primera vez que se consulta el registry.
    """
    global _discovered
    if _discovered:
        return
    _discovered = True

    import importlib
    import pkgutil
    from pathlib import Path

    detectors_pkg = Path(__file__).resolve().parent / "detectors"
    if not detectors_pkg.is_dir():
        return

    package_name = "agent.ml.detectors"
    for _, module_name, _ in pkgutil.iter_modules([str(detectors_pkg)]):
        try:
            importlib.import_module(f"{package_name}.{module_name}")
        except Exception as exc:
            logger.warning("Error importando detector %s: %s", module_name, exc)


def get_detector(name: str) -> Optional[BaseDetector]:
    """Devuelve un detector por su nombre, o None si no existe."""
    _discover_detectors()
    return _detector_registry.get(name)


def list_detectors() -> List[Dict]:
    """Devuelve la información de todos los detectores registrados."""
    _discover_detectors()
    return [det.get_info() for det in _detector_registry.values()]


def get_detector_names() -> List[str]:
    """Devuelve los nombres de todos los detectores registrados."""
    _discover_detectors()
    return list(_detector_registry.keys())
