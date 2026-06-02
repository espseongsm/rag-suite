import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from genai_platform import GenAIPlatform
from services.data.main import _build_gateway_embed_fn
from services.data.models import IndexConfig
from services.data.service import DataService
from services.gateway.registry import ServiceRegistry
from services.gateway.servers import create_grpc_server as create_gateway_server
from services.models.service import ModelService
from services.shared.server import create_grpc_server

LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class FakeEmbeddingHandler(BaseHTTPRequestHandler):
    """Tiny TEI-compatible /embed endpoint for SDK smoke tests."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        texts = payload.get("inputs", [])
        if isinstance(texts, str):
            texts = [texts]

        vectors = []
        for text in texts:
            seed = (sum(ord(ch) for ch in text) % 17 + 1) / 100.0
            vectors.append([seed] * 384)

        body = json.dumps(vectors).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return


def test_python_sdk_routes_through_gateway_to_data_and_models(monkeypatch):
    embedding_port = _free_port()
    models_port = _free_port()
    data_port = _free_port()
    gateway_port = _free_port()

    monkeypatch.setenv("LOCAL_EMBEDDING_URL", f"http://127.0.0.1:{embedding_port}")
    monkeypatch.setenv("LOCAL_EMBEDDING_MODELS", LOCAL_EMBEDDING_MODEL)
    monkeypatch.setenv("GENAI_GATEWAY_URL", f"127.0.0.1:{gateway_port}")
    monkeypatch.setenv("VECTOR_STORE", "memory")
    monkeypatch.setenv("DATA_WORKER_COUNT", "1")

    embedding_http = HTTPServer(("127.0.0.1", embedding_port), FakeEmbeddingHandler)
    embedding_thread = threading.Thread(target=embedding_http.serve_forever, daemon=True)
    embedding_thread.start()

    model_servicer = ModelService()
    model_server = create_grpc_server(model_servicer, port=models_port, service_name="models")
    model_server.start()

    data_servicer = DataService(embed_fn=_build_gateway_embed_fn())
    data_server = create_grpc_server(data_servicer, port=data_port, service_name="data")
    data_server.start()

    registry = ServiceRegistry()
    registry.register_platform_service("models", f"127.0.0.1:{models_port}")
    registry.register_platform_service("data", f"127.0.0.1:{data_port}")
    gateway_server = create_gateway_server(registry, port=gateway_port)
    gateway_server.start()

    platform = GenAIPlatform(gateway_url=f"127.0.0.1:{gateway_port}")

    try:
        embedding_models = platform.models.list_embedding_models()
        assert [m.name for m in embedding_models] == [LOCAL_EMBEDDING_MODEL]
        assert embedding_models[0].provider == "local"

        direct_embedding = platform.models.embed(
            ["AXE Suite smoke test"],
            model=LOCAL_EMBEDDING_MODEL,
        )
        assert direct_embedding.provider == "local"
        assert len(direct_embedding.embeddings) == 1
        assert len(direct_embedding.embeddings[0]) == 384

        index_name = "sdk-smoke-docs"
        index = platform.data.create_index(
            IndexConfig(
                name=index_name,
                embedding_model=LOCAL_EMBEDDING_MODEL,
                embedding_dimensions=384,
                chunking_strategy="fixed",
                chunk_size=120,
                chunk_overlap=10,
            ),
            owner="smoke-test",
        )
        assert index.name == index_name

        job = platform.data.ingest(
            index_name=index_name,
            filename="hello.txt",
            content=b"AXE Suite routes Python SDK calls through Gateway into Data and Model.",
            content_type="text/plain",
            metadata={"kind": "smoke"},
        )

        deadline = time.time() + 10
        while time.time() < deadline:
            job = platform.data.get_ingest_status(job.job_id)
            if job.status in {"completed", "failed"}:
                break
            time.sleep(0.1)

        assert job.status == "completed", job.error
        assert job.document_id

        docs = platform.data.list_documents(index_name)
        assert len(docs) == 1
        assert docs[0].filename == "hello.txt"

        results = platform.data.search(
            index_name=index_name,
            query="How does AXE Suite route SDK calls?",
            top_k=3,
        )
        assert results
        assert "Gateway" in results[0].text
    finally:
        data_servicer.close(timeout=2)
        for server in (gateway_server, data_server, model_server):
            server.stop(grace=0).wait(timeout=2)
        embedding_http.shutdown()
        embedding_http.server_close()
