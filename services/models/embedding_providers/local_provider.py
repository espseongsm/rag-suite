"""HTTP adapter for a local embedding server such as Hugging Face TEI."""

from __future__ import annotations

from typing import List

import httpx

from services.models.embedding_providers.base import EmbeddingProvider
from services.models.models import EmbeddingResponse, ModelCapability, ModelInfo


class LocalEmbeddingProvider(EmbeddingProvider):
    """Calls a local embedding HTTP service and normalizes its response."""

    def __init__(self, base_url: str, model_names: List[str], timeout_seconds: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._model_names = model_names
        self._client = httpx.Client(timeout=timeout_seconds)

    def embed(self, texts: List[str], model: str) -> EmbeddingResponse:
        if model not in self._model_names:
            raise ValueError(f"Model '{model}' not configured. Available: {self._model_names}")

        response = self._client.post(f"{self._base_url}/embed", json={"inputs": texts})
        response.raise_for_status()
        embeddings = _normalize_embedding_payload(response.json())
        return EmbeddingResponse(embeddings=embeddings, model=model, provider="local")

    def get_supported_embedding_models(self) -> List[ModelInfo]:
        return [
            ModelInfo(
                name=name,
                provider="local",
                capabilities=ModelCapability(context_window=512),
            )
            for name in self._model_names
        ]


def _normalize_embedding_payload(payload) -> List[List[float]]:
    """Support TEI /embed and OpenAI-compatible response shapes."""
    if isinstance(payload, dict) and "data" in payload:
        return [item["embedding"] for item in payload["data"]]
    if isinstance(payload, list) and payload and all(isinstance(x, (int, float)) for x in payload):
        return [payload]
    if isinstance(payload, list):
        return payload
    raise ValueError("Unsupported embedding response shape")
