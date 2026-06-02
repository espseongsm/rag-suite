from datetime import datetime, timedelta

from services.data.external_vector_store import ExternalVectorStore
from services.data.models import Chunk, Index, IndexConfig, SearchResult


class FakeBackend:
    supports_native_hybrid_search = False

    def __init__(self):
        self.created = []
        self.upserts = []
        self.deleted_documents = []
        self.deleted_indexes = []

    def create_index(self, index):
        self.created.append(index.name)

    def upsert(self, index_name, records):
        self.upserts.append((index_name, records))

    def delete_by_document(self, index_name, document_id):
        self.deleted_documents.append((index_name, document_id))

    def delete_index(self, index_name):
        self.deleted_indexes.append(index_name)

    def search(
        self,
        index_name,
        query_embedding,
        top_k,
        metadata_filters=None,
        score_threshold=None,
    ):
        return [
            SearchResult(
                chunk_id="chunk-1",
                document_id="doc-1",
                text="hello",
                score=0.9,
                metadata={"dept": "eng"},
            )
        ]


class FakeNativeHybridBackend(FakeBackend):
    supports_native_hybrid_search = True

    def hybrid_search(
        self,
        index_name,
        query,
        query_embedding,
        top_k,
        metadata_filters=None,
        score_threshold=None,
    ):
        self.hybrid_call = (
            index_name,
            query,
            query_embedding,
            top_k,
            metadata_filters,
            score_threshold,
        )
        return [
            SearchResult(
                chunk_id="hybrid-1",
                document_id="doc-1",
                text="native hybrid",
                score=1.0,
            )
        ]


class FakeState:
    def __init__(self):
        self.indexes = {}
        self.inserted = []

    def insert_chunk_records(self, index_name, records):
        self.inserted.append((index_name, records))
        return len(records)

    def delete_by_document(self, index_name, document_id):
        return 2

    def delete_index(self, index_name):
        return 3

    def keyword_search(self, index_name, query, top_k=5, metadata_filters=None):
        return []

    def create_index(self, index):
        self.indexes[index.name] = index

    def get_index(self, name):
        return self.indexes.get(name)

    def list_indexes(self):
        return list(self.indexes.values())

    def increment_index_stats(self, name, documents_delta, chunks_delta, last_ingested_at):
        self.indexes[name].document_count += documents_delta
        self.indexes[name].total_chunks += chunks_delta
        self.indexes[name].last_ingested_at = last_ingested_at

    def put_document(self, doc):
        self.doc = doc

    def get_document(self, index_name, document_id):
        return getattr(self, "doc", None)

    def list_documents(self, index_name):
        return [self.doc] if hasattr(self, "doc") else []

    def enqueue_job(self, job, index_name, payload):
        self.job = job

    def get_job(self, job_id):
        return getattr(self, "job", None)

    def update_job(self, job_id, **kwargs):
        self.job_updates = kwargs

    def claim_next_job(self, worker_id):
        return None

    def release_stale_claims(self, stale_after: timedelta):
        return 0


def test_external_store_mirrors_inserted_chunks_to_state():
    backend = FakeBackend()
    state = FakeState()
    store = ExternalVectorStore(backend, state)

    chunks = [Chunk(text="hello", start_offset=0, end_offset=5)]
    count = store.insert("idx", "doc-1", chunks, [[1.0, 0.0]], {"dept": "eng"})

    assert count == 1
    backend_index, backend_records = backend.upserts[0]
    state_index, state_records = state.inserted[0]
    assert backend_index == state_index == "idx"
    assert backend_records[0].chunk_id == state_records[0].chunk_id
    assert backend_records[0].metadata == {"dept": "eng"}


def test_external_store_delegates_index_and_delete_lifecycle():
    backend = FakeBackend()
    state = FakeState()
    store = ExternalVectorStore(backend, state)
    index = Index(name="idx", config=IndexConfig(name="idx"))

    store.create_index(index)
    store.increment_index_stats("idx", 1, 2, datetime.utcnow())

    assert backend.created == ["idx"]
    assert store.get_index("idx").document_count == 1
    assert store.delete_by_document("idx", "doc-1") == 2
    assert backend.deleted_documents == [("idx", "doc-1")]
    assert store.delete_index("idx") == 3
    assert backend.deleted_indexes == ["idx"]


def test_external_store_delegates_native_hybrid_when_backend_supports_it():
    backend = FakeNativeHybridBackend()
    store = ExternalVectorStore(backend, FakeState())

    results = store.hybrid_search(
        index_name="idx",
        query="hello",
        query_embedding=[1.0, 0.0],
        top_k=2,
        metadata_filters={"dept": "eng"},
        score_threshold=0.1,
    )

    assert results[0].chunk_id == "hybrid-1"
    assert backend.hybrid_call == (
        "idx",
        "hello",
        [1.0, 0.0],
        2,
        {"dept": "eng"},
        0.1,
    )


def test_external_store_rejects_native_hybrid_when_backend_is_vector_only():
    store = ExternalVectorStore(FakeBackend(), FakeState())

    try:
        store.hybrid_search("idx", "hello", [1.0, 0.0])
    except NotImplementedError:
        pass
    else:
        raise AssertionError("Expected vector-only backend to reject native hybrid search")
