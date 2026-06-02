"""Smoke test an already-running AXE Suite stack.

Run this after starting Docker Compose, for example:

    axe-suite up --vector-db qdrant --local-embedding
    uv run python examples/live_stack_smoke.py

The script uses the public SDK against Gateway, creates a disposable index,
ingests chapter-5.md by default, searches it, and removes the index unless
--keep-index is passed.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genai_platform import GenAIPlatform
from services.data.models import IndexConfig, IngestJob, SearchResult

DEFAULT_GATEWAY_URL = "localhost:50051"
DEFAULT_INDEX_NAME = "chapter-5-live-smoke"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIMENSIONS = 384
DEFAULT_DOCUMENT_PATH = Path(__file__).resolve().parents[1] / "chapter-5.md"
SMOKE_QUESTION = "What does the Data Service provide for grounding AI applications?"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a live SDK -> Gateway -> Data -> Model -> VectorDB smoke test.",
    )
    parser.add_argument(
        "--gateway-url",
        default=DEFAULT_GATEWAY_URL,
        help="Gateway gRPC address.",
    )
    parser.add_argument(
        "--index",
        default=DEFAULT_INDEX_NAME,
        help="Temporary index name to create.",
    )
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help="Embedding model registered in the running Model Service.",
    )
    parser.add_argument(
        "--embedding-dimensions",
        type=int,
        default=DEFAULT_EMBEDDING_DIMENSIONS,
        help="Embedding vector dimensions for the index.",
    )
    parser.add_argument(
        "--document",
        type=Path,
        default=DEFAULT_DOCUMENT_PATH,
        help="Document file to index.",
    )
    parser.add_argument(
        "--question",
        default=SMOKE_QUESTION,
        help="Search query to run after ingestion.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="Seconds to wait for ingestion to complete.",
    )
    parser.add_argument("--chunk-size", type=int, default=900, help="Index chunk size.")
    parser.add_argument("--chunk-overlap", type=int, default=120, help="Index chunk overlap.")
    parser.add_argument(
        "--document-preview-chars",
        type=int,
        default=700,
        help="Characters of the indexed document to print.",
    )
    parser.add_argument(
        "--keep-index",
        action="store_true",
        help="Leave the smoke index in the running backend for manual inspection.",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Use hybrid search instead of vector search.",
    )
    return parser.parse_args()


def read_document(path: Path) -> bytes:
    document_path = path.expanduser().resolve()
    if not document_path.exists():
        raise FileNotFoundError(f"document not found: {document_path}")
    if not document_path.is_file():
        raise ValueError(f"document path is not a file: {document_path}")
    return document_path.read_bytes()


def preview_text(content: bytes, max_chars: int) -> str:
    text = content.decode("utf-8", errors="replace")
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def wait_for_ingest(platform: GenAIPlatform, job_id: str, timeout: float) -> IngestJob:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = platform.data.get_ingest_status(job_id)
        if job.status == "completed":
            return job
        if job.status == "failed":
            raise RuntimeError(job.error or "ingestion failed")
        time.sleep(0.5)
    raise TimeoutError(f"ingestion job {job_id} did not complete within {timeout:.1f}s")


def print_results(results: list[SearchResult]) -> None:
    if not results:
        raise RuntimeError("search returned no results")

    print(f"Retrieved response(s): {len(results)}")
    for index, result in enumerate(results, start=1):
        print(f"\n[{index}] score={result.score:.4f} document={result.document_id}")
        if result.metadata:
            metadata = ", ".join(f"{key}={value}" for key, value in sorted(result.metadata.items()))
            print(f"metadata: {metadata}")
        print("response text:")
        print(result.text)


def run_smoke(args: argparse.Namespace) -> int:
    platform = GenAIPlatform(gateway_url=args.gateway_url)
    created_index = False
    document_path = args.document.expanduser().resolve()
    document_content = read_document(document_path)

    print(f"Gateway     : {args.gateway_url}")
    print(f"Index       : {args.index}")
    print(f"Embeddings  : {args.embedding_model} ({args.embedding_dimensions} dims)")
    print(f"Document    : {document_path}")
    print(f"Size        : {len(document_content)} bytes")

    try:
        print("\n[1] Resetting smoke index...")
        try:
            platform.data.delete_index(args.index)
        except Exception:
            pass

        print("[2] Creating index...")
        platform.data.create_index(
            IndexConfig(
                name=args.index,
                embedding_model=args.embedding_model,
                embedding_dimensions=args.embedding_dimensions,
                chunking_strategy="recursive",
                chunk_size=args.chunk_size,
                chunk_overlap=args.chunk_overlap,
            ),
            owner="live-smoke",
        )
        created_index = True

        print("[3] Ingesting smoke document...")
        print(f"    filename: {document_path.name}")
        print(f"    chunking: recursive size={args.chunk_size} overlap={args.chunk_overlap}")
        print("    indexed document preview:")
        print(f"    {preview_text(document_content, args.document_preview_chars)}")
        job = platform.data.ingest(
            index_name=args.index,
            filename=document_path.name,
            content=document_content,
            content_type="text/plain",
            metadata={"kind": "live-smoke", "source": document_path.name},
        )
        completed = wait_for_ingest(platform, job.job_id, args.timeout)
        print(f"    completed: job={completed.job_id} document={completed.document_id}")

        mode = "hybrid" if args.hybrid else "vector"
        print(f"[4] Asking question ({mode} search)...")
        print(f"    question: {args.question}")
        search_fn = platform.data.hybrid_search if args.hybrid else platform.data.search
        results = search_fn(args.index, query=args.question, top_k=3)
        print_results(results)
    finally:
        if created_index and not args.keep_index:
            print(f"\n[5] Cleaning up index '{args.index}'...")
            platform.data.delete_index(args.index)

    if args.keep_index:
        print(f"\nKept index '{args.index}' for manual inspection.")
    print("\nLive stack smoke test passed.")
    return 0


def main() -> int:
    try:
        return run_smoke(parse_args())
    except Exception as error:
        print(f"\nLive stack smoke test failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
