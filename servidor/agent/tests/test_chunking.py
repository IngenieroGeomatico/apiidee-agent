"""Tests unitarios para el módulo de chunking RAG."""

from django.test import TestCase

from agent.rag.chunking import (
    chunk_file,
    chunk_code_file,
    chunk_markdown_file,
    _chunk_by_lines,
    _finalize_chunks,
)


class ChunkFileDispatchTest(TestCase):
    """Verifica que chunk_file() despacha a la estrategia correcta según extensión."""

    def test_extension_py_usa_code(self):
        """Fichero .py debe usar chunking por código."""
        content = "def foo():\n    pass\n\ndef bar():\n    pass\n"
        result = chunk_file(content, "app/main.py")
        # Debe producir chunks con language='py'
        self.assertTrue(all(
            c["metadata"]["language"] == "py" for c in result
        ))

    def test_extension_js_usa_code(self):
        """Fichero .js debe usar chunking por código."""
        content = "function foo() {}\nfunction bar() {}\n"
        result = chunk_file(content, "src/index.js")
        self.assertTrue(all(
            c["metadata"]["language"] == "js" for c in result
        ))

    def test_extension_md_usa_markdown(self):
        """Fichero .md debe usar chunking por markdown."""
        content = "# Título\nTexto\n## Subtítulo\nMás texto\n"
        result = chunk_file(content, "docs/readme.md")
        self.assertTrue(all(
            c["metadata"]["language"] == "markdown" for c in result
        ))

    def test_extension_txt_usa_markdown(self):
        """Fichero .txt está en _MARKDOWN_EXTENSIONS, usa chunking markdown."""
        content = "# Nota\nContenido de texto plano.\n"
        result = chunk_file(content, "notas.txt")
        self.assertTrue(all(
            c["metadata"]["language"] == "markdown" for c in result
        ))

    def test_extension_csv_usa_lines(self):
        """Fichero .csv no es ni code ni markdown, usa chunking por líneas."""
        content = "a,b,c\n1,2,3\n4,5,6\n"
        result = chunk_file(content, "data.csv")
        # Debe producir chunks con language='csv'
        self.assertTrue(all(
            c["metadata"]["language"] == "csv" for c in result
        ))

    def test_extension_desconocida_usa_lines(self):
        """Extensión no reconocida debe caer al fallback de líneas."""
        content = "línea uno\nlínea dos\n"
        result = chunk_file(content, "archivo.xyz")
        self.assertTrue(all(
            c["metadata"]["language"] == "xyz" for c in result
        ))

    def test_sin_extension_language_text(self):
        """Fichero sin extensión debe tener language='text'."""
        content = "contenido sin extensión\n"
        result = chunk_file(content, "Makefile")
        self.assertTrue(all(
            c["metadata"]["language"] == "text" for c in result
        ))


class ChunkCodeFileTest(TestCase):
    """Verifica el chunking por fronteras de función/clase en código."""

    def test_split_funciones_python(self):
        """Debe separar funciones Python en chunks distintos con max_chunk_size bajo."""
        body = "    x = 1\n" * 20  # cuerpo largo para superar max_chunk_size
        content = (
            f"import os\n\n"
            f"def foo():\n{body}\n"
            f"def bar():\n{body}\n"
        )
        result = chunk_code_file(content, "mod.py", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 2)

    def test_split_funciones_js(self):
        """Debe separar funciones JavaScript en chunks distintos con max_chunk_size bajo."""
        body = "  console.log('x');\n" * 20
        content = (
            f"const config = {{}};\n\n"
            f"function init() {{\n{body}}}\n\n"
            f"function run() {{\n{body}}}\n"
        )
        result = chunk_code_file(content, "app.js", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 2)

    def test_split_clase_python(self):
        """Debe detectar fronteras de clase Python con max_chunk_size bajo."""
        body = "    x = 1\n" * 20
        content = (
            f"class Foo:\n{body}\n"
            f"class Bar:\n{body}\n"
        )
        result = chunk_code_file(content, "models.py", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 2)

    def test_sin_fronteras_usa_lines(self):
        """Código sin funciones/clases debe caer al fallback de líneas."""
        content = "x = 1\ny = 2\nz = 3\n"
        result = chunk_code_file(content, "script.py")
        # Debe producir al menos un chunk
        self.assertGreaterEqual(len(result), 1)

    def test_metadata_correcta(self):
        """Cada chunk debe tener source, chunk_index y language."""
        content = "def a():\n    pass\n\ndef b():\n    pass\n"
        result = chunk_code_file(content, "utils.py")
        for i, chunk in enumerate(result):
            self.assertIn("content", chunk)
            meta = chunk["metadata"]
            self.assertEqual(meta["source"], "utils.py")
            self.assertEqual(meta["chunk_index"], i)
            self.assertEqual(meta["language"], "py")

    def test_async_function_js(self):
        """Debe detectar async function como frontera con max_chunk_size bajo."""
        body = "  console.log('x');\n" * 20
        content = (
            f"async function fetchData() {{\n{body}}}\n\n"
            f"async function postData() {{\n{body}}}\n"
        )
        result = chunk_code_file(content, "api.js", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 2)

    def test_export_function_js(self):
        """Debe detectar export function como frontera con max_chunk_size bajo."""
        body = "  console.log('x');\n" * 20
        content = (
            f"export function helper() {{\n{body}}}\n\n"
            f"export function main() {{\n{body}}}\n"
        )
        result = chunk_code_file(content, "lib.ts", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 2)

    def test_async_def_python(self):
        """Debe detectar async def como frontera en Python con max_chunk_size bajo."""
        body = "    x = 1\n" * 20
        content = (
            f"async def fetch():\n{body}\n"
            f"async def process():\n{body}\n"
        )
        result = chunk_code_file(content, "async_mod.py", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 2)


