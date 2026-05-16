"""
Architect-JS RAG Pipeline — Document Ingestion & Chunking

Supports:
  - TypeScript/JavaScript source files (.ts, .tsx, .js, .jsx)
  - Markdown files (.md)
  - JSON files (.json, .jsonl)
  - Plain text files (.txt)
  - PDF files (.pdf) — requires pypdf
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional

from ..logger import get_logger

logger = get_logger("rag.ingestion")

# Supported file extensions
CODE_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}
DOC_EXTENSIONS = {".md", ".markdown", ".txt", ".rst"}
DATA_EXTENSIONS = {".json", ".jsonl"}
PDF_EXTENSIONS = {".pdf"}

ALL_SUPPORTED = CODE_EXTENSIONS | DOC_EXTENSIONS | DATA_EXTENSIONS | PDF_EXTENSIONS

# Files/directories to skip
IGNORE_PATTERNS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".next", "coverage", ".cache",
    "package-lock.json",  # Too noisy
}


@dataclass
class Document:
    """A raw document loaded from disk before chunking."""
    source: str          # Absolute file path
    content: str         # Full text content
    language: str        # "typescript" | "javascript" | "markdown" | "json" | "text"
    size_bytes: int = 0

    @property
    def relative_path(self) -> str:
        """Returns path relative to cwd if possible."""
        try:
            return str(Path(self.source).relative_to(Path.cwd()))
        except ValueError:
            return self.source


@dataclass
class Chunk:
    """A chunk of text derived from a Document, ready for embedding."""
    source: str        # Parent document path
    content: str       # Chunk text
    chunk_index: int   # Position within the document
    language: str      # Inherited from parent document
    start_line: int = 0
    end_line: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        """Deterministic ID for deduplication."""
        import hashlib
        h = hashlib.sha256(f"{self.source}::{self.chunk_index}".encode()).hexdigest()
        return h[:16]

    def to_metadata(self) -> dict:
        return {
            "source": self.source,
            "chunk_index": self.chunk_index,
            "language": self.language,
            "start_line": self.start_line,
            "end_line": self.end_line,
            **self.metadata,
        }


class DocumentIngester:
    """
    Scans directories and files, loads content, and splits into chunks.
    Uses a simple line-based chunking strategy optimized for code.
    """

    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 50):
        self.chunk_size = chunk_size  # Characters per chunk (approx 1 char ≈ 0.25 tokens for code)
        self.chunk_overlap = chunk_overlap

    def _should_skip(self, path: Path) -> bool:
        """Return True if the path should be ignored."""
        for part in path.parts:
            if part in IGNORE_PATTERNS:
                return True
        # Skip very large files (>500KB)
        if path.is_file() and path.stat().st_size > 500_000:
            logger.debug(f"Skipping large file: {path}")
            return True
        return False

    def _detect_language(self, ext: str) -> str:
        if ext in {".ts", ".tsx"}:
            return "typescript"
        if ext in {".js", ".jsx", ".mjs", ".cjs"}:
            return "javascript"
        if ext in {".md", ".markdown"}:
            return "markdown"
        if ext in {".json", ".jsonl"}:
            return "json"
        if ext == ".pdf":
            return "pdf"
        return "text"

    def _read_pdf(self, path: Path) -> Optional[str]:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages)
        except ImportError:
            logger.warning("pypdf not installed — skipping PDF file. Run: pip install pypdf")
            return None
        except Exception as e:
            logger.warning(f"Could not read PDF {path}: {e}")
            return None

    def _read_jsonl(self, path: Path) -> str:
        """For .jsonl, pretty-print each line as a separate JSON block."""
        lines = []
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        lines.append(json.dumps(obj, indent=2))
                    except json.JSONDecodeError:
                        lines.append(line)
                    if i >= 200:  # Limit large JSONL files
                        lines.append("... (truncated)")
                        break
        except Exception as e:
            logger.warning(f"Could not read JSONL {path}: {e}")
        return "\n---\n".join(lines)

    def load_file(self, path: Path) -> Optional[Document]:
        """Load a single file and return a Document."""
        if self._should_skip(path):
            return None

        ext = path.suffix.lower()
        if ext not in ALL_SUPPORTED:
            return None

        language = self._detect_language(ext)

        if ext == ".pdf":
            content = self._read_pdf(path)
        elif ext == ".jsonl":
            content = self._read_jsonl(path)
        else:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                logger.warning(f"Could not read {path}: {e}")
                return None

        if not content or not content.strip():
            return None

        return Document(
            source=str(path.resolve()),
            content=content,
            language=language,
            size_bytes=len(content.encode("utf-8")),
        )

    def scan_path(self, target: str | Path) -> List[Document]:
        """Scan a file or directory and return all loadable Documents."""
        target = Path(target)
        docs: List[Document] = []

        if target.is_file():
            doc = self.load_file(target)
            if doc:
                docs.append(doc)
        elif target.is_dir():
            for path in target.rglob("*"):
                if path.is_file():
                    doc = self.load_file(path)
                    if doc:
                        docs.append(doc)
        else:
            logger.warning(f"Path not found: {target}")

        logger.info(f"Loaded {len(docs)} documents from {target}")
        return docs

    def chunk_document(self, doc: Document) -> List[Chunk]:
        """
        Split a document into overlapping chunks.
        Code files: split by lines; other files: split by characters.
        """
        chunks: List[Chunk] = []
        lines = doc.content.splitlines(keepends=True)

        if not lines:
            return chunks

        # Build chunks from lines
        current_lines: List[str] = []
        current_chars = 0
        chunk_index = 0
        start_line = 1
        line_num = 1

        for line in lines:
            current_lines.append(line)
            current_chars += len(line)

            if current_chars >= self.chunk_size:
                content = "".join(current_lines)
                chunks.append(Chunk(
                    source=doc.source,
                    content=content,
                    chunk_index=chunk_index,
                    language=doc.language,
                    start_line=start_line,
                    end_line=line_num,
                ))
                chunk_index += 1

                # Overlap: keep last N chars worth of lines
                overlap_chars = 0
                overlap_lines: List[str] = []
                for prev_line in reversed(current_lines):
                    if overlap_chars + len(prev_line) > self.chunk_overlap:
                        break
                    overlap_lines.insert(0, prev_line)
                    overlap_chars += len(prev_line)

                current_lines = overlap_lines
                current_chars = overlap_chars
                start_line = line_num - len(overlap_lines) + 1

            line_num += 1

        # Flush remaining content
        if current_lines:
            content = "".join(current_lines)
            if content.strip():
                chunks.append(Chunk(
                    source=doc.source,
                    content=content,
                    chunk_index=chunk_index,
                    language=doc.language,
                    start_line=start_line,
                    end_line=line_num - 1,
                ))

        return chunks

    def ingest(self, target: str | Path) -> List[Chunk]:
        """Full ingestion: scan → load → chunk. Returns all chunks."""
        docs = self.scan_path(target)
        all_chunks: List[Chunk] = []
        for doc in docs:
            chunks = self.chunk_document(doc)
            all_chunks.extend(chunks)
        logger.info(f"Generated {len(all_chunks)} chunks from {len(docs)} documents")
        return all_chunks
