"""Service registry for Gateway gRPC routing."""

from typing import Dict, List


class ServiceRegistry:
    """Tracks platform service addresses by service name."""

    def __init__(self):
        self._platform_services: Dict[str, List[str]] = {}

    def register_platform_service(self, service_name: str, address: str):
        """Register a platform service address."""
        if service_name not in self._platform_services:
            self._platform_services[service_name] = []
        if address not in self._platform_services[service_name]:
            self._platform_services[service_name].append(address)
            print(f"Registered platform service '{service_name}' at {address}")

    def get_platform_service_address(self, service_name: str) -> str:
        """Get the first address for a platform service."""
        addresses = self._platform_services.get(service_name, [])
        if not addresses:
            raise ValueError(f"Platform service '{service_name}' not registered")
        return addresses[0]
