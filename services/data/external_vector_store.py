"""VectorStore wrapper for external vector databases.

Postgres remains the durable state store for indexes, documents, ingest jobs,
and keyword search. The selected backend owns vector upsert/search.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Dict, List, Optional

from services.data.models import (
    Chunk,
    ClaimedJob,
    DocumentMetadata,
    Index,
    IngestJob,
    JobPayload,
)
from services.data.store import VectorStore
from services.data.vector_backends import VectorBackend, VectorRecord

if TYPE_CHECKING:
    from services.data.pgvector_store import PgvectorStore


class ExternalVectorStore(VectorStore):
    """Compose Postgres state with an external vector-search backend."""

    def __init__(
        self,
        backend: VectorBackend,
        state_store: Optional["PgvectorStore"] = None,
    ):
        self._backend = backend
        if state_store is None:
            from services.data.pgvector_store import PgvectorStore

            state_store = PgvectorStore(
                os.getenv("DB_CONNECTION_STRING", "postgresql://localhost/genai_platform")
            )
        self._state = state_store

    # ------------------------------------------------------------------ chunks

    def insert(
        self,
        index_name: str,
        document_id: str,
        chunks: List[Chunk],
        embeddings: List[List[float]],
        metadata: Dict[str, str],
    ) -> int:
        records = [
            VectorRecord(
                chunk_id=str(uuid.uuid4()),
                document_id=document_id,
                text=chunk.text,
                embedding=embedding,
                metadata=dict(metadata),
            )
            for chunk, embedding in zip(chunks, embeddings)
        ]
        self._backend.upsert(index_name, records)
        self._state.insert_chunk_records(index_name, records)
        return len(records)

    def delete_by_document(self, index_name: str, document_id: str) -> int:
        self._backend.delete_by_document(index_name, document_id)
        return self._state.delete_by_document(index_name, document_id)

    def delete_index(self, index_name: str) -> int:
        self._backend.delete_index(index_name)
        return self._state.delete_index(index_name)

    def search(
        self,
        index_name: str,
        query_embedding: List[float],
        top_k: int = 5,
        metadata_filters: Optional[Dict[str, str]] = None,
        score_threshold: Optional[float] = None,
    ):
        return self._backend.search(
            index_name=index_name,
            query_embedding=query_embedding,
            top_k=top_k,
            metadata_filters=metadata_filters,
            score_threshold=score_threshold,
        )

    def keyword_search(
        self,
        index_name: str,
        query: str,
        top_k: int = 5,
        metadata_filters: Optional[Dict[str, str]] = None,
    ):
        return self._state.keyword_search(index_name, query, top_k, metadata_filters)

    def hybrid_search(
        self,
        index_name: str,
        query: str,
        query_embedding: List[float],
        top_k: int = 5,
        metadata_filters: Optional[Dict[str, str]] = None,
        score_threshold: Optional[float] = None,
    ):
        if not getattr(self._backend, "supports_native_hybrid_search", False):
            raise NotImplementedError(
                f"{type(self._backend).__name__} does not support native hybrid search"
            )
        return self._backend.hybrid_search(
            index_name=index_name,
            query=query,
            query_embedding=query_embedding,
            top_k=top_k,
            metadata_filters=metadata_filters,
            score_threshold=score_threshold,
        )

    # ------------------------------------------------------------------ indexes

    def create_index(self, index: Index) -> None:
        if self._state.get_index(index.name) is not None:
            raise ValueError(f"Index '{index.name}' already exists")
        self._backend.create_index(index)
        self._state.create_index(index)

    def get_index(self, name: str) -> Optional[Index]:
        return self._state.get_index(name)

    def list_indexes(self) -> List[Index]:
        return self._state.list_indexes()

    def increment_index_stats(
        self,
        name: str,
        documents_delta: int,
        chunks_delta: int,
        last_ingested_at: datetime,
    ) -> None:
        self._state.increment_index_stats(name, documents_delta, chunks_delta, last_ingested_at)

    # ----------------------------------------------------------------- documents

    def put_document(self, doc: DocumentMetadata) -> None:
        self._state.put_document(doc)

    def get_document(self, index_name: str, document_id: str) -> Optional[DocumentMetadata]:
        return self._state.get_document(index_name, document_id)

    def list_documents(self, index_name: str) -> List[DocumentMetadata]:
        return self._state.list_documents(index_name)

    # ----------------------------------------------------------------- job queue

    def enqueue_job(self, job: IngestJob, index_name: str, payload: JobPayload) -> None:
        self._state.enqueue_job(job, index_name, payload)

    def get_job(self, job_id: str) -> Optional[IngestJob]:
        return self._state.get_job(job_id)

    def update_job(
        self,
        job_id: str,
        *,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        document_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        self._state.update_job(
            job_id,
            status=status,
            progress=progress,
            document_id=document_id,
            error=error,
        )

    def claim_next_job(self, worker_id: str) -> Optional[ClaimedJob]:
        return self._state.claim_next_job(worker_id)

    def release_stale_claims(self, stale_after: timedelta) -> int:
        return self._state.release_stale_claims(stale_after)
