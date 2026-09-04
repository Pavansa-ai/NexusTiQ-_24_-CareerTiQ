"""
Document chunking and embedding generation for local RAG.

Reads documents from data/documents/, chunks them, generates Gemini embeddings,
and persists the index to data/index/ so it can be loaded on subsequent startups.
"""
from __future__ import annotations

import json
import logging
import os
import pickle
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from src.ai.gemini_client import get_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

DOCUMENTS_DIR = Path("data/documents")
INDEX_DIR = Path("data/index")
INDEX_FILE = INDEX_DIR / "embeddings.pkl"
CHUNK_SIZE = 400      # characters per chunk
CHUNK_OVERLAP = 80    # character overlap between chunks


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class DocumentChunk:
    chunk_id: str
    source_file: str
    section_title: str
    text: str
    embedding: list[float] = field(default_factory=list)


@dataclass
class EmbeddingIndex:
    chunks: list[DocumentChunk]
    matrix: Optional[np.ndarray]  # shape (n_chunks, embed_dim)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_or_build_index() -> EmbeddingIndex:
    """
    Load a pre-built index from disk, or build one from documents if missing.
    Also rebuilds if documents were modified more recently than the index.
    """
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    if _index_is_fresh():
        try:
            return _load_index()
        except Exception as exc:
            logger.warning(f"Could not load saved index: {exc}. Rebuilding.")

    logger.info("Building embedding index from documents…")
    index = _build_index()
    _save_index(index)
    return index


def _index_is_fresh() -> bool:
    """Check if the saved index is newer than all document files."""
    if not INDEX_FILE.exists():
        return False
    idx_mtime = INDEX_FILE.stat().st_mtime
    for doc_path in DOCUMENTS_DIR.glob("*.md"):
        if doc_path.stat().st_mtime > idx_mtime:
            return False
    return True


def _load_index() -> EmbeddingIndex:
    with open(INDEX_FILE, "rb") as f:
        data = pickle.load(f)
    logger.info(f"Loaded embedding index: {len(data.chunks)} chunks.")
    return data


def _save_index(index: EmbeddingIndex) -> None:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(INDEX_FILE, "wb") as f:
        pickle.dump(index, f)
    logger.info(f"Saved embedding index: {len(index.chunks)} chunks.")


def _build_index() -> EmbeddingIndex:
    """Read documents, chunk them, embed, and build the index."""
    chunks = _load_and_chunk_documents()

    if not chunks:
        logger.warning("No document chunks found. Local RAG will be unavailable.")
        return EmbeddingIndex(chunks=[], matrix=None)

    client = get_client()
    if not client.available:
        logger.warning("Gemini unavailable — index has no embeddings. RAG will use keyword fallback.")
        return EmbeddingIndex(chunks=chunks, matrix=None)

    texts = [c.text for c in chunks]
    logger.info(f"Embedding {len(texts)} chunks via Gemini…")
    embeddings = client.embed(texts, task_type="RETRIEVAL_DOCUMENT")

    valid_chunks = []
    valid_embeddings = []
    for chunk, emb in zip(chunks, embeddings or []):
        if emb and len(emb) > 0:
            chunk.embedding = emb
            valid_chunks.append(chunk)
            valid_embeddings.append(emb)
        else:
            logger.warning(f"Skipping chunk '{chunk.chunk_id}' — empty embedding.")

    if valid_embeddings:
        matrix = np.array(valid_embeddings, dtype=np.float32)
        # L2-normalize for cosine similarity via dot product
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-9, norms)
        matrix = matrix / norms
    else:
        matrix = None

    return EmbeddingIndex(chunks=valid_chunks, matrix=matrix)


def _load_and_chunk_documents() -> list[DocumentChunk]:
    """Read all .md files from documents dir and chunk them."""
    chunks: list[DocumentChunk] = []

    if not DOCUMENTS_DIR.exists():
        logger.warning(f"Documents directory not found: {DOCUMENTS_DIR}")
        return chunks

    for doc_path in sorted(DOCUMENTS_DIR.glob("*.md")):
        text = doc_path.read_text(encoding="utf-8")
        file_chunks = _chunk_text(text, doc_path.name)
        chunks.extend(file_chunks)

    logger.info(f"Loaded {len(chunks)} chunks from {DOCUMENTS_DIR}")
    return chunks


def _chunk_text(text: str, source_file: str) -> list[DocumentChunk]:
    """Split text into overlapping chunks, preserving section headers."""
    lines = text.split("\n")
    chunks: list[DocumentChunk] = []
    current_section = source_file.replace(".md", "").replace("_", " ").title()
    current_text = ""
    chunk_idx = 0

    def flush(sec: str, content: str) -> None:
        nonlocal chunk_idx
        content = content.strip()
        if not content:
            return
        # Split long sections into overlapping character chunks
        start = 0
        while start < len(content):
            end = min(start + CHUNK_SIZE, len(content))
            snippet = content[start:end]
            chunk_id = f"{source_file}_{chunk_idx:03d}"
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    source_file=source_file,
                    section_title=sec,
                    text=f"[{sec}]\n{snippet}",
                )
            )
            chunk_idx += 1
            if end >= len(content):
                break
            start = end - CHUNK_OVERLAP

    for line in lines:
        if line.startswith("# ") or line.startswith("## "):
            flush(current_section, current_text)
            current_section = line.lstrip("#").strip()
            current_text = line + "\n"
        else:
            current_text += line + "\n"

    flush(current_section, current_text)
    return chunks
