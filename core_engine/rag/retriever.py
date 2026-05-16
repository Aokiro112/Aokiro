"""
Architect-JS RAG Pipeline — Retriever
Semantic retrieval with source referencing and context injection.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from ..config import get_config
from ..logger import get_logger
from .embedder import embed_query
from .store import VectorStore

logger = get_logger("rag.retriever")


@dataclass
class RetrievedChunk:
    """A retrieved chunk with its similarity score and source reference."""
    content: str
    source: str
    start_line: int
    end_line: int
    language: str
    chunk_index: int
    similarity: float
    distance: float

    @property
    def source_ref(self) -> str:
        """Human-readable source reference: path:L10-L25"""
        try:
            from pathlib import Path
            import os
            rel = os.path.relpath(self.source)
        except Exception:
            rel = self.source
        return f"{rel}:L{self.start_line}-L{self.end_line}"


class Retriever:
    """
    Semantic retriever: embed query → search ChromaDB → return ranked chunks.
    """

    def __init__(self, store: Optional[VectorStore] = None, top_k: Optional[int] = None):
        cfg = get_config()
        self.store = store or VectorStore()
        self.top_k = top_k or cfg.rag.top_k

    def retrieve(
        self,
        query: str,
        n_results: Optional[int] = None,
        language_filter: Optional[str] = None,
    ) -> List[RetrievedChunk]:
        """
        Retrieve the most semantically similar chunks for a query.

        Args:
            query: Natural language or code query.
            n_results: Override default top_k.
            language_filter: Filter by language ("typescript", "javascript", etc.)

        Returns:
            List of RetrievedChunk, ordered by similarity (highest first).
        """
        n = n_results or self.top_k

        if self.store.count() == 0:
            logger.warning("Vector store is empty. Run indexing first.")
            return []

        # Build where clause for language filtering
        where = None
        if language_filter:
            where = {"language": language_filter}

        query_embedding = embed_query(query)
        results = self.store.query(query_embedding, n_results=n, where=where)

        chunks = []
        for r in results:
            meta = r.get("metadata", {})
            chunks.append(RetrievedChunk(
                content=r.get("content", ""),
                source=meta.get("source", "unknown"),
                start_line=meta.get("start_line", 0),
                end_line=meta.get("end_line", 0),
                language=meta.get("language", "text"),
                chunk_index=meta.get("chunk_index", 0),
                similarity=r.get("similarity", 0.0),
                distance=r.get("distance", 1.0),
            ))

        logger.debug(f"Retrieved {len(chunks)} chunks for query: {query[:60]}...")
        return chunks

    def format_context(self, chunks: List[RetrievedChunk], max_chars: int = 4000) -> str:
        """
        Format retrieved chunks into a context string for LLM injection.
        Includes source references and language markers.
        """
        if not chunks:
            return "No relevant context found in the indexed codebase."

        parts = []
        total_chars = 0

        for i, chunk in enumerate(chunks, 1):
            header = f"[Source {i}: {chunk.source_ref}] ({chunk.language}, similarity: {chunk.similarity:.2f})"
            lang_tag = chunk.language if chunk.language in ("typescript", "javascript", "python") else "text"
            block = f"{header}\n```{lang_tag}\n{chunk.content}\n```"

            if total_chars + len(block) > max_chars:
                # Add truncation notice and stop
                parts.append(f"... (additional {len(chunks) - i + 1} chunks truncated to fit context window)")
                break

            parts.append(block)
            total_chars += len(block)

        return "\n\n".join(parts)

    def retrieve_and_format(self, query: str, n_results: Optional[int] = None) -> tuple[List[RetrievedChunk], str]:
        """
        Retrieve chunks and format them in one call.
        Returns (chunks, formatted_context_string).
        """
        chunks = self.retrieve(query, n_results)
        context = self.format_context(chunks)
        return chunks, context
