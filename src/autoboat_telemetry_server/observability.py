"""Structured logging and Prometheus metrics for the telemetry server."""

__all__ = [
    "REQUEST_LOG_FORMAT",
    "count_429",
    "count_clean_instances_deletions",
    "init_app",
    "observe_db_query",
    "record_boat_status_payload",
    "record_image_bytes",
    "refresh_state_gauges",
    "set_instance_count",
    "setup_logging",
]

import json
import logging
import os
import time
import uuid
from typing import Any

from flask import Blueprint, Flask, Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from sqlalchemy.sql import Select as BaseSelect

REQUEST_LOG_FORMAT = (
    "method=%(method)s path=%(path)s status=%(status)s "
    "duration_ms=%(duration_ms)s response_bytes=%(response_bytes)s request_id=%(request_id)s"
)

_http_requests_total: Counter | None = None
_http_request_duration_seconds: Histogram | None = None
_http_429_total: Counter | None = None
_clean_instances_deleted_total: Counter | None = None
_http_response_bytes_total: Counter | None = None
_http_request_bytes_total: Counter | None = None
_http_exceptions_total: Counter | None = None
_db_query_duration_seconds: Histogram | None = None
_db_queries_total: Counter | None = None
_boat_status_payload_bytes: Histogram | None = None
_images_uploaded_total: Counter | None = None
_image_bytes_received_total: Counter | None = None
_instances_total: Gauge | None = None
_config_hashes_total: Gauge | None = None
_images_stored_total: Gauge | None = None
_image_storage_bytes: Gauge | None = None
_app_info: Gauge | None = None


