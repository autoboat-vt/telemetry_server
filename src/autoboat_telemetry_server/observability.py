"""
Structured logging and Prometheus metrics for the telemetry server.

See `.github/instructions/python-source.instructions.md` #"Observability" for
the rationale (why JSON, why stdlib logging, cardinality bounds, singleton
guards, how to add a metric).
"""

__all__ = ["REQUEST_LOG_FORMAT", "count_429", "count_clean_instances_deletions", "init_app", "setup_logging"]

import json
import logging
import time
import uuid
from typing import Any

from flask import Blueprint, Flask, Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

# re-exported for tests / callers that want the raw formatter string
REQUEST_LOG_FORMAT = "method=%(method)s path=%(path)s status=%(status)s duration_ms=%(duration_ms)s request_id=%(request_id)s"


# metric singletons — see python-source.instructions.md #"Metric singletons"
_http_requests_total: Counter | None = None
_http_request_duration_seconds: Histogram | None = None
_http_429_total: Counter | None = None
_clean_instances_deleted_total: Counter | None = None


class _JsonFormatter(logging.Formatter):
    """Minimal JSON formatter for structured request logs."""

    _REQUEST_FIELDS = ("method", "path", "status", "duration_ms", "request_id")

    def format(self, record: logging.LogRecord) -> str:

        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
        }

        # request records carry the structured fields via extra=; plain
        # records fall back to getMessage(); see instructions #"Structured logging"
        request_fields = {k: getattr(record, k, None) for k in self._REQUEST_FIELDS}
        if any(v is not None for v in request_fields.values()):
            payload.update({k: v for k, v in request_fields.items() if v is not None})
            if record.getMessage():
                payload["message"] = record.getMessage()
        else:
            payload["message"] = record.getMessage()

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def setup_logging(*, level: int = logging.INFO) -> None:
    """
    Configure the root logger with the JSON formatter.

    Idempotent — see instructions #"Structured logging".
    """

    root = logging.getLogger()

    if any(getattr(h, "_ats_json_handler", False) for h in root.handlers):
        root.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    handler._ats_json_handler = True  # idempotency marker
    root.addHandler(handler)
    root.setLevel(level)


def _ensure_metrics() -> None:
    """Create the Prometheus metric singletons if they don't exist yet."""

    global _http_requests_total, _http_request_duration_seconds, _http_429_total, _clean_instances_deleted_total  # noqa: PLW0603

    if _http_requests_total is None:
        _http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests by method, path rule, and status code.",
            labelnames=("method", "path", "status"),
        )
        _http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds, by method and path rule.",
            labelnames=("method", "path"),
        )
        _http_429_total = Counter("http_429_total", "HTTP 429 responses from write-lock contention.")
        _clean_instances_deleted_total = Counter(
            "clean_instances_deleted_total", "Telemetry instances deleted by the clean_instances cron route."
        )


def _path_label() -> str:
    """
    Return the Flask routing rule as a stable label, not the raw URL.

    See instructions #"Metric cardinality is bounded by design".
    """

    if request.url_rule is not None:
        return request.url_rule.rule

    return request.path


def _log_request(response: Response) -> Response:
    """Emit the structured request log record and record metrics."""

    duration_ms = (time.perf_counter() - g.request_start) * 1000.0

    logging.getLogger("autoboat_telemetry_server.request").info(
        REQUEST_LOG_FORMAT,
        extra={
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": f"{duration_ms:.3f}",
            "request_id": getattr(g, "request_id", "-"),
        },
    )

    if _http_requests_total is not None and _http_request_duration_seconds is not None:
        path_label = _path_label()
        _http_requests_total.labels(method=request.method, path=path_label, status=str(response.status_code)).inc()
        _http_request_duration_seconds.labels(method=request.method, path=path_label).observe(duration_ms / 1000.0)

    return response


def init_app(app: Flask) -> None:
    """Register structured logging, request hooks, and the /metrics endpoint."""

    _ensure_metrics()
    setup_logging()

    @app.before_request
    def _start_request_timer() -> None:
        g.request_start = time.perf_counter()
        # request_id: prefer inbound header (trace propagation), else uuid4
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex

    @app.after_request
    def _after_request(response: Response) -> Response:
        return _log_request(response)

    # /metrics endpoint — not CORS-enabled, not lock-decorated; see instructions
    metrics_bp = Blueprint(name="metrics_page", import_name=__name__)

    @metrics_bp.route("/metrics", methods=["GET"])
    def metrics() -> Response:
        """Expose Prometheus metrics in the text exposition format."""

        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    app.register_blueprint(metrics_bp)


def count_429() -> None:
    """Increment the write-lock-contention counter. No-op if metrics uninitialized."""

    if _http_429_total is not None:
        _http_429_total.inc()


def count_clean_instances_deletions(num_deleted: int) -> None:
    """Increment the clean_instances deletion counter by ``num_deleted``."""

    if _clean_instances_deleted_total is not None:
        _clean_instances_deleted_total.inc(num_deleted)
