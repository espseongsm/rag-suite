"""Gateway gRPC server factory."""

from concurrent import futures

import grpc

from proto import data_pb2_grpc, models_pb2_grpc
from services.gateway.grpc_proxy import DataServiceProxy, GenericProxy, ModelServiceProxy
from services.gateway.registry import ServiceRegistry


def create_grpc_server(registry: ServiceRegistry, port: int = 50051):
    """Create the gRPC gateway for Model and Data services."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    proxy = GenericProxy(registry)

    models_pb2_grpc.add_ModelServiceServicer_to_server(ModelServiceProxy(proxy), server)
    data_pb2_grpc.add_DataServiceServicer_to_server(DataServiceProxy(proxy), server)

    server.add_insecure_port(f"[::]:{port}")
    return server
