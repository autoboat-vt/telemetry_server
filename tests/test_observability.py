"""Tests for ``autoboat_telemetry_server.observability`` — see instructions #"Observability"."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient

if TYPE_CHECKING:
    from prometheus_client import Counter

# pull the module-level metric singletons so tests can read their values
# directly via ``.collect()`` without parsing the /metrics text output
from autoboat_telemetry_server import observability


def _counter_value(metric: Counter, labels: dict[str, str]) -> float:
    """Read the current value of a labeled counter.

    Parameters
    ----------
    metric
        A prometheus_client Counter (or the module-level singleton wrapper).
    labels
        The label set to look up.

    Returns
    -------
    float
        The current counter value for those labels, or 0.0 if the label set
        has never been incremented (prometheus_client raises KeyError on
        untouched label sets, so we catch that).
    """

    try:
        return metric.labels(**labels)._value.get()  # type: ignore[attr-defined]
    except KeyError:
        return 0.0


def _counter_total(metric: Counter) -> float:
    """Read the total (unlabeled) value of a counter with no labels."""

    return metric._value.get()  # type: ignore[attr-defined]


class TestMetricsEndpoint:
    """The ``/metrics`` route is registered and serves Prometheus format."""

    def test_metrics_route_exists(self, client: FlaskClient) -> None:
        """GET /metrics returns 200."""

        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_content_type(self, client: FlaskClient) -> None:
        """The response is served with the Prometheus text exposition content type."""

        response = client.get("/metrics")
        assert response.content_type.startswith("text/plain")
        # the full content type includes a version parameter:
        # text/plain; version=0.0.4; charset=utf-8
        assert "version=" in response.content_type

    def test_metrics_body_contains_process_metrics(self, client: FlaskClient) -> None:
        """prometheus_client's default REGISTRY includes process metrics."""

        response = client.get("/metrics")
        body = response.get_data(as_text=True)
        # python_gc_objects_collected_total is one of the standard process
        # metrics prometheus_client exposes for free
        assert "python_gc_objects_collected_total" in body

    def test_metrics_body_contains_http_requests_total(self, client: FlaskClient) -> None:
        """The http_requests_total counter is exposed in the /metrics body."""

        # hit any route once to make sure the counter has at least one sample
        client.get("/")
        response = client.get("/metrics")
        body = response.get_data(as_text=True)
        assert "http_requests_total" in body


class TestHttpRequestsTotal:
    """``http_requests_total`` counts requests by method, path rule, status."""

    def test_increments_on_request(self, client: FlaskClient) -> None:
        """A GET to / increments the counter for (GET, /, 200)."""

        before = _counter_value(observability._http_requests_total, {"method": "GET", "path": "/", "status": "200"})
        client.get("/")
        after = _counter_value(observability._http_requests_total, {"method": "GET", "path": "/", "status": "200"})
        assert after == before + 1.0

    def test_counts_404s(self, client: FlaskClient) -> None:
        """A request to an unknown path increments the 404 counter."""

        before = _counter_value(
            observability._http_requests_total, {"method": "GET", "path": "/nonexistent-path", "status": "404"}
        )
        client.get("/nonexistent-path")
        after = _counter_value(
            observability._http_requests_total, {"method": "GET", "path": "/nonexistent-path", "status": "404"}
        )
        assert after == before + 1.0

    def test_path_label_is_rule_not_url(self, client: FlaskClient) -> None:
        """The path label uses the Flask rule, not the raw URL with instance_id.

        This keeps cardinality bounded: requests to /boat_status/get/1 and
        /boat_status/get/2 both hit the same label set.
        """

        # create an instance so the route exists; use the instance_manager
        # create endpoint (GET) then clean up
        create_response = client.get("/instance_manager/create")
        assert create_response.status_code == 200
        instance_id = create_response.get_json()

        try:
            client.get(f"/boat_status/get/{instance_id}")
            # the label should be the rule with <int:instance_id>, NOT the
            # raw path with the actual ID
            label_value = _counter_value(
                observability._http_requests_total,
                {"method": "GET", "path": "/boat_status/get/<int:instance_id>", "status": "200"},
            )
            assert label_value >= 1.0
        finally:
            client.delete(f"/instance_manager/delete/{instance_id}")