class _JsonFormatter(logging.Formatter):
    """
    Minimal JSON formatter for structured request logs.

    Inherits
    --------
    :class:`logging.Formatter`
    """

    _REQUEST_FIELDS = ("method", "path", "status", "duration_ms", "response_bytes", "request_id")

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record as a JSON string.

        Parameters
        ----------
        record
            The log record to format.

        Returns
        -------
        `str`
            The formatted JSON string representing the log record.
        """

        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
        }

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

    Parameters
    ----------
    level
        The logging level to set for the root logger. Default is :attr:`logging.INFO`.
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

    global _http_requests_total, _http_request_duration_seconds, _http_429_total  # noqa: PLW0603
    global _clean_instances_deleted_total, _http_response_bytes_total  # noqa: PLW0603
    global _http_request_bytes_total, _http_exceptions_total  # noqa: PLW0603
    global _db_query_duration_seconds, _db_queries_total  # noqa: PLW0603
    global _boat_status_payload_bytes, _images_uploaded_total  # noqa: PLW0603
    global _image_bytes_received_total, _instances_total  # noqa: PLW0603
    global _config_hashes_total, _images_stored_total, _image_storage_bytes  # noqa: PLW0603
    global _app_info  # noqa: PLW0603

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
        _http_response_bytes_total = Counter(
            "http_response_bytes_total",
            "Total HTTP response body bytes transferred, by method and path rule.",
            labelnames=("method", "path"),
        )

        # --- request/response payload sizes ---------------------------------
        _http_request_bytes_total = Counter(
            "http_request_bytes_total",
            "Total HTTP request body bytes received, by method and path rule.",
            labelnames=("method", "path"),
        )
        # Unhandled exceptions that reach Flask's error handler. Note that most
        # routes here catch their own exceptions and return 500, so this only
        # fires for failures outside a handler's try/except.
        _http_exceptions_total = Counter(
            "http_exceptions_total",
            "Unhandled exceptions raised while handling a request, by method and path rule.",
            labelnames=("method", "path", "exception"),
        )

        # --- database -------------------------------------------------------
        _db_queries_total = Counter(
            "db_queries_total", "Total SQL statements executed against the SQLite binds.", labelnames=("operation",)
        )
        _db_query_duration_seconds = Histogram(
            "db_query_duration_seconds",
            "SQL statement latency in seconds, by statement operation.",
            labelnames=("operation",),
            buckets=(0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
        )

        # --- domain specific -------------------------------------------------
        _boat_status_payload_bytes = Histogram(
            "boat_status_payload_bytes",
            "Size in bytes of decoded boat-status payloads, by encoding (json or binary).",
            labelnames=("encoding",),
            buckets=(64, 256, 512, 1024, 2048, 4096, 8192, 16384, 65536),
        )
        _images_uploaded_total = Counter(
            "images_uploaded_total", "Images received via image_manager/upload (including de-duplicated uploads)."
        )
        _image_bytes_received_total = Counter("image_bytes_received_total", "Total raw image payload bytes received.")

        # --- state gauges (refreshed on scrape) -----------------------------
        _instances_total = Gauge("instances_total", "Number of telemetry instances currently stored.")
        _config_hashes_total = Gauge("config_hashes_total", "Number of stored autopilot-parameter config hashes.")
        _images_stored_total = Gauge("images_stored_total", "Number of distinct images stored.")
        _image_storage_bytes = Gauge("image_storage_bytes", "Total bytes of stored image payloads.")
        _app_info = Gauge(
            "telemetry_server_info", "Static build/version information. Always 1; read the labels.", labelnames=("version",)
        )


def _path_label() -> str:
    """
    Return the Flask routing rule as a stable label, not the raw URL.

    Returns
    -------
    `str`
        The Flask routing rule (e.g., ``/boat_status/get/<int:instance_id>``) if available,
        otherwise the raw request path.
    """

    if request.url_rule is not None:
        return request.url_rule.rule

    return request.path


def _log_request(response: Response) -> Response:
    """
    Emit the structured request log record and record metrics.

    Parameters
    ----------
    response
        The Flask response object to log and record metrics for.

    Returns
    -------
    :class:`Response`
        The same Flask response object, unmodified.
    """

    duration_ms = (time.perf_counter() - g.request_start) * 1000.0
    response_bytes = len(response.get_data())

    logging.getLogger("autoboat_telemetry_server.request").info(
        REQUEST_LOG_FORMAT,
        extra={
            "method": request.method,
            "path": request.path,
            "status": response.status_code,
            "duration_ms": f"{duration_ms:.3f}",
            "response_bytes": response_bytes,
            "request_id": getattr(g, "request_id", "-"),
        },
    )

    if _http_requests_total is not None and _http_request_duration_seconds is not None:
        path_label = _path_label()
        _http_requests_total.labels(method=request.method, path=path_label, status=str(response.status_code)).inc()
        _http_request_duration_seconds.labels(method=request.method, path=path_label).observe(duration_ms / 1000.0)

    if _http_response_bytes_total is not None:
        _http_response_bytes_total.labels(method=request.method, path=_path_label()).inc(response_bytes)

    request_bytes = getattr(g, "request_bytes", None)
    if _http_request_bytes_total is not None and request_bytes is not None:
        _http_request_bytes_total.labels(method=request.method, path=_path_label()).inc(request_bytes)

    return response


def init_app(app: Flask) -> None:
    """
    Register structured logging, request hooks, and the `/metrics` endpoint.

    Parameters
    ----------
    app
        The Flask application instance to initialize observability for.
    """

    _ensure_metrics()
    setup_logging()

    @app.before_request
    def _start_request_timer() -> None:
        g.request_start = time.perf_counter()
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        # content_length is None for a bodyless request (curl -X POST with no
        # data), so default it to 0 rather than recording None
        g.request_bytes = request.content_length or 0

    @app.after_request
    def _after_request(response: Response) -> Response:
        """
        Emit the structured request log record and record metrics after each request.

        Parameters
        ----------
        response
            The Flask response object to log and record metrics for.

        Returns
        -------
        :class:`Response`
            The same Flask response object, unmodified.
        """

        return _log_request(response)

    @app.teardown_request
    def _record_exception(exc: BaseException | None) -> None:
        """
        Count exceptions that escaped a route handler.

        Parameters
        ----------
        exc
            The exception raised while handling the request, or `None`.
        """

        if exc is None or _http_exceptions_total is None:
            return

        _http_exceptions_total.labels(method=request.method, path=_path_label(), exception=type(exc).__name__).inc()

    metrics_bp = Blueprint(name="metrics_page", import_name=__name__)

    @metrics_bp.route("/metrics", methods=["GET"])
    def metrics() -> Response:
        """
        Expose Prometheus metrics in the text exposition format.

        Refresh the state gauges before rendering so each scrape reports current
        DB row counts rather than values from the last mutating request.

        Returns
        -------
        :class:`Response`
            A Flask response containing the Prometheus metrics in the text exposition format.
        """

        refresh_state_gauges()
        return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)

    app.register_blueprint(metrics_bp)

    if _app_info is not None:
        # labels are process-lifetime constants, so set once at startup
        version = os.environ.get("TELEMETRY_SERVER_VERSION", "0.0.0")
        _app_info.labels(version=version).set(1)


def count_429() -> None:
    """Increment the write-lock-contention counter. No-op if metrics uninitialized."""

    if _http_429_total is not None:
        _http_429_total.inc()


def count_clean_instances_deletions(num_deleted: int) -> None:
    """
    Increment the clean_instances deletion counter by ``num_deleted``.

    Parameters
    ----------
    num_deleted
        The number of telemetry instances deleted by the clean_instances cron route.
    """

    if _clean_instances_deleted_total is not None:
        _clean_instances_deleted_total.inc(num_deleted)


def observe_db_query(operation: str, duration_seconds: float) -> None:
    """
    Record a single SQL statement's execution.

    Called from the SQLAlchemy ``before_cursor_execute``/``after_cursor_execute``
    event hooks in :mod:`autoboat_telemetry_server.models`.

    Parameters
    ----------
    operation
        The statement verb (``SELECT``, ``INSERT``, ``UPDATE``, ``DELETE``, ...).
    duration_seconds
        How long the statement took to execute.
    """

    if _db_queries_total is not None:
        _db_queries_total.labels(operation=operation).inc()

    if _db_query_duration_seconds is not None:
        _db_query_duration_seconds.labels(operation=operation).observe(duration_seconds)


def record_boat_status_payload(*, encoding: str, size_bytes: int) -> None:
    """
    Record the size of a decoded boat-status payload.

    Parameters
    ----------
    encoding
        ``"json"`` for the regular ``/set`` route, ``"binary"`` for ``/set_fast``.
    size_bytes
        The payload size in bytes.
    """

    if _boat_status_payload_bytes is not None:
        _boat_status_payload_bytes.labels(encoding=encoding).observe(size_bytes)


def record_image_bytes(size_bytes: int) -> None:
    """
    Record one image upload and its payload size.

    Counts de-duplicated uploads too, since the interesting question is how much
    camera traffic arrives, not how many distinct rows result.

    Parameters
    ----------
    size_bytes
        The raw image payload size in bytes.
    """

    if _images_uploaded_total is not None:
        _images_uploaded_total.inc()

    if _image_bytes_received_total is not None:
        _image_bytes_received_total.inc(size_bytes)


def set_instance_count(count: int) -> None:
    """
    Set the ``instances_total`` gauge directly.

    Parameters
    ----------
    count
        The current number of telemetry instances.
    """

    if _instances_total is not None:
        _instances_total.set(count)


def refresh_state_gauges() -> None:
    """
    Re-read DB row counts into the state gauges.

    Called on every ``/metrics`` scrape. Each gauge is updated independently and
    errors are swallowed per-gauge: if one bind is unavailable, a metrics endpoint
    returning partial data is far better than a 500 from the one endpoint meant
    to report ill health.

    Note that ``ImageTable`` lives on the separate ``images`` bind, so it is
    counted in its own query rather than joined with the other tables.

    The models import is deferred to call time because :mod:`.models` imports
    this module for the DB event hooks; a top-level import would be circular.
    """

    if _instances_total is None:
        return

    from autoboat_telemetry_server.models import HashTable, ImageTable, TelemetryTable, db  # noqa: PLC0415

    def _count(stmt: BaseSelect[Any]) -> int | None:
        """Run a scalar count, returning `None` if the query fails."""

        try:
            return int(db.session.execute(stmt).scalar_one())

        except Exception:
            db.session.rollback()
            return None

    count = _count(db.select(db.func.count(TelemetryTable.instance_id)))
    if count is not None:
        _instances_total.set(count)

    if _config_hashes_total is not None:
        hashes = _count(db.select(db.func.count(HashTable.config_hash)))
        if hashes is not None:
            _config_hashes_total.set(hashes)

    if _images_stored_total is not None:
        images = _count(db.select(db.func.count(ImageTable.image_uuid)))
        if images is not None:
            _images_stored_total.set(images)

    if _image_storage_bytes is not None:
        total = _count(db.select(db.func.coalesce(db.func.sum(db.func.length(ImageTable.data)), 0)))
        if total is not None:
            _image_storage_bytes.set(total)
