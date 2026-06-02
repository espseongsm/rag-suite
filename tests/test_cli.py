from genai_platform import cli


class Completed:
    returncode = 0


class Result:
    def __init__(self, text="hello", score=0.9, document_id="doc-1", metadata=None):
        self.text = text
        self.score = score
        self.document_id = document_id
        self.metadata = metadata or {}


def test_up_runs_default_stack_detached(monkeypatch):
    calls = []

    def fake_run(command, env=None):
        calls.append((command, env))
        return Completed()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli, "_ask_local_embedding", lambda: False)
    monkeypatch.setattr(cli, "_ask_vector_db", lambda: "pgvector")

    assert cli.main(["up"]) == 0

    command, env = calls[0]
    assert command[:2] == ["docker", "compose"]
    assert "--profile" not in command
    assert command[-3:] == ["up", "--build", "--detach"]
    assert env["VECTOR_STORE"] == "pgvector"
    assert "LOCAL_EMBEDDING_MODEL" not in env


def test_up_can_run_in_foreground(monkeypatch):
    calls = []

    def fake_run(command, env=None):
        calls.append(command)
        return Completed()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli.main(["up", "--foreground", "--no-local-embedding", "--vector-db", "pgvector"]) == 0

    assert calls[0][-2:] == ["up", "--build"]
    assert "--detach" not in calls[0]


def test_help_uses_axe_suite_name(capsys):
    try:
        cli.main(["--help"])
    except SystemExit as exc:
        assert exc.code == 0

    captured = capsys.readouterr()
    assert captured.out.startswith("usage: axe-suite")


def test_up_can_include_local_embedding_profile(monkeypatch):
    calls = []

    def fake_run(command, env=None):
        calls.append((command, env))
        return Completed()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert (
        cli.main(
            [
                "up",
                "--local-embedding-model",
                "BAAI/bge-small-en-v1.5",
                "--vector-db",
                "pgvector",
            ]
        )
        == 0
    )

    command, env = calls[0]
    assert "--profile" in command
    assert "local-embedding" in command
    assert command[-3:] == ["up", "--build", "--detach"]
    assert env["VECTOR_STORE"] == "pgvector"
    assert env["LOCAL_EMBEDDING_MODEL"] == "BAAI/bge-small-en-v1.5"


def test_up_can_include_vector_db_profile(monkeypatch):
    calls = []

    def fake_run(command, env=None):
        calls.append((command, env))
        return Completed()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli.main(["up", "--vector-db", "qdrant", "--no-local-embedding"]) == 0

    command, env = calls[0]
    assert "--profile" in command
    assert "qdrant" in command
    assert env["VECTOR_STORE"] == "qdrant"


def test_up_prompt_can_include_local_embedding_profile(monkeypatch):
    calls = []

    def fake_run(command, env=None):
        calls.append(command)
        return Completed()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.setattr(cli, "_ask_local_embedding", lambda: True)
    monkeypatch.setattr(cli, "_ask_vector_db", lambda: "pgvector")

    assert cli.main(["up"]) == 0

    assert "--profile" in calls[0]
    assert "local-embedding" in calls[0]


def test_up_rejects_azure_ai_search_without_env(monkeypatch):
    calls = []

    def fake_run(command, env=None):
        calls.append(command)
        return Completed()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    monkeypatch.delenv("AZURE_SEARCH_SERVICE_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_SEARCH_API_KEY", raising=False)

    try:
        cli.main(["up", "--vector-db", "azure-ai-search", "--no-local-embedding"])
    except SystemExit as exc:
        assert "AZURE_SEARCH_SERVICE_ENDPOINT" in str(exc)
        assert "AZURE_SEARCH_API_KEY" in str(exc)
    else:
        raise AssertionError("Expected Azure env validation to exit")

    assert calls == []


def test_vector_db_prompt_accepts_number(monkeypatch):
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda prompt: "5")

    assert cli._ask_vector_db() == "pgvector"


def test_down_can_remove_volumes(monkeypatch):
    calls = []

    def fake_run(command, env=None):
        calls.append(command)
        return Completed()

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    assert cli.main(["down", "--volumes"]) == 0

    assert calls[0][-2:] == ["down", "--volumes"]


def test_ask_searches_default_index(monkeypatch, capsys):
    calls = []

    class FakeData:
        def search(self, index, query, top_k):
            calls.append(("vector", index, query, top_k))
            return [Result(text="VectorDB 후보 중 Chroma는 local-first PoC가 단순하다.")]

    class FakePlatform:
        def __init__(self, gateway_url):
            self.gateway_url = gateway_url
            self.data = FakeData()

    monkeypatch.setattr(cli, "GenAIPlatform", FakePlatform)

    assert cli.main(["ask", "VectorDB 후보 중에 뭐가 제일 단순해?"]) == 0

    assert calls == [
        (
            "vector",
            "rag-pipeline-research-summary",
            "VectorDB 후보 중에 뭐가 제일 단순해?",
            3,
        )
    ]
    out = capsys.readouterr().out
    assert "mode: vector" in out
    assert "Chroma" in out


def test_ask_can_use_hybrid_search(monkeypatch, capsys):
    calls = []

    class FakeData:
        def hybrid_search(self, index, query, top_k):
            calls.append(("hybrid", index, query, top_k))
            return [Result(text="pgvector는 Postgres 안에서 extension으로 동작한다.")]

    class FakePlatform:
        def __init__(self, gateway_url):
            self.gateway_url = gateway_url
            self.data = FakeData()

    monkeypatch.setattr(cli, "GenAIPlatform", FakePlatform)

    assert cli.main(["ask", "pgvector는 별도 docker야?", "--hybrid", "--top-k", "1"]) == 0

    assert calls == [
        ("hybrid", "rag-pipeline-research-summary", "pgvector는 별도 docker야?", 1)
    ]
    out = capsys.readouterr().out
    assert "mode: hybrid" in out
    assert "pgvector" in out