class ChunkMarkdownFileTest(TestCase):
    """Verifica el chunking por encabezados en Markdown."""

    def test_split_por_h1(self):
        """Debe separar secciones por encabezados H1 con max_chunk_size bajo."""
        body = "Texto de relleno. " * 20
        content = f"# Intro\n{body}\n# Desarrollo\n{body}\n"
        result = chunk_markdown_file(content, "doc.md", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 2)

    def test_split_por_h2(self):
        """Debe separar secciones por encabezados H2 con max_chunk_size bajo."""
        body = "Contenido extenso. " * 20
        content = f"## Sección A\n{body}\n## Sección B\n{body}\n"
        result = chunk_markdown_file(content, "doc.md", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 2)

    def test_split_por_h3_a_h6(self):
        """Debe detectar encabezados de nivel 3 a 6 con max_chunk_size bajo."""
        body = "Texto de relleno. " * 20
        content = (
            f"### Nivel 3\n{body}\n"
            f"#### Nivel 4\n{body}\n"
            f"##### Nivel 5\n{body}\n"
            f"###### Nivel 6\n{body}\n"
        )
        result = chunk_markdown_file(content, "deep.md", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 4)

    def test_preambulo_antes_de_heading(self):
        """Texto antes del primer heading debe incluirse como chunk."""
        preamble = "Texto previo al heading. " * 20
        body = "Contenido extenso. " * 20
        content = f"{preamble}\n# Título\n{body}\n"
        result = chunk_markdown_file(content, "doc.md", max_chunk_size=100)
        self.assertGreaterEqual(len(result), 2)
        # El preámbulo debe estar en alguno de los primeros chunks
        texto_total = " ".join(c["content"] for c in result)
        self.assertIn("Texto previo", texto_total)

    def test_sin_headings_usa_lines(self):
        """Markdown sin headings debe caer al fallback de líneas."""
        content = "Solo texto plano\nsin encabezados\n"
        result = chunk_markdown_file(content, "plain.md")
        self.assertGreaterEqual(len(result), 1)

    def test_language_es_markdown(self):
        """Todos los chunks de markdown deben tener language='markdown'."""
        content = "# A\nTexto A.\n# B\nTexto B.\n"
        result = chunk_markdown_file(content, "doc.md")
        for chunk in result:
            self.assertEqual(chunk["metadata"]["language"], "markdown")

    def test_heading_con_contenido_extenso(self):
        """Sección con contenido largo no debe perder texto."""
        body = "Párrafo largo. " * 50
        content = f"# Título\n{body}\n"
        result = chunk_markdown_file(content, "largo.md")
        texto_total = "".join(c["content"] for c in result)
        self.assertIn("Párrafo largo.", texto_total)


