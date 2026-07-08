"""Tests unitarios para los ejecutores de herramientas del servidor (tools/executors.py).

Cubre fetchWebPage, geocodePlace y searchIdeeService con todas las
llamadas HTTP mockeadas (sin red real).
"""
import json
from unittest.mock import MagicMock, patch

from django.test import TestCase


class FetchWebPageTest(TestCase):
    """Verifica fetchWebPage con respuestas HTML y no-HTML mockeadas."""

    @patch("agent.tools.executors.urlopen")
    def test_html_devuelve_texto_extraido(self, mock_urlopen):
        """fetchWebPage con contenido HTML devuelve texto extraído (sin tags)."""
        from agent.tools.executors import fetch_web_page

        html_content = b"<html><body><h1>Titulo</h1><p>Contenido de prueba</p></body></html>"
        mock_resp = MagicMock()
        mock_resp.read.return_value = html_content
        mock_resp.headers = {"Content-Type": "text/html; charset=utf-8"}
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = fetch_web_page(url="http://example.com")

        self.assertIn("Titulo", result)
        self.assertIn("Contenido de prueba", result)
        self.assertNotIn("<h1>", result)
        self.assertNotIn("<p>", result)

    @patch("agent.tools.executors.urlopen")
    def test_no_html_devuelve_texto_crudo(self, mock_urlopen):
        """fetchWebPage con contenido no-HTML devuelve texto crudo."""
        from agent.tools.executors import fetch_web_page

        raw_content = b"Linea 1\nLinea 2\nLinea 3"
        mock_resp = MagicMock()
        mock_resp.read.return_value = raw_content
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        result = fetch_web_page(url="http://example.com/data.json")

        self.assertIn("Linea 1", result)
        self.assertIn("Linea 2", result)


class GeocodePlaceTest(TestCase):
    """Verifica geocodePlace con distintos modos de entrada."""

    def test_con_id_y_type_devuelve_geojson_url(self):
        """geocodePlace con id+type devuelve dict con geojsonURL y name."""
        from agent.tools.executors import geocode_place

        result = geocode_place(q="Calle Mayor", id="280790001", type="portal")

        self.assertIn("geojsonURL", result)
        self.assertIn("name", result)
        self.assertEqual(result["name"], "Calle Mayor")
        self.assertIn("id=280790001", result["geojsonURL"])
        self.assertIn("type=portal", result["geojsonURL"])
        self.assertIn("outputformat=geoJson", result["geojsonURL"])

    @patch("agent.tools.executors._fetch_candidates")
    def test_con_q_y_candidatos_devuelve_lista(self, mock_candidates):
        """geocodePlace con q y candidatos encontrados devuelve dict con candidates."""
        from agent.tools.executors import geocode_place

        mock_candidates.return_value = [
            {"address": "Madrid, Madrid", "type": "Municipio",
             "muni": "Madrid", "id": "28079", "lat": "40.4168", "lng": "-3.7038"},
            {"address": "Madrid, Bogotá", "type": "Municipio",
             "muni": "Bogotá", "id": "99001", "lat": "0", "lng": "0"},
        ]

        result = geocode_place(q="Madrid")

        self.assertIn("candidates", result)
        self.assertIn("query", result)
        self.assertIn("instructions", result)
        self.assertEqual(result["query"], "Madrid")
        self.assertEqual(len(result["candidates"]), 2)
        # Primer candidato tiene coordenadas
        self.assertEqual(result["candidates"][0]["address"], "Madrid, Madrid")
        self.assertIn("geojsonURL", result["candidates"][0])
        self.assertIn("lat", result["candidates"][0])
        # Segundo candidato con lat/lng 0 no incluye coordenadas
        self.assertNotIn("lat", result["candidates"][1])

    @patch("agent.tools.executors._fetch_candidates")
    def test_con_q_sin_candidatos_devuelve_fallback(self, mock_candidates):
        """geocodePlace con q sin candidatos devuelve fallback con geojsonURL."""
        from agent.tools.executors import geocode_place

        mock_candidates.return_value = None

        result = geocode_place(q="Lugar inexistente XYZ")

        self.assertIn("geojsonURL", result)
        self.assertIn("name", result)
        self.assertIn("message", result)
        self.assertEqual(result["name"], "Lugar inexistente XYZ")
        self.assertIn("No candidates found", result["message"])


class SearchIdeeServiceTest(TestCase):
    """Verifica searchIdeeService con respuestas mockeadas del directorio IDEE."""

    @patch("agent.tools.executors._fetch_idee_category")
    def test_resultados_encontrados_devuelve_resumen(self, mock_fetch):
        """searchIdeeService con resultados devuelve texto con resumen formateado."""
        from agent.tools.executors import search_idee_service

        mock_fetch.return_value = [
            {"name": "WMS Catastro", "url": "http://ovc.catastro.meh.es/wms",
             "type": "WMS", "category": "WMS", "organization": "Catastro"},
        ]

        # Patcheamos ThreadPoolExecutor para ejecutar de forma síncrona
        with patch("agent.tools.executors.ThreadPoolExecutor") as MockPool:
            mock_executor = MagicMock()
            MockPool.return_value.__enter__ = MagicMock(return_value=mock_executor)
            MockPool.return_value.__exit__ = MagicMock(return_value=False)

            # Simular future completado
            mock_future = MagicMock()
            mock_future.result.return_value = [
                {"name": "WMS Catastro", "url": "http://ovc.catastro.meh.es/wms",
                 "type": "WMS", "category": "WMS", "organization": "Catastro"},
            ]
            mock_executor.submit.return_value = mock_future

            from concurrent.futures import as_completed
            with patch("agent.tools.executors.as_completed", return_value=[mock_future]):
                result = search_idee_service(query="catastro")

        self.assertIn("WMS Catastro", result)
        self.assertIn("catastro", result)
        self.assertIn("addLayer", result)

    def test_query_vacio_devuelve_error(self):
        """searchIdeeService con query vacío devuelve JSON con error."""
        from agent.tools.executors import search_idee_service

        result = search_idee_service(query="")
        parsed = json.loads(result)
        self.assertIn("error", parsed)

    def test_query_espacios_devuelve_error(self):
        """searchIdeeService con query de solo espacios devuelve JSON con error."""
        from agent.tools.executors import search_idee_service

        result = search_idee_service(query="   ")
        parsed = json.loads(result)
        self.assertIn("error", parsed)

    @patch("agent.tools.executors.as_completed")
    @patch("agent.tools.executors.ThreadPoolExecutor")
    def test_sin_resultados_devuelve_error(self, MockPool, mock_as_completed):
        """searchIdeeService sin resultados devuelve JSON con error y URL de ayuda."""
        from agent.tools.executors import search_idee_service

        mock_executor = MagicMock()
        MockPool.return_value.__enter__ = MagicMock(return_value=mock_executor)
        MockPool.return_value.__exit__ = MagicMock(return_value=False)

        mock_future = MagicMock()
        mock_future.result.return_value = []
        mock_executor.submit.return_value = mock_future
        mock_as_completed.return_value = [mock_future]

        result = search_idee_service(query="servicio_inexistente_xyz")
        parsed = json.loads(result)
        self.assertIn("error", parsed)
        self.assertIn("servicio_inexistente_xyz", parsed["error"])
