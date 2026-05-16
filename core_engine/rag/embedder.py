"""
Architect-JS RAG Pipeline — Embedding Module
Uses sentence-transformers with ONNX backend OR ChromaDB's built-in embedding function.
All-local, zero-API-cost embeddings.

Falls back gracefully if torch/CUDA is unavailable on Windows.
"""
from __future__ import annotations

import os
import warnings
from typing import List, Optional

from ..logger import get_logger

logger = get_logger("rag.embedder")

# Suppress torch DLL warnings on Windows
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
warnings.filterwarnings("ignore", category=UserWarning, module="transformers")
warnings.filterwarnings("ignore", category=FutureWarning)

_model = None
_model_name: Optional[str] = None
_using_chroma_ef = False


def _try_sentence_transformers(model_name: str):
    """
    Try to load a SentenceTransformer model.
    Returns the model or raises RuntimeError.
    """
    try:
        from sentence_transformers import SentenceTransformer
        # Try ONNX backend first (no torch needed, uses onnxruntime)
        try:
            m = SentenceTransformer(model_name, backend="onnx")
            logger.info(f"Loaded embedding model via ONNX backend: {model_name}")
            return m
        except Exception as onnx_err:
            logger.debug(f"ONNX backend failed ({onnx_err}), trying default backend")

        # Try standard backend
        m = SentenceTransformer(model_name)
        logger.info(f"Loaded embedding model: {model_name}")
        return m
    except (OSError, ImportError, Exception) as e:
        raise RuntimeError(str(e)) from e


def _try_chroma_ef():
    """
    Use ChromaDB's built-in DefaultEmbeddingFunction as ultimate fallback.
    This uses onnxruntime directly without torch.
    """
    try:
        from chromadb.utils import embedding_functions
        ef = embedding_functions.DefaultEmbeddingFunction()
        logger.info("Using ChromaDB DefaultEmbeddingFunction (onnxruntime-based)")
        return ef
    except Exception as e:
        raise RuntimeError(f"ChromaDB embedding function failed: {e}") from e


def get_embedding_model(model_name: Optional[str] = None):
    """Lazy-load the embedding model (singleton)."""
    global _model, _model_name, _using_chroma_ef

    if model_name is None:
        from ..config import get_config
        model_name = get_config().rag.embedding_model

    if _model is not None and _model_name == model_name:
        return _model

    logger.info(f"Loading embedding model: {model_name}")

    # Strategy 1: sentence-transformers (best quality)
    try:
        _model = _try_sentence_transformers(model_name)
        _model_name = model_name
        _using_chroma_ef = False
        return _model
    except RuntimeError as st_err:
        logger.warning(
            f"sentence-transformers failed to load model '{model_name}': {st_err}\n"
            "Falling back to ChromaDB DefaultEmbeddingFunction (onnxruntime)..."
        )

    # Strategy 2: ChromaDB's DefaultEmbeddingFunction (onnxruntime, no torch needed)
    try:
        _model = _try_chroma_ef()
        _model_name = "chroma-default"
        _using_chroma_ef = True
        return _model
    except RuntimeError as chroma_err:
        raise RuntimeError(
            f"All embedding backends failed.\n\n"
            f"Primary (sentence-transformers) error: {st_err}\n"
            f"Fallback (chromadb) error: {chroma_err}\n\n"
            "Solutions:\n"
            "1. Install Visual C++ Redistributable:\n"
            "   https://aka.ms/vs/17/release/vc_redist.x64.exe\n"
            "2. Or reinstall torch for CPU:\n"
            "   pip install torch --index-url https://download.pytorch.org/whl/cpu"
        ) from chroma_err


def embed_texts(texts: List[str], model_name: Optional[str] = None) -> List[List[float]]:
    """
    Embed a list of text strings.
    Returns a list of embedding vectors (list of floats).
    """
    if not texts:
        return []

    model = get_embedding_model(model_name)

    if _using_chroma_ef:
        # ChromaDB EF returns a list of lists directly
        embeddings = model(texts)
        return [list(e) for e in embeddings]

    # SentenceTransformer
    embeddings = model.encode(
        texts,
        batch_size=32,
        show_progress_bar=False,
        normalize_embeddings=True,  # L2-normalize for cosine similarity
    )
    return embeddings.tolist()


def embed_query(query: str, model_name: Optional[str] = None) -> List[float]:
    """Embed a single query string."""
    results = embed_texts([query], model_name)
    return results[0] if results else []
