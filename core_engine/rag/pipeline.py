"""
Architect-JS RAG Pipeline — Full Pipeline Orchestration
Coordinates: ingest → chunk → embed → store → retrieve → inject
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_config
from ..logger import get_logger
from .embedder import embed_texts
from .ingestion import Chunk, DocumentIngester
from .retriever import Retriever, RetrievedChunk
from .store import VectorStore

logger = get_logger("rag.pipeline")


@dataclass
class IndexingResult:
    """Summary of an indexing operation."""
    docs_processed: int
    chunks_generated: int
    chunks_added: int
    duration_seconds: float
    collection: str


class RagPipeline:
    """
    End-to-end RAG pipeline for Architect-JS.

    Usage:
        pipeline = RagPipeline()
        result = pipeline.index("./src")
        chunks, context = pipeline.retrieve("useEffect cleanup bug")
    """

    def __init__(
        self,
        collection_name: Optional[str] = None,
        db_path: Optional[str] = None,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        top_k: Optional[int] = None,
    ):
        cfg = get_config()
        self.store = VectorStore(
            collection_name=collection_name,
            db_path=db_path,
        )
        self.ingester = DocumentIngester(
            chunk_size=chunk_size or cfg.rag.chunk_size,
            chunk_overlap=chunk_overlap or cfg.rag.chunk_overlap,
        )
        self.retriever = Retriever(store=self.store, top_k=top_k or cfg.rag.top_k)

    def index(
        self,
        target: str | Path,
        progress_callback=None,
    ) -> IndexingResult:
        """
        Full indexing pipeline for a file or directory.
        1. Scan target for supported files
        2. Chunk documents
        3. Embed chunks in batches
        4. Add to ChromaDB

        Args:
            target: File path or directory to index.
            progress_callback: Optional callable(current, total, message) for progress updates.

        Returns:
            IndexingResult with counts and timing.
        """
        start = time.time()
        target = Path(target)

        # Step 1: Ingest (scan + chunk)
        if progress_callback:
            progress_callback(0, 100, f"Scanning {target}...")

        docs = self.ingester.scan_path(target)
        docs_count = len(docs)

        if progress_callback:
            progress_callback(10, 100, f"Loaded {docs_count} documents, chunking...")

        all_chunks: List[Chunk] = []
        for doc in docs:
            chunks = self.ingester.chunk_document(doc)
            all_chunks.extend(chunks)

        chunks_count = len(all_chunks)
        if progress_callback:
            progress_callback(30, 100, f"Generated {chunks_count} chunks, embedding...")

        if not all_chunks:
            logger.warning(f"No chunks generated from {target}")
            return IndexingResult(
                docs_processed=docs_count,
                chunks_generated=0,
                chunks_added=0,
                duration_seconds=time.time() - start,
                collection=self.store.collection_name,
            )

        # Step 2: Embed in batches
        batch_size = 64
        all_embeddings: List[List[float]] = []

        for batch_start in range(0, len(all_chunks), batch_size):
            batch = all_chunks[batch_start:batch_start + batch_size]
            texts = [c.content for c in batch]

            if progress_callback:
                pct = 30 + int((batch_start / len(all_chunks)) * 50)
                progress_callback(pct, 100, f"Embedding batch {batch_start + len(batch)}/{chunks_count}...")

            embeddings = embed_texts(texts)
            all_embeddings.extend(embeddings)

        if progress_callback:
            progress_callback(80, 100, "Adding to vector store...")

        # Step 3: Add to store
        added = self.store.add_chunks(all_chunks, all_embeddings)

        if progress_callback:
            progress_callback(100, 100, "Done!")

        duration = time.time() - start
        logger.info(f"Indexed {target}: {docs_count} docs, {chunks_count} chunks, {added} new in {duration:.1f}s")

        return IndexingResult(
            docs_processed=docs_count,
            chunks_generated=chunks_count,
            chunks_added=added,
            duration_seconds=duration,
            collection=self.store.collection_name,
        )

    def retrieve(self, query: str, n_results: Optional[int] = None) -> Tuple[List[RetrievedChunk], str]:
        """
        Retrieve relevant chunks and format them for LLM injection.
        Returns (chunks, formatted_context).
        """
        return self.retriever.retrieve_and_format(query, n_results)

    def get_status(self) -> Dict[str, Any]:
        """Return current pipeline status."""
        info = self.store.get_collection_info()
        return {
            "status": "ready" if info.get("total_chunks", 0) > 0 else "empty",
            **info,
        }

    def reset_index(self) -> None:
        """Clear the entire vector store collection."""
        self.store.reset()
        logger.warning("RAG index has been reset")
