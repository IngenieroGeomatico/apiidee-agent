"""
Módulo ML — Integración de modelos de machine learning locales.

Permite registrar detectores de objetos (piscinas, edificios, etc.) que se
ejecutan sobre imágenes georreferenciadas obtenidas via WMS y devuelven
GeoJSON con las detecciones.

Para añadir un nuevo detector: crear una clase en ``detectors/`` que extienda
``BaseDetector`` y decorarla con ``@detector``.
"""