class TestHttp429Counter:
    """``http_429_total`` increments when write-lock contention rejects a request.

    The reader-writer lock is non-blocking for writers: if a write can't be
    acquired immediately, the decorator returns 429 without running the
    handler. We simulate contention by holding the write lock from another
    thread while issuing a write request.
    """

    def test_429_increments_counter(self, client: FlaskClient) -> None:
        """A rejected write increments the http_429_total counter."""

        from autoboat_telemetry_server import shared_lock_manager

        before = _counter_total(observability._http_429_total)

        # hold the write lock so the next write attempt can't acquire it
        assert shared_lock_manager._rw_lock.acquire_write(blocking=False)
        try:
            # any write-locked route will do; /instance_manager/delete_all is
            # a DELETE that requires the write lock
            response = client.delete("/instance_manager/delete_all")
            assert response.status_code == 429
        finally:
            shared_lock_manager._rw_lock.release_write()

        after = _counter_total(observability._http_429_total)
        assert after == before + 1.0


class TestCleanInstancesCounter:
    """``clean_instances_deleted_total`` counts cron-driven instance deletions."""

    def test_increments_on_clean(self, app: Flask, client: FlaskClient) -> None:
        """Deleting 2 inactive instances increments the counter by 2."""

        from datetime import UTC, datetime, timedelta

        from autoboat_telemetry_server.models import TelemetryTable, db

        # create two instances and backdate their updated_at past the 5-min
        # clean threshold so they'll be picked up by clean_instances
        cutoff = datetime.now(UTC) - timedelta(minutes=10)
        old1 = TelemetryTable(
            default_autopilot_parameters={}, autopilot_parameters={}, boat_status={}, waypoints=[], boat_status_mapping=[]
        )
        old2 = TelemetryTable(
            default_autopilot_parameters={}, autopilot_parameters={}, boat_status={}, waypoints=[], boat_status_mapping=[]
        )
        db.session.add_all([old1, old2])
        db.session.commit()
        # backdate updated_at after insert so the column default doesn't
        # clobber our value; same pattern as test_routes.py TestInstanceManagerCleanInstances
        old1.updated_at = cutoff
        old2.updated_at = cutoff
        db.session.commit()
        db.session.expunge_all()

        before = _counter_total(observability._clean_instances_deleted_total)

        response = client.delete("/instance_manager/clean_instances")
        assert response.status_code == 200

        after = _counter_total(observability._clean_instances_deleted_total)
        assert after == before + 2.0

    def test_does_not_increment_on_error(self, app: Flask, client: FlaskClient) -> None:
        """If clean_instances fails, the counter must not increment.

        We force a failure by dropping the instances table mid-request. The
        route's catch-all ``except Exception`` returns 500 and the counter
        increment (which happens after the commit) is skipped.
        """

        from autoboat_telemetry_server.models import db

        before = _counter_total(observability._clean_instances_deleted_total)

        # drop the telemetry table so the query inside clean_instances raises
        with app.app_context():
            db.drop_all()
        response = client.delete("/instance_manager/clean_instances")
        assert response.status_code == 500

        # recreate for the fixture teardown
        with app.app_context():
            db.create_all()

        after = _counter_total(observability._clean_instances_deleted_total)
        assert after == before


