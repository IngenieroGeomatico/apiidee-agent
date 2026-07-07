"""Tests unitarios para el módulo de indexación (indexer.py).

Cubre el parser HTML (TextExtractor), la función _extract_html y
el registro de indexers (get_indexer).
"""
from django.test import TestCase

from agent.utils.html_parser import TextExtractor
from agent.rag.indexer import _extract_html, get_indexer
from agent.rag.indexer import GitRepoIndexer, WebIndexer


class TextExtractorSimpleTagsTest(TestCase):
    """Verifica que TextExtractor extrae texto de tags simples (p, div, h1-h6)."""

    def test_extrae_texto_de_p_div_y_headings(self):
        """Párrafos, divs y headings deben producir texto con saltos de línea."""
        html = "<p>Hola</p><div>Mundo</div><h1>Título</h1><h3>Subtítulo</h3>"
        extractor = TextExtractor()
        extractor.feed(html)
        text = "".join(extractor.text_parts)

        self.assertIn("Hola", text)
        self.assertIn("Mundo", text)
        self.assertIn("# Título", text)
        self.assertIn("### Subtítulo", text)


class TextExtractorSkipTagsTest(TestCase):
    """Verifica que script, style, nav, footer y header no producen texto."""

    def test_skip_tags_no_producen_texto(self):
        """El contenido dentro de tags ignorados no debe aparecer en la salida."""
        html = (
            "<script>var x = 1;</script>"
            "<style>.cls {}</style>"
            "<nav>navegación</nav>"
            "<footer>pie</footer>"
            "<header>cabecera</header>"
            "<p>visible</p>"
        )
        extractor = TextExtractor()
        extractor.feed(html)
        text = "".join(extractor.text_parts)

        self.assertNotIn("var x", text)
        self.assertNotIn(".cls", text)
        self.assertNotIn("navegación", text)
        self.assertNotIn("pie", text)
        self.assertNotIn("cabecera", text)
        self.assertIn("visible", text)


class TextExtractorSkipDepthTest(TestCase):
    """Verifica el manejo de _skip_depth con tags anidados."""

    def test_skip_depth_tags_anidados(self):
        """Tags skip anidados deben ocultarse; el texto fuera debe ser visible."""
        html = "<nav><footer>hidden</footer></nav>visible"
        extractor = TextExtractor()
        extractor.feed(html)
        text = "".join(extractor.text_parts)

        self.assertNotIn("hidden", text)
        self.assertIn("visible", text)

    def test_skip_depth_doble_apertura(self):
        """Doble apertura de skip tags incrementa profundidad correctamente."""
        html = "<nav><nav>oculto</nav>aún oculto</nav>fuera"
        extractor = TextExtractor()
        extractor.feed(html)
        text = "".join(extractor.text_parts)

        self.assertNotIn("oculto", text)
        self.assertNotIn("aún oculto", text)
        self.assertIn("fuera", text)


class TextExtractorLinksTest(TestCase):
    """Verifica que TextExtractor extrae enlaces de tags <a href>."""

    def test_extrae_links(self):
        """Los href de tags <a> deben registrarse en la lista de links."""
        html = '<a href="https://example.com">Enlace</a><a href="/ruta">Otro</a>'
        extractor = TextExtractor()
        extractor.feed(html)

        self.assertEqual(len(extractor.links), 2)
        self.assertEqual(extractor.links[0], "https://example.com")
        self.assertEqual(extractor.links[1], "/ruta")


class ParseHtmlTest(TestCase):
    """Verifica que _extract_html devuelve una tupla (texto, links)."""

    def test_devuelve_tupla_texto_y_links(self):
        """_extract_html debe devolver (str, list) con el texto y los enlaces."""
        html = '<p>Texto</p><a href="http://x.com">link</a>'
        text, links = _extract_html(html)

        self.assertIsInstance(text, str)
        self.assertIsInstance(links, list)
        self.assertIn("Texto", text)
        self.assertIn("link", text)
        self.assertEqual(links, ["http://x.com"])


class GetIndexerTest(TestCase):
    """Verifica el registro de indexers (get_indexer)."""

    def test_get_indexer_git(self):
        """get_indexer('git') debe devolver una instancia de GitRepoIndexer."""
        indexer = get_indexer("git")
        self.assertIsInstance(indexer, GitRepoIndexer)

    def test_get_indexer_web(self):
        """get_indexer('web') debe devolver una instancia de WebIndexer."""
        indexer = get_indexer("web")
        self.assertIsInstance(indexer, WebIndexer)

    def test_get_indexer_invalid_lanza_valueerror(self):
        """get_indexer con tipo desconocido debe lanzar ValueError."""
        with self.assertRaises(ValueError) as ctx:
            get_indexer("invalid")
        self.assertIn("invalid", str(ctx.exception))
