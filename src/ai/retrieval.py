"""
Local RAG retrieval — finds the most relevant policy/rule document chunks
for a given investigation query.

Uses cosine similarity (dot product on L2-normalized vectors) against the
pre-built local FAISS-compatible numpy matrix.
Falls back to keyword matching when embeddings are unavailable.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import numpy as np

from src.ai.embeddings import DocumentChunk, EmbeddingIndex
from src.ai.gemini_client import get_client

logger = logging.getLogger(__name__)

TOP_K = 4  # number of chunks to retrieve per query


def retrieve_relevant_chunks(
    index: EmbeddingIndex,
    query: str,
    top_k: int = TOP_K,
) -> list[DocumentChunk]:
    """
    Retrieve the top-k most relevant document chunks for the query.
    Uses Gemini embedding similarity if available, else keyword fallback.
    """
    if not index.chunks:
        return []

    # Try semantic retrieval first
    if index.matrix is not None and get_client().available:
        try:
            return _semantic_retrieve(index, query, top_k)
        except Exception as exc:
            logger.warning(f"Semantic retrieval failed: {exc}. Falling back to keyword.")

    # Keyword fallback
    return _keyword_retrieve(index.chunks, query, top_k)


def _semantic_retrieve(
    index: EmbeddingIndex,
    query: str,
    top_k: int,
) -> list[DocumentChunk]:
    """Cosine similarity retrieval using Gemini query embedding."""
    client = get_client()
    query_emb = client.embed_query(query)
    if query_emb is None:
        return _keyword_retrieve(index.chunks, query, top_k)

    q_vec = np.array(query_emb, dtype=np.float32)
    norm = np.linalg.norm(q_vec)
    if norm > 0:
        q_vec = q_vec / norm

    # matrix is already L2-normalized, so dot product = cosine similarity
    scores = index.matrix @ q_vec  # (n_chunks,)
    top_indices = np.argsort(scores)[::-1][:top_k]

    return [index.chunks[i] for i in top_indices]


def _keyword_retrieve(
    chunks: list[DocumentChunk],
    query: str,
    top_k: int,
) -> list[DocumentChunk]:
    """Simple keyword overlap scoring as fallback."""
    query_words = set(re.findall(r"\w+", query.lower()))

    scored: list[tuple[float, DocumentChunk]] = []
    for chunk in chunks:
        chunk_words = set(re.findall(r"\w+", chunk.text.lower()))
        overlap = len(query_words & chunk_words)
        scored.append((overlap, chunk))

    scored.sort(key=lambda x: -x[0])
    return [chunk for _, chunk in scored[:top_k]]


def build_retrieval_query(triggered_rule_ids: list[str], payees: list[str]) -> str:
    """Build a natural-language query from triggered rules for retrieval."""
    rule_map = {
        "R1": "unusually large transaction amount deviation threshold investigation",
        "R2": "new payee burst multiple transactions short time window",
        "R3": "odd hours activity timing deviation suspicious time",
        "R4": "behavioural pattern deviation multidimensional score",
    }
    parts = [rule_map.get(rid, "") for rid in triggered_rule_ids if rid in rule_map]
    if payees:
        parts.append(f"payee verification {' '.join(payees[:3])}")
    return " ".join(parts) or "transaction investigation risk signal banking"
