"""Command line helpers for running the data-focused GenAI Platform stack."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from genai_platform import GenAIPlatform

DEFAULT_INDEX_NAME = "rag-pipeline-research-summary"
VECTOR_DB_CHOICES = [
    ("qdrant", "Qdrant", ["qdrant"]),
    ("chroma", "Chroma", ["chroma"]),
    ("milvus", "Milvus", ["milvus"]),
    ("weaviate", "Weaviate", ["weaviate"]),
    ("pgvector", "pgvector", []),
    ("opensearch", "OpenSearch", ["opensearch"]),
    ("azure-ai-search", "Azure AI Search", []),
]
DEFAULT_VECTOR_DB = "pgvector"
LOCAL_EMBEDDING_MODEL_CHOICES = [
    (
        "minilm",
        "all-MiniLM-L6-v2",
        "sentence-transformers/all-MiniLM-L6-v2",
        "fast CPU smoke baseline, 384d",
    ),
    (
        "bge-m3",
        "BGE-M3",
        "BAAI/bge-m3",
        "recommended local multilingual RAG baseline, 1024d",
    ),
    (
        "qwen3-0.6b",
        "Qwen3-Embedding-0.6B",
        "Qwen/Qwen3-Embedding-0.6B",
        "multilingual and long-context candidate, up to 1024d",
    ),
    (
        "e5-large",
        "multilingual-e5-large",
        "intfloat/multilingual-e5-large",
        "widely used multilingual baseline, 1024d",
    ),
    (
        "arctic-l-v2",
        "Arctic Embed L v2.0",
        "Snowflake/snowflake-arctic-embed-l-v2.0",
        "multilingual enterprise retrieval candidate, 1024d",
    ),
]


def _default_project_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _compose_base(project_dir: Path, *, profiles: list[str] | None = None) -> list[str]:
    compose_file = project_dir / "docker-compose.yml"
    if not compose_file.exists():
        raise SystemExit(f"docker-compose.yml not found in {project_dir}")

    command = [
        "docker",
        "compose",
        "--project-directory",
        str(project_dir),
        "-f",
        str(compose_file),
    ]
    for profile in profiles or []:
        command.extend(["--profile", profile])
    return command


def _run(command: list[str], *, env: dict[str, str] | None = None) -> int:
    return subprocess.run(command, env=env).returncode


def _ask_local_embedding() -> bool:
    if not sys.stdin.isatty():
        return False
    answer = input("Start local embedding container? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def _resolve_local_embedding(args: argparse.Namespace) -> bool:
    if args.local_embedding_model:
        if args.local_embedding is False:
            raise SystemExit("--local-embedding-model cannot be used with --no-local-embedding")
        return True
    if args.local_embedding is not None:
        return args.local_embedding
    return _ask_local_embedding()


def _print_local_embedding_model_menu() -> None:
    print("Choose local embedding model")
    for index, (_, label, model_id, note) in enumerate(LOCAL_EMBEDDING_MODEL_CHOICES, start=1):
        print(f"{index}) {label} ({model_id}) - {note}")


def _normalize_local_embedding_model_choice(choice: str) -> str:
    value = choice.strip()
    normalized = value.lower()
    if normalized.isdigit():
        index = int(normalized)
        if 1 <= index <= len(LOCAL_EMBEDDING_MODEL_CHOICES):
            return LOCAL_EMBEDDING_MODEL_CHOICES[index - 1][2]

    for key, label, model_id, _ in LOCAL_EMBEDDING_MODEL_CHOICES:
        if normalized in {key, label.lower(), model_id.lower()}:
            return model_id
    return value


def _ask_local_embedding_model() -> str | None:
    if not sys.stdin.isatty():
        return None
    _print_local_embedding_model_menu()
    answer = input("Select local embedding model [1: all-MiniLM-L6-v2]: ").strip()
    if not answer:
        return None
    return _normalize_local_embedding_model_choice(answer)


def _resolve_local_embedding_model(args: argparse.Namespace, local_embedding: bool) -> str | None:
    if not local_embedding:
        return None
    if args.local_embedding_model:
        return _normalize_local_embedding_model_choice(args.local_embedding_model)
    return _ask_local_embedding_model()


def _vector_db_help() -> str:
    names = ", ".join(choice[0] for choice in VECTOR_DB_CHOICES)
    return f"Vector DB backend. Choices: {names}."


def _print_vector_db_menu() -> None:
    print("Choose Vector DB")
    for index, (_, label, _) in enumerate(VECTOR_DB_CHOICES, start=1):
        print(f"{index}) {label}")


def _normalize_vector_db_choice(choice: str) -> str:
    value = choice.strip().lower()
    if value.isdigit():
        index = int(value)
        if 1 <= index <= len(VECTOR_DB_CHOICES):
            return VECTOR_DB_CHOICES[index - 1][0]
    for key, label, _ in VECTOR_DB_CHOICES:
        if value in {key, label.lower()}:
            return key
    valid_numbers = f"1-{len(VECTOR_DB_CHOICES)}"
    raise SystemExit(f"Unknown Vector DB '{choice}'. Use a number ({valid_numbers}) or a name.")


def _ensure_supported_vector_db(vector_db: str) -> str:
    for key, _, _ in VECTOR_DB_CHOICES:
        if key == vector_db:
            return key
    raise SystemExit(f"Unknown Vector DB '{vector_db}'.")


def _ask_vector_db() -> str:
    if not sys.stdin.isatty():
        return DEFAULT_VECTOR_DB
    _print_vector_db_menu()
    answer = input("Select Vector DB [5: pgvector]: ").strip()
    if not answer:
        return DEFAULT_VECTOR_DB
    return _ensure_supported_vector_db(_normalize_vector_db_choice(answer))


def _resolve_vector_db(args: argparse.Namespace) -> str:
    if args.vector_db:
        return _ensure_supported_vector_db(_normalize_vector_db_choice(args.vector_db))
    return _ask_vector_db()


def _profiles_for_vector_db(vector_db: str) -> list[str]:
    for key, _, profiles in VECTOR_DB_CHOICES:
        if key == vector_db:
            return list(profiles)
    return []


def _validate_vector_db_environment(vector_db: str) -> None:
    if vector_db != "azure-ai-search":
        return
    missing = [
        name
        for name in ("AZURE_SEARCH_SERVICE_ENDPOINT", "AZURE_SEARCH_API_KEY")
        if not os.getenv(name)
    ]
    if missing:
        joined = ", ".join(missing)
        raise SystemExit(f"Azure AI Search requires environment variables: {joined}")


def _run_up(args: argparse.Namespace) -> int:
    vector_db = _resolve_vector_db(args)
    _validate_vector_db_environment(vector_db)
    local_embedding = _resolve_local_embedding(args)
    local_embedding_model = _resolve_local_embedding_model(args, local_embedding)
    profiles = _profiles_for_vector_db(vector_db)
    if local_embedding:
        profiles.append("local-embedding")
    command = _compose_base(args.project_dir, profiles=profiles)
    command.append("up")

    if args.build:
        command.append("--build")
    if args.detach:
        command.append("--detach")

    env = os.environ.copy()
    env["VECTOR_STORE"] = vector_db
    if local_embedding_model:
        env["LOCAL_EMBEDDING_MODEL"] = local_embedding_model

    return _run(command, env=env)


def _run_down(args: argparse.Namespace) -> int:
    command = _compose_base(args.project_dir)
    command.append("down")
    if args.volumes:
        command.append("--volumes")
    return _run(command)


def _run_status(args: argparse.Namespace) -> int:
    command = _compose_base(args.project_dir)
    command.append("ps")
    return _run(command)


def _run_logs(args: argparse.Namespace) -> int:
    command = _compose_base(args.project_dir)
    command.append("logs")
    if args.follow:
        command.append("--follow")
    command.extend(args.services)
    return _run(command)


def _truncate_text(text: str, max_chars: int) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _run_ask(args: argparse.Namespace) -> int:
    platform = GenAIPlatform(gateway_url=args.gateway_url)
    search_fn = platform.data.hybrid_search if args.hybrid else platform.data.search
    results = search_fn(args.index, query=args.question, top_k=args.top_k)

    print(f"index: {args.index}")
    print(f"query: {args.question}")
    print(f"mode: {'hybrid' if args.hybrid else 'vector'}")
    print()

    if not results:
        print("No results.")
        return 1

    for i, result in enumerate(results, start=1):
        print(f"[{i}] score={result.score:.4f} document={result.document_id}")
        if result.metadata:
            metadata = ", ".join(f"{k}={v}" for k, v in sorted(result.metadata.items()))
            print(f"metadata: {metadata}")
        print(_truncate_text(result.text, args.max_chars))
        print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axe-suite",
        description="Run the data-focused GenAI Platform Docker Compose stack.",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=_default_project_dir(),
        help="Directory containing docker-compose.yml.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    up = subparsers.add_parser("up", help="Start the platform stack.")
    detach_group = up.add_mutually_exclusive_group()
    detach_group.add_argument(
        "--detach",
        "-d",
        action="store_true",
        dest="detach",
        help="Run containers in the background. This is the default.",
    )
    detach_group.add_argument(
        "--foreground",
        action="store_false",
        dest="detach",
        help="Run containers in the current terminal.",
    )
    up.add_argument("--no-build", action="store_false", dest="build", help="Skip image builds.")
    up.add_argument(
        "--vector-db",
        help=_vector_db_help(),
    )
    embedding_group = up.add_mutually_exclusive_group()
    embedding_group.add_argument(
        "--local-embedding",
        action="store_true",
        dest="local_embedding",
        default=None,
        help="Start the optional local embedding container.",
    )
    embedding_group.add_argument(
        "--no-local-embedding",
        action="store_false",
        dest="local_embedding",
        help="Skip the local embedding prompt and start only the default stack.",
    )
    up.add_argument(
        "--local-embedding-model",
        help="Model id or researched alias for the optional local embedding container.",
    )
    up.set_defaults(func=_run_up, build=True, detach=True)

    down = subparsers.add_parser("down", help="Stop and remove the platform stack.")
    down.add_argument("--volumes", "-v", action="store_true", help="Remove named volumes too.")
    down.set_defaults(func=_run_down)

    status = subparsers.add_parser("status", help="Show container status.")
    status.set_defaults(func=_run_status)

    logs = subparsers.add_parser("logs", help="Show service logs.")
    logs.add_argument("--follow", "-f", action="store_true", help="Follow log output.")
    logs.add_argument("services", nargs="*", help="Optional service names.")
    logs.set_defaults(func=_run_logs)

    ask = subparsers.add_parser("ask", help="Ask a question against an ingested index.")
    ask.add_argument("question", help="Question to search for.")
    ask.add_argument(
        "--index",
        default=os.getenv("AXE_SUITE_INDEX", DEFAULT_INDEX_NAME),
        help="Data index to search.",
    )
    ask.add_argument(
        "--gateway-url",
        default=os.getenv("GENAI_GATEWAY_URL", "localhost:50051"),
        help="Gateway gRPC address.",
    )
    ask.add_argument("--top-k", type=int, default=3, help="Number of chunks to return.")
    ask.add_argument("--hybrid", action="store_true", help="Use hybrid search.")
    ask.add_argument("--max-chars", type=int, default=700, help="Maximum characters per result.")
    ask.set_defaults(func=_run_ask)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.project_dir = args.project_dir.resolve()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
