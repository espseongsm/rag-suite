"""Main SDK entry point for the data-focused GenAI Platform."""

import os
from typing import Optional

from .clients.data import DataClient
from .clients.models import ModelClient


class GenAIPlatform:
    """Lazy SDK facade for Model and Data services."""

    def __init__(self, gateway_url: Optional[str] = None):
        self.gateway_url = gateway_url or os.getenv("GENAI_GATEWAY_URL", "localhost:50051")
        self._models = None
        self._data = None

    @property
    def models(self) -> ModelClient:
        """Access the Model Service client."""
        if self._models is None:
            self._models = ModelClient(self)
        return self._models

    @property
    def data(self) -> DataClient:
        """Access the Data Service client."""
        if self._data is None:
            self._data = DataClient(self)
        return self._data
