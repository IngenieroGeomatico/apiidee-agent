"""
BaseDetector — Clase base abstracta para detectores de objetos sobre imágenes.

Cada detector encapsula un modelo ML y expone una interfaz común:
  - ``name``: identificador único (ej: ``pool_detector``)
  - ``label``: nombre legible para el usuario (ej: ``Piscinas``)
  - ``description``: texto que el LLM lee para decidir cuándo usarlo
  - ``detect(image, bbox, srs)``: ejecuta la inferencia y devuelve GeoJSON
"""
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class BaseDetector(ABC):
    """Clase base abstracta para detectores de objetos georreferenciados.

    Las subclases deben implementar ``detect()`` y definir las propiedades
    ``name``, ``label`` y ``description``.  El modelo se carga una sola vez
    en ``__init__`` y se reutiliza en cada llamada.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Identificador único del detector (ej: ``pool_detector``)."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Nombre legible para el usuario (ej: ``Piscinas``)."""

    @property
    @abstractmethod
    def description(self) -> str:
        """Descripción para el LLM de qué detecta este modelo."""

    @abstractmethod
    def detect(self, image: Any, bbox: Dict, srs: str = "EPSG:3857") -> Dict:
        """Ejecuta la detección sobre una imagen georreferenciada.

        Args:
            image: Imagen como numpy array (H, W, C) en formato RGB uint8,
                   o como ``PIL.Image.Image``.
            bbox: Extensión geográfica de la imagen::

                    {"minX": float, "minY": float,
                     "maxX": float, "maxY": float}

            srs: Sistema de referencia de ``bbox`` (por defecto EPSG:3857).

        Returns:
            GeoJSON FeatureCollection con las detecciones.  Cada Feature
            debe incluir al menos ``geometry`` y ``properties`` con
            ``detector``, ``confidence`` y ``label``.

        Ejemplo de retorno::

            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [...]},
                        "properties": {
                            "detector": "pool_detector",
                            "label": "Piscina",
                            "confidence": 0.92
                        }
                    }
                ]
            }
        """

    def get_info(self) -> Dict:
        """Devuelve un dict con la información del detector para el registry."""
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
        }
