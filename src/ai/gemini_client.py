"""
Gemini API client — handles both LLM reasoning and embedding calls.

Uses the current google-genai SDK (google.genai).
Reads GEMINI_API_KEY from environment.
Implements retry logic and graceful fallback on failure.
Never hard-codes keys.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

GEMINI_LLM_MODEL = "gemini-2.0-flash"
GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0


class GeminiClient:
    """
    Thin wrapper around the Google Generative AI SDK (google.genai).
    Handles key loading, model initialisation, and error handling.
    """

    def __init__(self) -> None:
        self._available = False
        self._client = None
        self._init()

    def _init(self) -> None:
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            logger.warning(
                "GEMINI_API_KEY not set. Gemini features will be unavailable. "
                "Deterministic fallback will be used."
            )
            return
        try:
            from google import genai
            self._client = genai.Client(api_key=api_key)
            self._available = True
            logger.info(f"Gemini client initialised (model={GEMINI_LLM_MODEL}).")
        except ImportError:
            logger.error("google-genai package not found. Install with: pip install google-genai")
            self._available = False
        except Exception as exc:
            logger.error(f"Failed to initialise Gemini client: {exc}")
            self._available = False

    @property
    def available(self) -> bool:
        return self._available

    # -----------------------------------------------------------------------
    # Text generation
    # -----------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> Optional[str]:
        """
        Generate text using the Gemini LLM.
        Returns None on failure.
        """
        if not self._available or not self._client:
            return None

        from google.genai import types as genai_types

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=GEMINI_LLM_MODEL,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=temperature,
                        max_output_tokens=max_output_tokens,
                        response_mime_type="application/json",
                    ),
                )
                if response and response.text:
                    return response.text.strip()
                logger.warning(f"Gemini returned empty response (attempt {attempt}).")
            except Exception as exc:
                logger.warning(f"Gemini generate attempt {attempt} failed: {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)

        return None

    # -----------------------------------------------------------------------
    # Embeddings
    # -----------------------------------------------------------------------

    def embed(self, texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> Optional[list[list[float]]]:
        """
        Embed a list of texts using gemini-embedding-001.
        Returns list of embedding vectors, or None on failure.
        """
        if not self._available or not self._client:
            return None

        results: list[list[float]] = []
        for text in texts:
            emb = self._embed_one(text, task_type)
            results.append(emb if emb else [])

        return results

    def embed_query(self, text: str) -> Optional[list[float]]:
        """Embed a single query string for retrieval."""
        if not self._available or not self._client:
            return None
        return self._embed_one(text, "RETRIEVAL_QUERY")

    def _embed_one(self, text: str, task_type: str) -> Optional[list[float]]:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                from google.genai import types as genai_types
                response = self._client.models.embed_content(
                    model=GEMINI_EMBEDDING_MODEL,
                    contents=text,
                    config=genai_types.EmbedContentConfig(task_type=task_type),
                )
                # SDK returns EmbedContentResponse; embedding is in .embeddings[0].values
                if response and response.embeddings:
                    return list(response.embeddings[0].values)
                # Fallback: try .embedding attribute
                if hasattr(response, "embedding") and response.embedding:
                    return list(response.embedding.values)
                logger.warning(f"Empty embedding response (attempt {attempt})")
            except Exception as exc:
                logger.warning(f"Embedding attempt {attempt} failed: {exc}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_DELAY_SECONDS * attempt)
        return None


# Singleton
_client: Optional[GeminiClient] = None


def get_client() -> GeminiClient:
    global _client
    if _client is None:
        _client = GeminiClient()
    return _client
