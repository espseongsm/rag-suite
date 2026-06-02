"""Shared contracts and helpers for external vector database adapters."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

from services.data.models import Index, SearchResult


@dataclass(frozen=True)
class VectorRecord:
    chunk_id: str
    document_id: str
    text: str
    embedding: List[float]
    metadata: Dict[str, str]


class VectorBackend(Protocol):
    """Minimal adapter surface used by ExternalVectorStore."""

    supports_native_hybrid_search: bool

    def create_index(self, index: Index) -> None:
        """Create a backend collection/index for this Data Service index."""

    def upsert(self, index_name: str, records: List[VectorRecord]) -> None:
        """Insert or replace vector records."""

    def delete_by_document(self, index_name: str, document_id: str) -> None:
        """Delete all vector records for one document."""

    def delete_index(self, index_name: str) -> None:
        """Delete the backend collection/index."""

    def search(
        self,
        index_name: str,
        query_embedding: List[float],
        top_k: int,
        metadata_filters: Optional[Dict[str, str]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[SearchResult]:
        """Return nearest vector records."""

    def hybrid_search(
        self,
        index_name: str,
        query: str,
        query_embedding: List[float],
        top_k: int,
        metadata_filters: Optional[Dict[str, str]] = None,
        score_threshold: Optional[float] = None,
    ) -> List[SearchResult]:
        """Run backend-native hybrid search when available."""


def backend_name(raw: str, *, prefix: str = "axe", max_length: int = 63) -> str:
    """Make a stable lower-case backend collection name."""
    normalized = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    base = normalized or "index"
    budget = max_length - len(prefix) - len(digest) - 2
    base = base[: max(budget, 1)].strip("-") or "index"
    return f"{prefix}-{base}-{digest}"


def milvus_name(raw: str, *, prefix: str = "axe", max_length: int = 63) -> str:
    """Milvus collection names are safest as letter/number/underscore."""
    name = backend_name(raw, prefix=prefix, max_length=max_length).replace("-", "_")
    if not name[0].isalpha():
        name = f"i_{name}"
    return name[:max_length]


def weaviate_class_name(raw: str, *, prefix: str = "Axe", max_length: int = 200) -> str:
    """Weaviate class names should start with an uppercase letter."""
    words = re.findall(r"[A-Za-z0-9]+", raw)
    body = "".join(word.capitalize() for word in words) or "Index"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}{body}{digest}"[:max_length]


def expanded_limit(top_k: int, metadata_filters: Optional[Dict[str, str]]) -> int:
    """Fetch a few extra records when client-side filters may apply."""
    if metadata_filters:
        return max(top_k * 10, top_k)
    return top_k


def passes_filters(
    metadata: Dict[str, str],
    metadata_filters: Optional[Dict[str, str]],
) -> bool:
    if not metadata_filters:
        return True
    return all(str(metadata.get(key)) == str(value) for key, value in metadata_filters.items())


def apply_result_filters(
    results: List[SearchResult],
    top_k: int,
    metadata_filters: Optional[Dict[str, str]],
    score_threshold: Optional[float],
) -> List[SearchResult]:
    filtered = [
        result
        for result in results
        if passes_filters(result.metadata, metadata_filters)
        and (score_threshold is None or result.score >= score_threshold)
    ]
    return filtered[:top_k]
