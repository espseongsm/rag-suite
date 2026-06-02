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
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genai_platform import GenAIPlatform
from services.data.models import IndexConfig, IngestJob, SearchResult

DEFAULT_GATEWAY_URL = "localhost:50051"
DEFAULT_INDEX_NAME = "chapter-5-live-smoke"
DEFAULT_DOCUMENT_PATH = Path(__file__).resolve().parents[1] / "chapter-5.md"
DOCUMENT_PREVIEW_LINES = 10
SMOKE_QUESTION = "What does the Data Service provide for grounding AI applications?"
KNOWN_EMBEDDING_DIMENSIONS = {
    "sentence-transformers/all-MiniLM-L6-v2": 384,
    "BAAI/bge-m3": 1024,
    "Qwen/Qwen3-Embedding-0.6B": 1024,
    "intfloat/multilingual-e5-large": 1024,
    "Snowflake/snowflake-arctic-embed-l-v2.0": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


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
        default=None,
        help="Override the embedding model. Defaults to the running Model Service model.",
    )
    parser.add_argument(
        "--embedding-dimensions",
        type=int,
        default=None,
        help="Override embedding vector dimensions for the index.",
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


def first_lines(content: bytes, line_count: int) -> list[str]:
    text = content.decode("utf-8", errors="replace")
    return text.splitlines()[:line_count]


def _format_embedding_models(models: list[Any]) -> str:
    return ", ".join(f"{model.name} ({model.provider})" for model in models) or "none"


def _select_embedding_model(models: list[Any]) -> Any:
    for model in models:
        if model.provider == "local":
            return model
    return models[0]


def resolve_embedding_config(
    platform: GenAIPlatform,
    embedding_model: str | None,
    embedding_dimensions: int | None,
) -> tuple[str, int, list[Any]]:
    available_models = platform.models.list_embedding_models()

    if embedding_model:
        if not available_models:
            raise RuntimeError(
                "No embedding models are available from Model Service. "
                "Start the stack with --local-embedding-model or configure an embedding provider."
            )
        model_name = embedding_model
        available_model_names = {model.name for model in available_models}
        if model_name not in available_model_names:
            raise RuntimeError(
                f"Requested embedding model '{model_name}' is not available from Model Service. "
                f"Available embedding models: {_format_embedding_models(available_models)}"
            )
    else:
        if not available_models:
            raise RuntimeError(
                "No embedding models are available from Model Service. "
                "Start the stack with --local-embedding-model or configure an embedding provider."
            )
        model_name = _select_embedding_model(available_models).name

    dimensions = embedding_dimensions or KNOWN_EMBEDDING_DIMENSIONS.get(model_name)
    if dimensions is None:
        raise RuntimeError(
            f"Unknown embedding dimensions for model '{model_name}'. "
            "Pass --embedding-dimensions explicitly. "
            f"Available embedding models: {_format_embedding_models(available_models)}"
        )

    return model_name, dimensions, available_models


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
        print(f"\nResult {index}: score={result.score:.4f} document={result.document_id}")
        if result.metadata:
            metadata = ", ".join(f"{key}={value}" for key, value in sorted(result.metadata.items()))
            print(f"metadata: {metadata}")
        print("response text:")
        print(result.text)


def run_smoke(args: argparse.Namespace) -> int:
    platform = GenAIPlatform(gateway_url=args.gateway_url)
    created_index = False
    embedding_model, embedding_dimensions, available_embedding_models = resolve_embedding_config(
        platform=platform,
        embedding_model=args.embedding_model,
        embedding_dimensions=args.embedding_dimensions,
    )
    document_path = args.document.expanduser().resolve()
    document_content = read_document(document_path)

    print(f"Gateway     : {args.gateway_url}")
    print(f"Index       : {args.index}")
    print(f"Embeddings  : {embedding_model} ({embedding_dimensions} dims)")
    print(f"Available   : {_format_embedding_models(available_embedding_models)}")
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
                embedding_model=embedding_model,
                embedding_dimensions=embedding_dimensions,
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
        print(f"    indexed document first {DOCUMENT_PREVIEW_LINES} lines:")
        for line_number, line in enumerate(
            first_lines(document_content, DOCUMENT_PREVIEW_LINES),
            start=1,
        ):
            print(f"    {line_number:02d}: {line}")
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
