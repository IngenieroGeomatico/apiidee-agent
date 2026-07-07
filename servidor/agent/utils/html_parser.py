"""HTML text extractor — extrae texto plano y enlaces ignorando etiquetas de navegacion/estilo."""

from html.parser import HTMLParser


class TextExtractor(HTMLParser):
    """Extrae texto plano y enlaces de HTML, ignorando script/style/nav/footer/header.

    Usa un contador de profundidad en vez de un booleano para que los tags
    anidados (p.ej. ``<nav><footer>...</footer></nav>``) se manejen correctamente.
    """

    _SKIP_TAGS = {'script', 'style', 'nav', 'footer', 'header'}

    _HEADING_TAGS = {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}

    _BLOCK_TAGS = {'p', 'div', 'li', 'br', 'tr', 'td', 'th', 'section'}

    def __init__(self):
        super().__init__()
        self.text_parts: list[str] = []
        self.links: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        if tag == 'a':
            for attr_name, attr_val in attrs:
                if attr_name == 'href' and attr_val:
                    self.links.append(attr_val)
        if tag in self._HEADING_TAGS:
            level = int(tag[1])
            self.text_parts.append('\n' + '#' * level + ' ')
        if tag in self._BLOCK_TAGS:
            self.text_parts.append('\n')

    def handle_endtag(self, tag: str):
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str):
        if self._skip_depth == 0:
            self.text_parts.append(data)
