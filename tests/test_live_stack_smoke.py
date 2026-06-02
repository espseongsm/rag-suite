from types import SimpleNamespace

import pytest

from examples import live_stack_smoke


class FakePlatform:
    def __init__(self, embedding_models):
        self.models = SimpleNamespace(list_embedding_models=lambda: embedding_models)


def embedding_model(name, provider):
    return SimpleNamespace(name=name, provider=provider)


def test_resolve_embedding_config_prefers_local_model():
    platform = FakePlatform(
        [
            embedding_model("text-embedding-3-small", "openai"),
            embedding_model("BAAI/bge-m3", "local"),
        ]
    )

    model, dimensions, available = live_stack_smoke.resolve_embedding_config(
        platform=platform,
        embedding_model=None,
        embedding_dimensions=None,
    )

    assert model == "BAAI/bge-m3"
    assert dimensions == 1024
    assert len(available) == 2


def test_resolve_embedding_config_uses_explicit_available_model():
    platform = FakePlatform([embedding_model("Qwen/Qwen3-Embedding-0.6B", "local")])

    model, dimensions, _ = live_stack_smoke.resolve_embedding_config(
        platform=platform,
        embedding_model="Qwen/Qwen3-Embedding-0.6B",
        embedding_dimensions=None,
    )

    assert model == "Qwen/Qwen3-Embedding-0.6B"
    assert dimensions == 1024


def test_resolve_embedding_config_rejects_unavailable_explicit_model():
    platform = FakePlatform([embedding_model("Qwen/Qwen3-Embedding-0.6B", "local")])

    with pytest.raises(RuntimeError, match="not available"):
        live_stack_smoke.resolve_embedding_config(
            platform=platform,
            embedding_model="sentence-transformers/all-MiniLM-L6-v2",
            embedding_dimensions=None,
        )


def test_resolve_embedding_config_requires_dimensions_for_unknown_model():
    platform = FakePlatform([embedding_model("custom/model", "local")])

    with pytest.raises(RuntimeError, match="Unknown embedding dimensions"):
        live_stack_smoke.resolve_embedding_config(
            platform=platform,
            embedding_model=None,
            embedding_dimensions=None,
        )


def test_resolve_embedding_config_accepts_unknown_model_with_dimensions():
    platform = FakePlatform([embedding_model("custom/model", "local")])

    model, dimensions, _ = live_stack_smoke.resolve_embedding_config(
        platform=platform,
        embedding_model=None,
        embedding_dimensions=768,
    )

    assert model == "custom/model"
    assert dimensions == 768
