"""
Architect-JS RAG Pipeline — ChromaDB Vector Store
Persistent vector storage with metadata filtering and deduplication.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config import get_config
from ..logger import get_logger
from .ingestion import Chunk

logger = get_logger("rag.store")


class VectorStore:
    """
    ChromaDB-backed persistent vector store.
    Uses the EF (embedding function) interface for flexible embedding models.
    """

    def __init__(
        self,
        collection_name: Optional[str] = None,
        db_path: Optional[str] = None,
    ):
        cfg = get_config()
        self.collection_name = collection_name or cfg.rag.collection_name
        self.db_path = Path(db_path or cfg.rag.db_path).resolve()
        self.db_path.mkdir(parents=True, exist_ok=True)

        self._client = None
        self._collection = None

    def _get_client(self):
        if self._client is None:
            try:
                import chromadb
                self._client = chromadb.PersistentClient(path=str(self.db_path))
                logger.info(f"ChromaDB initialized at: {self.db_path}")
            except ImportError:
                raise RuntimeError(
                    "chromadb is not installed. Run: pip install chromadb"
                )
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    def add_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]) -> int:
        """
        Add chunks with their embeddings to the store.
        Skips duplicates based on chunk ID.
        Returns number of new chunks added.
        """
        if not chunks or not embeddings:
            return 0

        if len(chunks) != len(embeddings):
            raise ValueError(f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) length mismatch")

        collection = self._get_collection()

        # Build batch
        ids = [c.id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = [c.to_metadata() for c in chunks]

        # Check for existing IDs to avoid duplicate errors
        existing = collection.get(ids=ids, include=[])
        existing_ids = set(existing.get("ids", []))
        new_indices = [i for i, id_ in enumerate(ids) if id_ not in existing_ids]

        if not new_indices:
            logger.debug(f"All {len(chunks)} chunks already exist in store")
            return 0

        # Add only new chunks in batches of 100
        batch_size = 100
        added = 0
        for batch_start in range(0, len(new_indices), batch_size):
            batch_idx = new_indices[batch_start:batch_start + batch_size]
            collection.add(
                ids=[ids[i] for i in batch_idx],
                embeddings=[embeddings[i] for i in batch_idx],
                documents=[documents[i] for i in batch_idx],
                metadatas=[metadatas[i] for i in batch_idx],
            )
            added += len(batch_idx)

        logger.info(f"Added {added} new chunks to '{self.collection_name}' (skipped {len(chunks) - added} duplicates)")
        return added

    def query(
        self,
        query_embedding: List[float],
        n_results: int = 5,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Query the vector store for similar chunks.
        Returns a list of result dicts with 'content', 'metadata', 'distance'.
        """
        collection = self._get_collection()

        try:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n_results, self.count()),
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"Query error: {e}")
            return []

        if not results or not results.get("ids"):
            return []

        items = []
        ids = results["ids"][0]
        docs = results["documents"][0]
        metas = results["metadatas"][0]
        dists = results["distances"][0]

        for id_, doc, meta, dist in zip(ids, docs, metas, dists):
            items.append({
                "id": id_,
                "content": doc,
                "metadata": meta,
                "distance": dist,
                "similarity": 1.0 - dist,  # cosine distance → similarity
            })

        return items

    def count(self) -> int:
        """Return total number of chunks in the collection."""
        try:
            return self._get_collection().count()
        except Exception:
            return 0

    def get_collection_info(self) -> Dict[str, Any]:
        """Return summary information about the collection."""
        try:
            col = self._get_collection()
            count = col.count()
            # Sample a few to get unique sources
            if count > 0:
                sample = col.get(limit=min(count, 1000), include=["metadatas"])
                sources = set()
                for meta in sample.get("metadatas", []):
                    if meta and "source" in meta:
                        sources.add(meta["source"])
            else:
                sources = set()

            return {
                "collection": self.collection_name,
                "db_path": str(self.db_path),
                "total_chunks": count,
                "unique_sources": len(sources),
                "sources": sorted(sources),
            }
        except Exception as e:
            return {"error": str(e)}

    def reset(self) -> None:
        """Delete and recreate the collection."""
        client = self._get_client()
        try:
            client.delete_collection(self.collection_name)
            logger.warning(f"Deleted collection: {self.collection_name}")
        except Exception:
            pass
        self._collection = None

    def delete_by_source(self, source_path: str) -> int:
        """Remove all chunks from a specific source file."""
        collection = self._get_collection()
        try:
            results = collection.get(
                where={"source": source_path},
                include=["metadatas"],
            )
            ids = results.get("ids", [])
            if ids:
                collection.delete(ids=ids)
                logger.info(f"Deleted {len(ids)} chunks from {source_path}")
            return len(ids)
        except Exception as e:
            logger.error(f"Error deleting chunks for {source_path}: {e}")
            return 0
