"""gRPC proxy that routes SDK calls to Model and Data services."""

from typing import Dict, Optional

import grpc

from proto import data_pb2_grpc, models_pb2_grpc
from services.gateway.registry import ServiceRegistry


class GenericProxy:
    """Routes calls using the x-target-service request metadata."""

    def __init__(self, registry: ServiceRegistry):
        self.registry = registry
        self._stub_factories: Dict[str, callable] = {
            "models": lambda channel: models_pb2_grpc.ModelServiceStub(channel),
            "data": lambda channel: data_pb2_grpc.DataServiceStub(channel),
        }

    def _extract_target_service(self, context) -> Optional[str]:
        metadata = dict(context.invocation_metadata())
        return metadata.get("x-target-service")

    def _forward_request(self, service_name: str, stub_factory, method_name: str, request, context):
        try:
            backend_addr = self.registry.get_platform_service_address(service_name)
            channel = grpc.insecure_channel(backend_addr)
            stub = stub_factory(channel)
            method = getattr(stub, method_name)
            response = method(request)
            if hasattr(response, "__iter__") and not isinstance(response, (str, bytes)):

                def stream_with_cleanup():
                    try:
                        yield from response
                    finally:
                        channel.close()

                return stream_with_cleanup()
            channel.close()
            return response
        except grpc.RpcError as e:
            context.set_code(e.code())
            context.set_details(e.details())
            raise
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            raise


class GenericServiceProxy:
    """Generated-servicer-compatible proxy base."""

    def __init__(self, proxy: GenericProxy):
        self.proxy = proxy
        self._proxy = proxy

    def __getattribute__(self, name: str):
        if name.startswith("_") or name in ("proxy", "_proxy"):
            return super().__getattribute__(name)
        proxy = super().__getattribute__("_proxy")

        def handler(request, context):
            target_service = proxy._extract_target_service(context)
            if not target_service:
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Missing x-target-service metadata")
                return None
            stub_factory = proxy._stub_factories.get(target_service)
            if not stub_factory:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details(f"Service '{target_service}' not found")
                return None
            return proxy._forward_request(target_service, stub_factory, name, request, context)

        return handler


class ModelServiceProxy(GenericServiceProxy, models_pb2_grpc.ModelServiceServicer):
    """Proxy handler for Model Service."""

    pass


class DataServiceProxy(GenericServiceProxy, data_pb2_grpc.DataServiceServicer):
    """Proxy handler for Data Service."""

    pass
