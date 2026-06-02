"""Gateway entry point for the data-focused platform."""

import os

from services.gateway.registry import ServiceRegistry
from services.gateway.servers import create_grpc_server


def main():
    """Run the gRPC Gateway."""
    registry = ServiceRegistry()
    registry.register_platform_service(
        "models", os.getenv("MODELS_SERVICE_ADDR", "localhost:50053")
    )
    registry.register_platform_service("data", os.getenv("DATA_SERVICE_ADDR", "localhost:50054"))

    grpc_port = int(os.getenv("GATEWAY_PORT", "50051"))
    grpc_server = create_grpc_server(registry, grpc_port)
    grpc_server.start()
    print(f"Gateway gRPC server started on port {grpc_port}")
    print("Routes: x-target-service=models | x-target-service=data")
    try:
        grpc_server.wait_for_termination()
    except KeyboardInterrupt:
        print("\nStopping gateway...")
        grpc_server.stop(0)


if __name__ == "__main__":
    main()
