"""Smoke test an already-running AXE Suite stack.

Run this after starting Docker Compose, for example:

    axe-suite up --vector-db qdrant --local-embedding
    uv run python examples/live_stack_smoke.py

The script uses the public SDK against Gateway, creates a disposable index,
ingests a tiny document, searches it, and removes the index unless --keep-index
is passed.
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
DEFAULT_INDEX_NAME = "live-smoke-qdrant"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_EMBEDDING_DIMENSIONS = 384
SMOKE_DOCUMENT = (
    "AXE Suite live smoke test. The running stack routes SDK calls through Gateway "
    "into Data Service, uses Model Service for local embeddings, and stores vectors "
    "in the selected VectorDB backend."
)
SMOKE_QUESTION = "Where are vectors stored in this live test?"


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
        "--question",
        default=SMOKE_QUESTION,
        help="Search query to run after ingestion.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Seconds to wait for ingestion to complete.",
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

    print(f"Gateway     : {args.gateway_url}")
    print(f"Index       : {args.index}")
    print(f"Embeddings  : {args.embedding_model} ({args.embedding_dimensions} dims)")

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
                chunking_strategy="fixed",
                chunk_size=180,
                chunk_overlap=20,
            ),
            owner="live-smoke",
        )
        created_index = True

        print("[3] Ingesting smoke document...")
        print("    filename: live_stack_smoke.txt")
        print("    indexed document:")
        print(f"    {SMOKE_DOCUMENT}")
        job = platform.data.ingest(
            index_name=args.index,
            filename="live_stack_smoke.txt",
            content=SMOKE_DOCUMENT.encode("utf-8"),
            content_type="text/plain",
            metadata={"kind": "live-smoke"},
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