class ChunkByLinesTest(TestCase):
    """Verifica el chunking por líneas con tamaño máximo."""

    def test_contenido_pequeno_un_chunk(self):
        """Contenido que cabe en max_chunk_size produce un solo chunk."""
        content = "línea 1\nlínea 2\nlínea 3"
        result = _chunk_by_lines(content, "file.txt", max_chunk_size=500)
        self.assertEqual(len(result), 1)

    def test_contenido_grande_multiples_chunks(self):
        """Contenido que excede max_chunk_size se divide en varios chunks."""
        lines = [f"línea {i}" for i in range(100)]
        content = "\n".join(lines)
        result = _chunk_by_lines(content, "big.txt", max_chunk_size=50)
        self.assertGreater(len(result), 1)

    def test_cada_chunk_no_excede_max(self):
        """Ningún chunk debe exceder max_chunk_size (aprox)."""
        lines = [f"dato-{i}" for i in range(200)]
        content = "\n".join(lines)
        max_size = 80
        result = _chunk_by_lines(content, "data.log", max_chunk_size=max_size)
        for chunk in result:
            # Puede exceder ligeramente por la última línea añadida,
            # pero cada chunk se construye respetando el límite
            self.assertLessEqual(
                len(chunk["content"]), max_size + 50,
                f"Chunk demasiado grande: {len(chunk['content'])} chars"
            )

    def test_chunks_vacios_se_filtran(self):
        """Líneas vacías no deben generar chunks con contenido vacío."""
        content = "\n\n\n\ncontenido real\n\n\n\n"
        result = _chunk_by_lines(content, "sparse.txt", max_chunk_size=500)
        for chunk in result:
            self.assertTrue(
                chunk["content"].strip(),
                "Se encontró un chunk vacío"
            )

    def test_metadata_source_y_language(self):
        """Cada chunk debe tener source del fichero y language de la extensión."""
        content = "datos\nmás datos"
        result = _chunk_by_lines(content, "info.log", max_chunk_size=500)
        self.assertEqual(len(result), 1)
        meta = result[0]["metadata"]
        self.assertEqual(meta["source"], "info.log")
        self.assertEqual(meta["language"], "log")

    def test_sin_extension_language_text(self):
        """Fichero sin extensión debe tener language='text'."""
        content = "contenido"
        result = _chunk_by_lines(content, "README", max_chunk_size=500)
        self.assertEqual(result[0]["metadata"]["language"], "text")

    def test_chunk_index_secuencial(self):
        """Los chunk_index deben ser secuenciales empezando en 0."""
        lines = [f"línea-{i}" for i in range(50)]
        content = "\n".join(lines)
        result = _chunk_by_lines(content, "seq.txt", max_chunk_size=30)
        indices = [c["metadata"]["chunk_index"] for c in result]
        self.assertEqual(indices, list(range(len(result))))


class FinalizeChunksTest(TestCase):
    """Verifica el merge de chunks pequeños y split de chunks oversized."""

    def test_merge_chunks_pequenos(self):
        """Chunks pequeños deben fusionarse si caben juntos."""
        raw = ["a", "b", "c"]
        result = _finalize_chunks(raw, "f.py", "py", max_chunk_size=100)
        # Los tres caben en 100 chars, deben fusionarse en uno
        self.assertEqual(len(result), 1)
        self.assertIn("a", result[0]["content"])
        self.assertIn("b", result[0]["content"])
        self.assertIn("c", result[0]["content"])

    def test_split_chunk_oversized(self):
        """Un chunk que excede max_chunk_size debe dividirse."""
        # Crear un chunk de ~200 chars
        big_chunk = "\n".join([f"línea {i}" for i in range(30)])
        raw = [big_chunk]
        result = _finalize_chunks(raw, "f.py", "py", max_chunk_size=50)
        self.assertGreater(len(result), 1)

    def test_no_merge_si_excede(self):
        """Dos chunks que juntos exceden max_chunk_size no se fusionan."""
        raw = ["a" * 40, "b" * 40]
        result = _finalize_chunks(raw, "f.py", "py", max_chunk_size=50)
        self.assertEqual(len(result), 2)

    def test_metadata_con_language_correcto(self):
        """Cada chunk resultante debe tener el language indicado."""
        raw = ["contenido"]
        result = _finalize_chunks(raw, "mod.rs", "rs", max_chunk_size=500)
        self.assertEqual(result[0]["metadata"]["language"], "rs")

    def test_metadata_source_correcto(self):
        """Cada chunk resultante debe tener el source indicado."""
        raw = ["contenido"]
        result = _finalize_chunks(raw, "path/to/file.go", "go", max_chunk_size=500)
        self.assertEqual(result[0]["metadata"]["source"], "path/to/file.go")

    def test_chunk_index_secuencial(self):
        """Los chunk_index deben ser secuenciales tras merge/split."""
        raw = ["x" * 30, "y" * 30, "z" * 30]
        result = _finalize_chunks(raw, "f.py", "py", max_chunk_size=40)
        indices = [c["metadata"]["chunk_index"] for c in result]
        self.assertEqual(indices, list(range(len(result))))

    def test_chunks_vacios_se_filtran(self):
        """Chunks que quedan vacíos tras strip deben eliminarse."""
        raw = ["contenido real", "   ", "\n\n", "otro contenido"]
        result = _finalize_chunks(raw, "f.py", "py", max_chunk_size=500)
        for chunk in result:
            self.assertTrue(
                chunk["content"].strip(),
                "Se encontró un chunk vacío tras finalizar"
            )

    def test_lista_vacia_devuelve_vacia(self):
        """Lista vacía de entrada debe producir lista vacía."""
        result = _finalize_chunks([], "f.py", "py", max_chunk_size=500)
        self.assertEqual(result, [])

    def test_mix_merge_y_split(self):
        """Mezcla de chunks pequeños y grandes se procesa correctamente."""
        small = "abc"
        big = "\n".join([f"línea-{i}" for i in range(30)])
        raw = [small, big, small]
        result = _finalize_chunks(raw, "f.py", "py", max_chunk_size=50)
        # Debe haber más de 1 chunk por el grande
        self.assertGreater(len(result), 1)
        # Todo el contenido debe estar presente
        texto_total = "\n".join(c["content"] for c in result)
        self.assertIn("abc", texto_total)
        self.assertIn("línea-0", texto_total)
