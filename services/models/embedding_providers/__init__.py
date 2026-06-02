"""Embedding provider adapters."""

from .base import EmbeddingProvider
from .huggingface_provider import HuggingFaceEmbeddingProvider
from .local_provider import LocalEmbeddingProvider
from .openai_provider import OpenAIEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "HuggingFaceEmbeddingProvider",
    "LocalEmbeddingProvider",
    "OpenAIEmbeddingProvider",
]
