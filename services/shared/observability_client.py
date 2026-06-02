"""No-op observability client kept for ModelService tracing hooks."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional

from services.shared.traced_service import StatusCode


@dataclass
class _SpanRecord:
    trace_id: str
    span_id: str
    parent_span_id: str = ""
    service: str = ""
    operation: str = ""
    start_time_ns: int = 0
    end_time_ns: Optional[int] = None
    status: str = StatusCode.OK.value
    error_message: str = ""


@dataclass
class _GenerationRecord:
    span: _SpanRecord
    model: str
    provider: str = ""
    requested_model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def span_id(self) -> str:
        return self.span.span_id

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)


class ObservabilityClient:
    """No-op client with the same surface ModelService expects."""

    def __init__(self, *args, service_name: str = "", **kwargs) -> None:
        self.service_name = service_name

    @classmethod
    def null(cls) -> "ObservabilityClient":
        return cls()

    def start_span(
        self,
        *,
        trace_id: str,
        parent_span_id: Optional[str],
        service: str,
        operation: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> _SpanRecord:
        return _SpanRecord(
            trace_id=trace_id,
            span_id=uuid.uuid4().hex,
            parent_span_id=parent_span_id or "",
            service=service,
            operation=operation,
            start_time_ns=time.time_ns(),
        )

    def end_span(
        self,
        span_id: str,
        *,
        status: StatusCode = StatusCode.OK,
        error_message: str = "",
        attributes: Optional[Dict[str, Any]] = None,
        numeric_attributes: Optional[Dict[str, float]] = None,
    ) -> None:
        return None

    def start_generation(
        self,
        *,
        trace_id: str,
        parent_span_id: Optional[str],
        service: str,
        model: str,
        **attributes: Any,
    ) -> _GenerationRecord:
        span = self.start_span(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            service=service,
            operation=f"{service}.generation",
        )
        generation = _GenerationRecord(span=span, model=model)
        generation.update(**attributes)
        return generation

    def end_generation(
        self,
        span_id: str,
        *,
        status: StatusCode = StatusCode.OK,
        error_message: str = "",
        **attributes: Any,
    ) -> None:
        return None

    def log(self, **kwargs: Any) -> None:
        return None

    def record_counter(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        return None

    def record_histogram(
        self,
        name: str,
        value: float,
        labels: Optional[Dict[str, str]] = None,
    ) -> None:
        return None

    def flush_all(self) -> None:
        return None
