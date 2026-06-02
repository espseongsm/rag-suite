"""No-op-safe Model Service metrics publisher."""

from __future__ import annotations

from dataclasses import dataclass

from services.shared.observability_client import ObservabilityClient


class PlatformMetrics:
    MODEL_REQUEST_TOTAL = "model.request.total"
    MODEL_REQUEST_DURATION = "model.request.duration_ms"
    MODEL_COST_USD = "model.cost_usd"
    MODEL_TOKENS_PROMPT = "model.tokens.prompt"
    MODEL_TOKENS_COMPLETION = "model.tokens.completion"
    MODEL_CACHE_HITS = "model.cache_hits"
    MODEL_FALLBACKS = "model.fallbacks"


@dataclass
class ModelRequestMetrics:
    """Per-request metric data the publisher consumes."""

    provider: str
    model: str
    workflow_id: str = ""
    cache_hit: bool = False
    fallback_used: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0


class ModelServiceMetricsPublisher:
    """Publishes per-request Model Service metrics when observability is wired."""

    def __init__(self, observability: ObservabilityClient) -> None:
        self.observability = observability

    def publish(self, request_metrics: ModelRequestMetrics) -> None:
        labels = {
            "provider": request_metrics.provider or "unknown",
            "model": request_metrics.model or "unknown",
            "workflow_id": request_metrics.workflow_id or "unknown",
            "cache_hit": str(request_metrics.cache_hit),
        }
        self.observability.record_counter(PlatformMetrics.MODEL_REQUEST_TOTAL, 1.0, labels)
        self.observability.record_histogram(
            PlatformMetrics.MODEL_REQUEST_DURATION,
            request_metrics.duration_ms,
            labels,
        )
        self.observability.record_counter(
            PlatformMetrics.MODEL_COST_USD,
            request_metrics.cost_usd,
            labels,
        )
        if request_metrics.prompt_tokens:
            self.observability.record_counter(
                PlatformMetrics.MODEL_TOKENS_PROMPT,
                request_metrics.prompt_tokens,
                labels,
            )
        if request_metrics.completion_tokens:
            self.observability.record_counter(
                PlatformMetrics.MODEL_TOKENS_COMPLETION,
                request_metrics.completion_tokens,
                labels,
            )
        if request_metrics.cache_hit:
            self.observability.record_counter(PlatformMetrics.MODEL_CACHE_HITS, 1.0, labels)
        if request_metrics.fallback_used:
            self.observability.record_counter(PlatformMetrics.MODEL_FALLBACKS, 1.0, labels)
