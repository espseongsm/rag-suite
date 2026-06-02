"""Data Service entry point."""

import os
from typing import Callable, List, Optional

import grpc

from proto import models_pb2, models_pb2_grpc
from services.data.service import DataService
from services.shared.server import create_grpc_server, get_service_port, run_service


def _build_gateway_embed_fn() -> Optional[Callable[[List[str], str], List[List[float]]]]:
    """Return an embedding callable that routes through the Gateway to Model Service."""
    gateway_url = os.getenv("GENAI_GATEWAY_URL")
    if not gateway_url:
        return None

    channel = grpc.insecure_channel(gateway_url)
    stub = models_pb2_grpc.ModelServiceStub(channel)
    metadata = (("x-target-service", "models"),)

    def _embed(texts: List[str], model: str) -> List[List[float]]:
        response = stub.Embed(
            models_pb2.EmbedRequest(texts=texts, model=model),
            metadata=metadata,
        )
        return [list(embedding.values) for embedding in response.embeddings]

    return _embed


def main():
    """Run the Data Service server."""
    service_name = "data"
    port = get_service_port(service_name)

    servicer = DataService(embed_fn=_build_gateway_embed_fn())
    server = create_grpc_server(servicer=servicer, port=port, service_name=service_name)

    run_service(server, service_name, port)


if __name__ == "__main__":
    main()
