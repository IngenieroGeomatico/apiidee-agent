"""Tests unitarios para el recuperador RAG (rag/retriever.py).

Cubre retrieve_context con y sin vectorstore, clear_faiss_cache
y el caché de _get_faiss_store.
"""
import threading
from unittest.mock import MagicMock, patch, PropertyMock

from django.test import TestCase

import agent.rag.retriever as retriever_module


class RetrieveContextSinVectorstoreTest(TestCase):
    """Verifica retrieve_context cuando no existe el directorio de vectorstore."""

    def setUp(self):
        """Limpia el caché de FAISS antes de cada test."""
        retriever_module._faiss_store_cache.clear()

    def tearDown(self):
        """Limpia el caché de FAISS después de cada test."""
        retriever_module._faiss_store_cache.clear()

    @patch("agent.rag.retriever.settings")
    def test_sin_directorio_devuelve_lista_vacia(self, mock_settings):
        """retrieve_context devuelve [] si VECTORSTORE_DIR no existe."""
        mock_path = MagicMock()
        mock_path.exists.return_value = False
        mock_settings.VECTORSTORE_DIR = mock_path

        from agent.rag.retriever import retrieve_context
        result = retrieve_context("consulta de prueba")

        self.assertEqual(result, [])


class RetrieveContextConFaissStoreTest(TestCase):
    """Verifica retrieve_context con un FAISS store mockeado."""

    def setUp(self):
        retriever_module._faiss_store_cache.clear()

    def tearDown(self):
        retriever_module._faiss_store_cache.clear()

    @patch("agent.rag.retriever._get_faiss_store")
    @patch("agent.rag.retriever.Path")
    @patch("agent.rag.retriever.settings")
    def test_con_store_devuelve_resultados_ordenados(self, mock_settings, MockPath, mock_get_store):
        """retrieve_context con FAISS store devuelve resultados ordenados por relevancia."""
        # Simular directorio de vectorstore con un subdirectorio que contiene index.faiss
        mock_vectorstore_dir = MagicMock()
        mock_vectorstore_dir.exists.return_value = True

        mock_repo_dir = MagicMock()
        mock_repo_dir.is_dir.return_value = True
        mock_index_path = MagicMock()
        mock_index_path.exists.return_value = True
        mock_repo_dir.__truediv__ = MagicMock(return_value=mock_index_path)

        mock_vectorstore_dir.iterdir.return_value = [mock_repo_dir]
        MockPath.return_value = mock_vectorstore_dir

        # Simular documentos con scores (menor = más relevante)
        doc_close = MagicMock()
        doc_close.page_content = "Documento cercano"
        doc_close.metadata = {"source": "close.py"}

        doc_far = MagicMock()
        doc_far.page_content = "Documento lejano"
        doc_far.metadata = {"source": "far.py"}

        mock_store = MagicMock()
        mock_store.similarity_search_with_score.return_value = [
            (doc_far, 0.9),    # Menos relevante
            (doc_close, 0.1),  # Más relevante
        ]
        mock_get_store.return_value = mock_store

        from agent.rag.retriever import retrieve_context
        result = retrieve_context("búsqueda", k=5)

        self.assertEqual(len(result), 2)
        # El más relevante (score más bajo) debe estar primero
        self.assertEqual(result[0]["content"], "Documento cercano")
        self.assertEqual(result[0]["metadata"]["source"], "close.py")
        self.assertEqual(result[1]["content"], "Documento lejano")


class ClearFaissCacheTest(TestCase):
    """Verifica clear_faiss_cache()."""

    def setUp(self):
        retriever_module._faiss_store_cache.clear()

    def tearDown(self):
        retriever_module._faiss_store_cache.clear()

    def test_clear_faiss_cache_limpia_diccionario(self):
        """clear_faiss_cache() vacía el diccionario de caché."""
        retriever_module._faiss_store_cache["fake_path"] = MagicMock()
        self.assertEqual(len(retriever_module._faiss_store_cache), 1)

        from agent.rag.retriever import clear_faiss_cache
        clear_faiss_cache()

        self.assertEqual(len(retriever_module._faiss_store_cache), 0)


class GetFaissStoreCacheTest(TestCase):
    """Verifica que _get_faiss_store() cachea y reutiliza instancias."""

    def setUp(self):
        retriever_module._faiss_store_cache.clear()

    def tearDown(self):
        retriever_module._faiss_store_cache.clear()

    @patch("agent.rag.retriever._load_faiss_store")
    def test_cachea_y_reutiliza_instancia(self, mock_load):
        """_get_faiss_store() carga una vez y devuelve la misma instancia en la segunda llamada."""
        fake_store = MagicMock(name="fake_faiss_store")
        mock_load.return_value = fake_store

        from agent.rag.retriever import _get_faiss_store

        store1 = _get_faiss_store("/fake/path/repo1")
        store2 = _get_faiss_store("/fake/path/repo1")

        self.assertIs(store1, store2)
        # Solo se carga una vez desde disco
        mock_load.assert_called_once()
