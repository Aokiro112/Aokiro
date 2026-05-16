"""
Architect-JS RAG Pipeline — Web Search Retriever
Fetches live search results and converts them into RetrievedChunk format
so they can be seamlessly mixed with local vector store results.

Strategy (in priority order):
  1. Google Custom Search API  — if GOOGLE_API_KEY + GOOGLE_CSE_ID are set in .env
  2. DuckDuckGo (duckduckgo_search) — free, no API key required (fallback)
  3. Graceful no-op — if neither is available, returns an empty list with a warning
"""
from __future__ import annotations

import urllib.parse
import urllib.request
import json
from dataclasses import dataclass
from typing import List, Optional

from ..config import get_config
from ..logger import get_logger
from .retriever import RetrievedChunk

logger = get_logger("rag.web_retriever")


def _google_search(query: str, api_key: str, cse_id: str, n: int) -> List[dict]:
    """Call Google Custom Search JSON API."""
    params = urllib.parse.urlencode({
        "q": query,
        "key": api_key,
        "cx": cse_id,
        "num": min(n, 10),
    })
    url = f"https://www.googleapis.com/customsearch/v1?{params}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [])
        return [
            {
                "title": item.get("title", ""),
                "snippet": item.get("snippet", ""),
                "link": item.get("link", ""),
            }
            for item in items
        ]
    except Exception as e:
        logger.warning(f"Google Custom Search failed: {e}")
        return []


def _ddg_search(query: str, n: int) -> List[dict]:
    """Use ddgs library (no API key needed)."""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=n):
                results.append({
                    "title": r.get("title", ""),
                    "snippet": r.get("body", ""),
                    "link": r.get("href", ""),
                })
        return results
    except ImportError:
        logger.warning(
            "ddgs is not installed. "
            "Run: pip install ddgs   (or set GOOGLE_API_KEY + GOOGLE_CSE_ID)"
        )
        return []
    except Exception as e:
        logger.warning(f"DuckDuckGo search failed: {e}")
        return []


def _results_to_chunks(results: List[dict]) -> List[RetrievedChunk]:
    """Convert raw search result dicts into RetrievedChunk objects."""
    chunks = []
    for i, r in enumerate(results):
        content = f"**{r['title']}**\n{r['snippet']}\nSource: {r['link']}"
        chunks.append(RetrievedChunk(
            content=content,
            source=r["link"],
            start_line=0,
            end_line=0,
            language="web",
            chunk_index=i,
            similarity=0.75,   # Flat score — web results are not vector-ranked
            distance=0.25,
        ))
    return chunks


class WebRetriever:
    """
    Searches the web and returns results as RetrievedChunk objects.
    Prefers Google Custom Search API; falls back to DuckDuckGo.
    """

    def __init__(self):
        cfg = get_config()
        self.cfg = cfg.web_search
        self.max_results = self.cfg.max_results

    def is_available(self) -> bool:
        """True if at least one search backend can be used."""
        if self.cfg.google_api_key and self.cfg.google_cse_id:
            return True
        try:
            import ddgs  # noqa: F401
            return True
        except ImportError:
            return False

    def retrieve(self, query: str, n_results: Optional[int] = None) -> List[RetrievedChunk]:
        """
        Run a web search and return results as RetrievedChunk list.

        Args:
            query: Natural language search query.
            n_results: Max results to return (overrides config).

        Returns:
            List of RetrievedChunk with language='web'.
        """
        if not self.cfg.enabled:
            return []

        n = n_results or self.max_results

        # Try Google first if keys are present
        if self.cfg.google_api_key and self.cfg.google_cse_id:
            logger.debug(f"Web search via Google CSE: {query!r}")
            raw = _google_search(query, self.cfg.google_api_key, self.cfg.google_cse_id, n)
            if raw:
                return _results_to_chunks(raw)

        # Fallback: DuckDuckGo (free)
        logger.debug(f"Web search via DuckDuckGo: {query!r}")
        raw = _ddg_search(query, n)
        if raw:
            return _results_to_chunks(raw)

        logger.warning("Web search returned no results — both backends failed or unavailable.")
        return []

    def format_context(self, chunks: List[RetrievedChunk]) -> str:
        """Format web search chunks into a context string for LLM injection."""
        if not chunks:
            return ""
        parts = []
        for i, chunk in enumerate(chunks, 1):
            parts.append(f"[Web Result {i}]\n{chunk.content}")
        return "\n\n".join(parts)
