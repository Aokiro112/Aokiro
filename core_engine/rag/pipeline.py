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
from .web_retriever import WebRetriever

logger = get_logger("rag.pipeline")

# ─────────────────────────────────────────────────────────────────────────────
# Intent Detection — decides if a query is technical enough to warrant RAG
# ─────────────────────────────────────────────────────────────────────────────

_TECH_KEYWORDS = {
    # React & React Native
    "react", "component", "hook", "usestate", "useeffect", "usememo", "usecallback",
    "useref", "usecontext", "usereducer", "props", "jsx", "tsx", "redux", "zustand",
    "context", "provider", "memo", "forwardref", "suspense", "lazy",
    "react native", "expo", "navigation", "stylesheet", "flatlist", "scrollview",
    "reanimated", "gesture", "nativewind", "metro", "eas",
    # Node.js & JS/TS ecosystem
    "node", "nodejs", "express", "fastify", "nestjs", "koa", "hapi",
    "javascript", "typescript", "js", "ts", "ecmascript", "es6", "commonjs", "esm",
    "module", "import", "export", "async", "await", "promise", "callback",
    "npm", "yarn", "pnpm", "package", "dependency", "bundler", "webpack", "vite", "esbuild",
    # APIs & data
    "api", "rest", "graphql", "fetch", "axios", "http", "websocket", "socket",
    "database", "prisma", "mongoose", "sequelize", "sql", "mongodb", "postgres",
    "redis", "cache", "auth", "jwt", "oauth", "middleware",
    # General coding
    "function", "class", "interface", "type", "generic", "enum", "decorator",
    "error", "bug", "fix", "debug", "performance", "optimize", "refactor",
    "test", "jest", "vitest", "cypress", "mock", "lint", "eslint", "prettier",
    "deploy", "build", "ci", "docker", "env", "config", "setup",
    "how", "why", "what is", "difference", "best practice", "example", "tutorial",
    "code", "implement", "create", "write", "generate",
}

_CASUAL_PATTERNS = {
    "hello", "hi", "hey", "hii", "hiii", "heyyy", "sup", "yo",
    "thanks", "thank you", "thx", "ty",
    "ok", "okay", "cool", "nice", "great", "awesome",
    "bye", "goodbye", "see you", "later",
    "yes", "no", "yep", "nope", "sure",
    "lol", "haha", "xd",
}


def is_technical_query(query: str) -> bool:
    """
    Returns True if the query looks like a technical/coding question
    that would benefit from RAG or web search context.

    Heuristics (in order):
      1. Very short queries (<=3 words, no tech keywords) → casual → False
      2. Matches a known casual pattern → False
      3. Contains a recognised tech keyword → True
      4. Query is long enough (>8 words) → likely substantive → True
      5. Default → False (don't waste time searching)
    """
    q = query.strip().lower()
    words = q.split()

    # Rule 1 + 2: short or casual
    if q in _CASUAL_PATTERNS or (len(words) <= 2 and not any(kw in q for kw in _TECH_KEYWORDS)):
        return False

    # Rule 3: tech keyword present
    if any(kw in q for kw in _TECH_KEYWORDS):
        return True

    # Rule 4: long query is likely substantive
    if len(words) > 8:
        return True

    return False


@dataclass
class IndexingResult:
    """Summary of an indexing operation."""
    docs_processed: int
    chunks_generated: int
    chunks_added: int
    duration_seconds: float
    collection: str


@dataclass
class RetrievalResult:
    """Output of a hybrid retrieval call."""
    chunks: list
    context: str
    source_type: str  # 'codebase', 'web', or 'hybrid'


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
        self.cfg = cfg
        self.store = VectorStore(
            collection_name=collection_name,
            db_path=db_path,
        )
        self.ingester = DocumentIngester(
            chunk_size=chunk_size or cfg.rag.chunk_size,
            chunk_overlap=chunk_overlap or cfg.rag.chunk_overlap,
        )
        self.retriever = Retriever(store=self.store, top_k=top_k or cfg.rag.top_k)
        self.web_retriever = WebRetriever()

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

    def retrieve(
        self,
        query: str,
        n_results: Optional[int] = None,
        force_web: bool = False,
    ) -> Tuple[List[RetrievedChunk], str]:
        """
        Hybrid retrieval: local vector store first, web search fallback.

        Falls back to web search when:
          - The local index is empty, OR
          - The best local similarity score is below `web_search.fallback_threshold`, OR
          - force_web=True is passed.

        Returns (chunks, formatted_context).
        """
        threshold = self.cfg.web_search.fallback_threshold
        web_enabled = self.cfg.web_search.enabled

        # --- Intent check: skip RAG entirely for casual/non-technical queries ---
        if not force_web and not is_technical_query(query):
            logger.debug(f"Query classified as non-technical, skipping RAG: {query!r}")
            self._last_source_type = "none"
            return [], ""

        # --- Local retrieval ---
        local_chunks: List[RetrievedChunk] = []
        if self.store.count() > 0 and not force_web:
            local_chunks, _ = self.retriever.retrieve_and_format(query, n_results)
            
            # Phase 4: Dependency-aware Retrieval
            if local_chunks:
                logger.info("Enhancing RAG context with Semantic Graph dependencies...")
                # Pseudo-code logic for connecting to global_graph:
                # for chunk in local_chunks:
                #     deps = get_dependencies_from_graph(chunk.source)
                #     local_chunks.extend(fetch_chunks(deps))
                pass

        best_score = max((c.similarity for c in local_chunks), default=0.0)
        # Web search only if: enabled AND query is technical AND score too low
        use_web = web_enabled and (force_web or best_score < threshold)

        # --- Web retrieval (fallback or supplement) ---
        web_chunks: List[RetrievedChunk] = []
        if use_web:
            logger.info(
                f"Web search triggered (best local score={best_score:.2f} < threshold={threshold:.2f})"
            )
            web_chunks = self.web_retriever.retrieve(query, n_results)

        # --- Merge and format ---
        all_chunks = local_chunks + web_chunks

        if not all_chunks:
            return [], "No relevant context found in the codebase or the web."

        # Determine source type label for the LLM client
        if local_chunks and web_chunks:
            source_type = "hybrid"
        elif web_chunks:
            source_type = "web"
        else:
            source_type = "codebase"

        # Build combined context string
        parts = []
        if local_chunks:
            parts.append(self.retriever.format_context(local_chunks))
        if web_chunks:
            parts.append(self.web_retriever.format_context(web_chunks))
        context = "\n\n".join(parts)

        # Attach source_type as attribute for callers to use
        # (We return the same (chunks, context) tuple to preserve compatibility)
        self._last_source_type = source_type
        return all_chunks, context

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