class TestStructuredLogging:
    """The JSON request logger emits one structured record per request."""

    @staticmethod
    def _capture_request_records() -> tuple[list[logging.LogRecord], logging.Handler]:
        """Install a handler on the request logger to capture records.

        We use a dedicated handler instead of pytest's ``caplog`` because
        ``caplog``'s handler lives on the root logger and races with
        ``setup_logging()`` (called by ``create_app()`` in the ``app``
        fixture), which can reconfigure root-logger handlers between tests.
        Attaching directly to the ``autoboat_telemetry_server.request``
        logger avoids that fragility.
        """

        records: list[logging.LogRecord] = []

        class _CaptureHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        request_logger = logging.getLogger("autoboat_telemetry_server.request")
        # a prior test (or pytest's logging plugin) may have set
        # ``disabled=True`` on this logger; clear it so our handler receives
        # records — see AGENTS.md #"Observability testing" for the saga
        request_logger.disabled = False
        handler = _CaptureHandler(level=logging.INFO)
        request_logger.addHandler(handler)
        request_logger.setLevel(logging.INFO)
        return records, handler

    def test_log_record_contains_required_fields(self, client: FlaskClient) -> None:
        """A GET to / produces a JSON log record with method, path, status, duration, request_id."""

        records, handler = self._capture_request_records()
        try:
            client.get("/")
        finally:
            logging.getLogger("autoboat_telemetry_server.request").removeHandler(handler)

        request_records = [r for r in records if r.name == "autoboat_telemetry_server.request"]
        assert len(request_records) >= 1, f"expected at least 1 request log record, got {len(request_records)}"
        record = request_records[-1]
        assert record.method == "GET"
        assert record.path == "/"
        assert record.status == 200
        assert hasattr(record, "duration_ms")
        assert hasattr(record, "request_id")
        # request_id is a 32-char hex string (uuid4().hex) when no header is sent
        assert isinstance(record.request_id, str)
        assert len(record.request_id) >= 8

    def test_log_record_respects_request_id_header(self, client: FlaskClient) -> None:
        """An inbound X-Request-Id header is used as the request_id."""

        custom_id = "my-trace-id-12345"
        records, handler = self._capture_request_records()
        try:
            client.get("/", headers={"X-Request-Id": custom_id})
        finally:
            logging.getLogger("autoboat_telemetry_server.request").removeHandler(handler)

        request_records = [r for r in records if r.name == "autoboat_telemetry_server.request"]
        assert request_records[-1].request_id == custom_id

    def test_json_formatter_emits_valid_json(self) -> None:
        """The _JsonFormatter produces valid JSON for a request record."""

        formatter = observability._JsonFormatter()
        record = logging.LogRecord(
            name="autoboat_telemetry_server.request",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg=observability.REQUEST_LOG_FORMAT,
            args=(),
            exc_info=None,
        )
        record.method = "GET"
        record.path = "/"
        record.status = 200
        record.duration_ms = "1.234"
        record.request_id = "abc123"

        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["method"] == "GET"
        assert parsed["path"] == "/"
        assert parsed["status"] == 200
        assert parsed["duration_ms"] == "1.234"
        assert parsed["request_id"] == "abc123"
        assert "ts" in parsed
        assert parsed["level"] == "INFO"

    def test_json_formatter_handles_non_request_records(self) -> None:
        """A plain log message (no request fields) is emitted with a message field."""

        formatter = observability._JsonFormatter()
        record = logging.LogRecord(
            name="some.logger",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="something went wrong: %s",
            args=("detail",),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "something went wrong: detail"
        assert parsed["level"] == "ERROR"
        # no request fields should be present
        assert "method" not in parsed
        assert "path" not in parsed


class TestSetupLogging:
    """``setup_logging`` installs the JSON handler idempotently."""

    def test_idempotent(self) -> None:
        """Calling setup_logging twice does not install a second handler."""

        root = logging.getLogger()
        # strip any existing _ats_json_handler so we start from a clean slate;
        # create_app() calls setup_logging() during fixture setup, so without
        # this the handler would already be present and the count check below
        # would be meaningless
        for h in list(root.handlers):
            if getattr(h, "_ats_json_handler", False):
                root.removeHandler(h)
        before = len(root.handlers)

        observability.setup_logging()
        observability.setup_logging()

        after = len(root.handlers)
        assert after == before + 1, "setup_logging installed more than one handler"

    def test_sets_level(self) -> None:
        """setup_logging sets the root logger level."""

        observability.setup_logging(level=logging.DEBUG)
        assert logging.getLogger().level == logging.DEBUG

        # restore to INFO for other tests
        observability.setup_logging(level=logging.INFO)

    def test_handler_has_marker(self) -> None:
        """The installed handler is tagged with our marker attribute."""

        observability.setup_logging()
        root = logging.getLogger()
        assert any(getattr(h, "_ats_json_handler", False) for h in root.handlers)


class TestMetricSingularity:
    """Metric objects are module-level singletons (no duplicate registration)."""

    def test_init_app_twice_does_not_raise(self, tmp_instance_dir: Path) -> None:
        """Calling init_app multiple times (across create_app calls) is safe.

        prometheus_client's default REGISTRY raises ValueError if a metric
        name is registered twice. init_app must guard against this because
        create_app is called per-test (and could be called multiple times in
        scripts).
        """

        import autoboat_telemetry_server as ats

        # create_app calls observability.init_app internally; calling
        # create_app twice exercises the singleton guard
        original = ats.INSTANCE_DIR
        ats.INSTANCE_DIR = tmp_instance_dir
        try:
            app1 = ats.create_app()
            app2 = ats.create_app()
            assert app1 is not app2
        finally:
            ats.INSTANCE_DIR = original
