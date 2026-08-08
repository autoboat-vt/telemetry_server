"""End-to-end route tests via the Flask test client.

Each route is exercised through the test client to verify the HTTP contract
(status codes, response shapes, lock decorator behavior, error-code ladder).
These tests stand in for the absent formal test suite and document the
expected wire format for each endpoint.

Coverage:
- ``instance_manager``: create, delete, set_user (immutability), set_name
  (uniqueness), set_diagnostic_message (validation), get_ids, clean_instances.
- ``boat_status``: get, get_new (flag clearing), set, set_mapping (validation),
  set_fast (binary ctypes decode).
- ``waypoints``: get, get_new, set (validation).
- ``autopilot_parameters``: create_config, set_default, set, get, get_hash,
  delete_config, double-JSON encoding gotcha.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from flask.testing import FlaskClient

from autoboat_telemetry_server.models import TelemetryTable, db

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _create_instance(client: FlaskClient) -> int:
    """POST /instance_manager/create and return the new instance_id."""
    response = client.get("/instance_manager/create")
    assert response.status_code == 200, response.data
    # The route returns jsonify(instance_id), which is a JSON number.
    return int(response.get_json())


def _make_config() -> dict:
    """Return a valid autopilot config dict for create_config / set_default."""
    return {
        "speed": {"default": 1.5, "description": "cruise speed in m/s"},
        "heading": {"default": 0.0, "description": "target heading in degrees"},
    }


# --------------------------------------------------------------------------- #
# Instance manager
# --------------------------------------------------------------------------- #


class TestInstanceManagerCreate:
    def test_create_returns_id(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        assert isinstance(instance_id, int)
        assert instance_id > 0

    def test_created_instance_has_default_identifier(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.get(f"/instance_manager/get_instance_info/{instance_id}")
        assert response.status_code == 200
        data = response.get_json()
        assert data["instance_identifier"] == f"Unnamed instance #{instance_id}"
        assert data["user"] == "unknown"

    def test_get_ids_lists_created_instance(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.get("/instance_manager/get_ids")
        assert response.status_code == 200
        assert instance_id in response.get_json()

    def test_get_all_instance_info(self, client: FlaskClient) -> None:
        _create_instance(client)
        _create_instance(client)
        response = client.get("/instance_manager/get_all_instance_info")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 2
        # Pin the exact key set so a regression that re-introduces the fat
        # JSON columns (boat_status, autopilot_parameters, waypoints, etc.)
        # would fail here.
        assert set(data[0].keys()) == {
            "instance_id",
            "instance_identifier",
            "user",
            "current_config_hash",
            "created_at",
            "updated_at",
        }


class TestInstanceManagerDelete:
    def test_delete_existing(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.delete(f"/instance_manager/delete/{instance_id}")
        assert response.status_code == 200
        assert f"{instance_id}" in response.get_data(as_text=True)

    def test_delete_nonexistent_returns_404(self, client: FlaskClient) -> None:
        response = client.delete("/instance_manager/delete/9999")
        assert response.status_code == 404
        assert b"Instance not found" in response.data

    def test_delete_all(self, client: FlaskClient) -> None:
        _create_instance(client)
        _create_instance(client)
        response = client.delete("/instance_manager/delete_all")
        assert response.status_code == 200
        assert b"2" in response.data
        # Verify empty
        assert client.get("/instance_manager/get_ids").get_json() == []


class TestInstanceManagerSetUser:
    """The user field immutability invariant (Section 3.3), exercised via HTTP."""

    def test_set_user_once_succeeds(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/instance_manager/set_user/{instance_id}/alice")
        assert response.status_code == 200

    def test_set_user_twice_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        assert client.post(f"/instance_manager/set_user/{instance_id}/alice").status_code == 200
        response = client.post(f"/instance_manager/set_user/{instance_id}/bob")
        assert response.status_code == 400
        assert b"can only be set once" in response.data

    def test_set_user_on_nonexistent_returns_404(self, client: FlaskClient) -> None:
        response = client.post("/instance_manager/set_user/9999/alice")
        assert response.status_code == 404

    def test_get_user(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        client.post(f"/instance_manager/set_user/{instance_id}/alice")
        response = client.get(f"/instance_manager/get_user/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == "alice"


class TestInstanceManagerSetName:
    def test_set_name_succeeds(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/instance_manager/set_name/{instance_id}/my-boat")
        assert response.status_code == 200

    def test_get_name(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        client.post(f"/instance_manager/set_name/{instance_id}/my-boat")
        response = client.get(f"/instance_manager/get_name/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == "my-boat"

    def test_duplicate_name_returns_400(self, client: FlaskClient) -> None:
        id1 = _create_instance(client)
        id2 = _create_instance(client)
        assert client.post(f"/instance_manager/set_name/{id1}/shared").status_code == 200
        response = client.post(f"/instance_manager/set_name/{id2}/shared")
        assert response.status_code == 400
        assert b"already exists" in response.data

    def test_same_instance_can_re_set_name(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        assert client.post(f"/instance_manager/set_name/{instance_id}/name1").status_code == 200
        response = client.post(f"/instance_manager/set_name/{instance_id}/name2")
        assert response.status_code == 200

    def test_get_id_by_name(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        client.post(f"/instance_manager/set_name/{instance_id}/my-boat")
        response = client.get("/instance_manager/get_id/my-boat")
        assert response.status_code == 200
        assert response.get_json() == instance_id

    def test_get_id_by_nonexistent_name_returns_404(self, client: FlaskClient) -> None:
        response = client.get("/instance_manager/get_id/nonexistent")
        assert response.status_code == 404


class TestInstanceManagerDiagnosticMessage:
    def test_set_valid_diagnostic(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/instance_manager/set_diagnostic_message/{instance_id}", json=[2, "low battery"])
        assert response.status_code == 200

    def test_get_diagnostic(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        client.post(f"/instance_manager/set_diagnostic_message/{instance_id}", json=[1, "all good"])
        response = client.get(f"/instance_manager/get_diagnostic_message/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == [1, "all good"]

    def test_invalid_intensity_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/instance_manager/set_diagnostic_message/{instance_id}", json=[9, "bad intensity"])
        assert response.status_code == 400

    def test_non_list_body_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/instance_manager/set_diagnostic_message/{instance_id}", json="not a list")
        assert response.status_code == 400

    def test_wrong_length_list_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/instance_manager/set_diagnostic_message/{instance_id}", json=[1, "msg", "extra"])
        assert response.status_code == 400

    def test_wrong_types_returns_404(self, client: FlaskClient) -> None:
        """Type mismatches raise TypeError, which this route maps to 404 (Section 3.12)."""

        instance_id = _create_instance(client)
        response = client.post(f"/instance_manager/set_diagnostic_message/{instance_id}", json=["not-int", "msg"])
        assert response.status_code == 404

    def test_set_diagnostic_on_nonexistent_returns_404(self, client: FlaskClient) -> None:
        response = client.post("/instance_manager/set_diagnostic_message/9999", json=[1, "msg"])
        assert response.status_code == 404


class TestInstanceManagerCleanInstances:
    def test_clean_removes_old_instances(self, app: Flask, client: FlaskClient) -> None:
        instance = TelemetryTable(
            default_autopilot_parameters={}, autopilot_parameters={}, boat_status={}, waypoints=[], boat_status_mapping=[]
        )
        db.session.add(instance)
        db.session.commit()

        # Capture the id before we mutate/delete - accessing it after the
        # clean route runs would raise DetachedInstanceError.
        instance_id = instance.instance_id

        # Backdate updated_at to be older than the 5-minute cutoff.
        instance.updated_at = datetime.now(UTC) - timedelta(minutes=10)
        db.session.commit()
        db.session.expunge_all()

        response = client.delete("/instance_manager/clean_instances")
        assert response.status_code == 200
        assert b"1" in response.data

        # Verify it's gone.
        assert client.get(f"/instance_manager/get_instance_info/{instance_id}").status_code == 404

    def test_clean_keeps_recent_instances(self, app: Flask, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.delete("/instance_manager/clean_instances")
        assert response.status_code == 200
        # The just-created instance should still be there.
        assert client.get(f"/instance_manager/get_instance_info/{instance_id}").status_code == 200


# --------------------------------------------------------------------------- #
# Boat status
# --------------------------------------------------------------------------- #


class TestBoatStatus:
    def test_get_empty_status(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.get(f"/boat_status/get/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == {}

    def test_set_and_get(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        status = {"heading": 45.0, "speed": 2.5}
        response = client.post(f"/boat_status/set/{instance_id}", json=status)
        assert response.status_code == 200

        response = client.get(f"/boat_status/get/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == status

    def test_set_non_dict_returns_404(self, client: FlaskClient) -> None:
        """Non-dict body raises TypeError, which this route maps to 404 (Section 3.12)."""

        instance_id = _create_instance(client)
        response = client.post(f"/boat_status/set/{instance_id}", json=[1, 2, 3])
        assert response.status_code == 404

    def test_set_on_nonexistent_returns_404(self, client: FlaskClient) -> None:
        response = client.post("/boat_status/set/9999", json={})
        assert response.status_code == 404

    def test_get_on_nonexistent_returns_404(self, client: FlaskClient) -> None:
        response = client.get("/boat_status/get/9999")
        assert response.status_code == 404


class TestBoatStatusGetNew:
    def test_get_new_returns_empty_when_no_update(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.get(f"/boat_status/get_new/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == {}

    def test_get_new_returns_status_after_set(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        status = {"heading": 90.0}
        client.post(f"/boat_status/set/{instance_id}", json=status)

        response = client.get(f"/boat_status/get_new/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == status

    def test_get_new_clears_flag(self, client: FlaskClient) -> None:
        """A second get_new after the first returns empty (flag was cleared)."""

        instance_id = _create_instance(client)
        client.post(f"/boat_status/set/{instance_id}", json={"heading": 90.0})

        assert client.get(f"/boat_status/get_new/{instance_id}").get_json() == {"heading": 90.0}
        assert client.get(f"/boat_status/get_new/{instance_id}").get_json() == {}


class TestBoatStatusSetMapping:
    def test_set_valid_mapping(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        mapping = [["heading", "c_float"], ["speed", "c_float"]]
        response = client.post(f"/boat_status/set_mapping/{instance_id}", json=mapping)
        assert response.status_code == 200

    def test_set_mapping_invalid_field_type(self, client: FlaskClient) -> None:
        """Invalid ctypes type raises TypeError -> 404 (Section 3.12)."""

        instance_id = _create_instance(client)
        mapping = [["heading", "not_a_ctypes_type"]]
        response = client.post(f"/boat_status/set_mapping/{instance_id}", json=mapping)
        assert response.status_code == 404

    def test_set_mapping_non_list(self, client: FlaskClient) -> None:
        """Non-list body raises TypeError -> 404 (Section 3.12)."""

        instance_id = _create_instance(client)
        response = client.post(f"/boat_status/set_mapping/{instance_id}", json={"not": "a list"})
        assert response.status_code == 404

    def test_set_mapping_wrong_pair_shape(self, client: FlaskClient) -> None:
        """Wrong-shape pair raises TypeError -> 404 (Section 3.12)."""

        instance_id = _create_instance(client)
        response = client.post(f"/boat_status/set_mapping/{instance_id}", json=[["only_one_element"]])
        assert response.status_code == 404

    def test_set_mapping_on_nonexistent_returns_404(self, client: FlaskClient) -> None:
        response = client.post("/boat_status/set_mapping/9999", json=[])
        assert response.status_code == 404


class TestBoatStatusSetFast:
    """Binary fast-path: ``set_fast`` decodes a ctypes struct from raw bytes."""

    def test_set_fast_without_mapping_returns_404(self, client: FlaskClient) -> None:
        """No mapping set raises TypeError -> 404 (Section 3.12)."""

        instance_id = _create_instance(client)
        response = client.post(
            f"/boat_status/set_fast/{instance_id}", data=b"\x00\x00\x00\x00", content_type="application/octet-stream"
        )
        assert response.status_code == 404

    def test_set_fast_with_mapping_updates_status(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        # Set up a mapping with two c_floats (4 bytes each).
        client.post(f"/boat_status/set_mapping/{instance_id}", json=[["heading", "c_float"], ["speed", "c_float"]])

        # Pack two little-endian floats: heading=1.0, speed=2.0
        import struct

        payload = struct.pack("<ff", 1.0, 2.0)
        response = client.post(f"/boat_status/set_fast/{instance_id}", data=payload, content_type="application/octet-stream")
        assert response.status_code == 200

        # Verify the decoded values landed in boat_status.
        status = client.get(f"/boat_status/get/{instance_id}").get_json()
        assert status["heading"] == pytest.approx(1.0)
        assert status["speed"] == pytest.approx(2.0)

    def test_set_fast_on_nonexistent_returns_404(self, client: FlaskClient) -> None:
        response = client.post("/boat_status/set_fast/9999", data=b"\x00\x00\x00\x00", content_type="application/octet-stream")
        assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Waypoints
# --------------------------------------------------------------------------- #


class TestWaypoints:
    def test_get_empty_waypoints(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.get(f"/waypoints/get/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == []

    def test_set_and_get(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        waypoints = [[1.0, 2.0], [3.0, 4.0]]
        response = client.post(f"/waypoints/set/{instance_id}", json=waypoints)
        assert response.status_code == 200

        response = client.get(f"/waypoints/get/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == waypoints

    def test_set_non_list_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/waypoints/set/{instance_id}", json={"not": "a list"})
        assert response.status_code == 400

    def test_set_wrong_point_length_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/waypoints/set/{instance_id}", json=[[1.0, 2.0, 3.0]])
        assert response.status_code == 400

    def test_set_non_numeric_coord_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/waypoints/set/{instance_id}", json=[["a", "b"]])
        assert response.status_code == 400

    def test_set_on_nonexistent_returns_400(self, client: FlaskClient) -> None:
        """Waypoints.set maps all TypeErrors (incl. instance-not-found) to 400."""

        response = client.post("/waypoints/set/9999", json=[])
        assert response.status_code == 400

    def test_get_new_returns_waypoints_after_set(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        waypoints = [[1.0, 2.0]]
        client.post(f"/waypoints/set/{instance_id}", json=waypoints)

        response = client.get(f"/waypoints/get_new/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == waypoints

    def test_get_new_clears_flag(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        client.post(f"/waypoints/set/{instance_id}", json=[[1.0, 2.0]])

        assert client.get(f"/waypoints/get_new/{instance_id}").get_json() == [[1.0, 2.0]]
        assert client.get(f"/waypoints/get_new/{instance_id}").get_json() == {}

    def test_get_new_empty_when_no_update(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.get(f"/waypoints/get_new/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == {}


# --------------------------------------------------------------------------- #
# Autopilot parameters
# --------------------------------------------------------------------------- #


class TestAutopilotCreateConfig:
    """``create_config`` accepts a double-JSON-encoded body (Section 5 gotcha)."""

    def test_create_config_returns_hash(self, client: FlaskClient) -> None:
        config = _make_config()
        # The route does json.loads(request.json), so we send a JSON-encoded
        # string of the config.
        response = client.post("/autopilot_parameters/create_config", json=json.dumps(config))
        assert response.status_code == 200
        hash_value = response.get_json()
        assert isinstance(hash_value, str)
        assert len(hash_value) == 64

    def test_create_config_duplicate_returns_500(self, client: FlaskClient) -> None:
        """Duplicate config raises ValueError, which falls through to 500 (no ValueError clause)."""

        config = _make_config()
        client.post("/autopilot_parameters/create_config", json=json.dumps(config))
        response = client.post("/autopilot_parameters/create_config", json=json.dumps(config))
        assert response.status_code == 500
        assert b"already exists" in response.data

    def test_create_config_invalid_returns_400(self, client: FlaskClient) -> None:
        # Missing 'description' key in the inner dict.
        bad_config = {"speed": {"default": 1.0}}
        response = client.post("/autopilot_parameters/create_config", json=json.dumps(bad_config))
        assert response.status_code == 400

    def test_get_hash_exists(self, client: FlaskClient) -> None:
        config = _make_config()
        create_response = client.post("/autopilot_parameters/create_config", json=json.dumps(config))
        hash_value = create_response.get_json()

        response = client.get(f"/autopilot_parameters/get_hash_exists/{hash_value}")
        assert response.status_code == 200
        assert response.get_json() is True

    def test_get_hash_exists_false_for_missing(self, client: FlaskClient) -> None:
        response = client.get("/autopilot_parameters/get_hash_exists/" + "0" * 64)
        assert response.status_code == 200
        assert response.get_json() is False

    def test_get_all_hashes(self, client: FlaskClient) -> None:
        client.post("/autopilot_parameters/create_config", json=json.dumps(_make_config()))
        response = client.get("/autopilot_parameters/get_all_hashes")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data) == 1
        assert "config_hash" in data[0]
        # Pin the exact key set so a regression that re-introduces the `data`
        # JSON column would fail here.
        assert set(data[0].keys()) == {"config_hash", "description", "created_at"}

    def test_get_config_by_hash(self, client: FlaskClient) -> None:
        config = _make_config()
        hash_value = client.post("/autopilot_parameters/create_config", json=json.dumps(config)).get_json()

        response = client.get(f"/autopilot_parameters/get_config/{hash_value}")
        assert response.status_code == 200
        assert response.get_json() == config

    def test_delete_config(self, client: FlaskClient) -> None:
        hash_value = client.post("/autopilot_parameters/create_config", json=json.dumps(_make_config())).get_json()

        response = client.delete(f"/autopilot_parameters/delete_config/{hash_value}")
        assert response.status_code == 200

        assert client.get(f"/autopilot_parameters/get_hash_exists/{hash_value}").get_json() is False

    def test_delete_nonexistent_config_returns_404(self, client: FlaskClient) -> None:
        response = client.delete("/autopilot_parameters/delete_config/" + "0" * 64)
        assert response.status_code == 404

    def test_set_hash_description(self, client: FlaskClient) -> None:
        hash_value = client.post("/autopilot_parameters/create_config", json=json.dumps(_make_config())).get_json()

        response = client.post(f"/autopilot_parameters/set_hash_description/{hash_value}/my-description")
        assert response.status_code == 200

        desc = client.get(f"/autopilot_parameters/get_hash_description/{hash_value}").get_json()
        assert desc == "my-description"


class TestAutopilotSetDefault:
    def test_set_default_creates_hash_and_applies_defaults(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        config = _make_config()
        response = client.post(f"/autopilot_parameters/set_default/{instance_id}", json=json.dumps(config))
        assert response.status_code == 200
        hash_value = response.get_json()
        assert len(hash_value) == 64

        # The route should have reset autopilot_parameters to the defaults.
        params = client.get(f"/autopilot_parameters/get/{instance_id}").get_json()
        assert params == {"speed": 1.5, "heading": 0.0}

        # current_config_hash should match the returned hash.
        current_hash = client.get(f"/autopilot_parameters/get_hash/{instance_id}").get_json()
        assert current_hash == hash_value

    def test_set_default_on_nonexistent_returns_400(self, client: FlaskClient) -> None:
        """Instance-not-found raises TypeError -> 400 on this route (Section 3.12)."""

        response = client.post("/autopilot_parameters/set_default/9999", json=json.dumps(_make_config()))
        assert response.status_code == 400

    def test_set_default_invalid_config_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(
            f"/autopilot_parameters/set_default/{instance_id}",
            json=json.dumps({"speed": {"default": 1.0}}),  # missing description
        )
        assert response.status_code == 400

    def test_get_default(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        config = _make_config()
        client.post(f"/autopilot_parameters/set_default/{instance_id}", json=json.dumps(config))

        response = client.get(f"/autopilot_parameters/get_default/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == config


class TestAutopilotSet:
    """``set`` replaces autopilot_parameters wholesale (double-JSON encoded)."""

    def test_set_with_matching_keys_succeeds(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        config = _make_config()
        client.post(f"/autopilot_parameters/set_default/{instance_id}", json=json.dumps(config))

        new_params = {"speed": 2.0, "heading": 90.0}
        response = client.post(f"/autopilot_parameters/set/{instance_id}", json=json.dumps(new_params))
        assert response.status_code == 200

        assert client.get(f"/autopilot_parameters/get/{instance_id}").get_json() == new_params

    def test_set_with_mismatched_keys_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        config = _make_config()
        client.post(f"/autopilot_parameters/set_default/{instance_id}", json=json.dumps(config))

        # 'speed' and 'heading' are expected; 'extra' is not.
        bad_params = {"speed": 2.0, "extra": 1.0}
        response = client.post(f"/autopilot_parameters/set/{instance_id}", json=json.dumps(bad_params))
        assert response.status_code == 400
        assert b"do not match" in response.data

    def test_set_without_default_allows_any_keys(self, client: FlaskClient) -> None:
        """If no default is set, the key-matching check is skipped."""

        instance_id = _create_instance(client)
        new_params = {"anything": 1.0, "goes": 2.0}
        response = client.post(f"/autopilot_parameters/set/{instance_id}", json=json.dumps(new_params))
        assert response.status_code == 200

    def test_set_non_dict_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/autopilot_parameters/set/{instance_id}", json=json.dumps([1, 2, 3]))
        assert response.status_code == 400

    def test_get_new_returns_params_after_set(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        new_params = {"speed": 2.0}
        client.post(f"/autopilot_parameters/set/{instance_id}", json=json.dumps(new_params))

        response = client.get(f"/autopilot_parameters/get_new/{instance_id}")
        assert response.status_code == 200
        assert response.get_json() == new_params

    def test_get_new_clears_flag(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        client.post(f"/autopilot_parameters/set/{instance_id}", json=json.dumps({"speed": 2.0}))

        assert client.get(f"/autopilot_parameters/get_new/{instance_id}").get_json() == {"speed": 2.0}
        assert client.get(f"/autopilot_parameters/get_new/{instance_id}").get_json() == {}


class TestAutopilotUpdateExistingParameter:
    def test_update_existing_succeeds(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        config = _make_config()
        client.post(f"/autopilot_parameters/set_default/{instance_id}", json=json.dumps(config))

        response = client.post(f"/autopilot_parameters/update_existing_parameter/{instance_id}/speed", json=json.dumps(3.0))
        assert response.status_code == 200

        params = client.get(f"/autopilot_parameters/get/{instance_id}").get_json()
        assert params["speed"] == 3.0

    def test_update_nonexistent_key_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        config = _make_config()
        client.post(f"/autopilot_parameters/set_default/{instance_id}", json=json.dumps(config))

        response = client.post(f"/autopilot_parameters/update_existing_parameter/{instance_id}/nonexistent", json=json.dumps(1.0))
        assert response.status_code == 400
        assert b"does not exist" in response.data

    def test_update_without_default_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/autopilot_parameters/update_existing_parameter/{instance_id}/speed", json=json.dumps(1.0))
        assert response.status_code == 400
        assert b"must be set" in response.data

    def test_update_invalid_type_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        config = _make_config()
        client.post(f"/autopilot_parameters/set_default/{instance_id}", json=json.dumps(config))

        # A dict is not a valid primitive value.
        response = client.post(
            f"/autopilot_parameters/update_existing_parameter/{instance_id}/speed", json=json.dumps({"nested": "dict"})
        )
        assert response.status_code == 400


class TestAutopilotSetDefaultFromHash:
    def test_set_default_from_existing_hash(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        config = _make_config()
        hash_value = client.post("/autopilot_parameters/create_config", json=json.dumps(config)).get_json()

        response = client.post(f"/autopilot_parameters/set_default_from_hash/{instance_id}/{hash_value}")
        assert response.status_code == 200

        # The instance's current_config_hash should now point at the hash.
        assert client.get(f"/autopilot_parameters/get_hash/{instance_id}").get_json() == hash_value

    def test_set_default_from_nonexistent_hash_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/autopilot_parameters/set_default_from_hash/{instance_id}/{'0' * 64}")
        assert response.status_code == 400
        assert b"does not exist" in response.data


# --------------------------------------------------------------------------- #
# Lock-decorator behavior at the route level
# --------------------------------------------------------------------------- #


class TestRouteLocking:
    """Sanity-check that routes are lock-decorated by observing 429 behavior.

    It's hard to reliably trigger a 429 through the test client (the lock is
    held only for the duration of the request), so these tests verify the
    *positive* path: that lock-decorated routes still return correct results
    when uncontested. The 429 path is covered in test_lock_manager.py.
    """

    def test_write_route_succeeds_uncontested(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.post(f"/boat_status/set/{instance_id}", json={"x": 1})
        assert response.status_code == 200

    def test_read_route_succeeds_uncontested(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        response = client.get(f"/boat_status/get/{instance_id}")
        assert response.status_code == 200


# --------------------------------------------------------------------------- #
# Route error-code ladder (Section 3.12)
# --------------------------------------------------------------------------- #


class TestErrorCodeLadder:
    """Verify the shared exception-to-status-code convention."""

    def test_instance_not_found_returns_404(self, client: FlaskClient) -> None:
        response = client.get("/boat_status/get/9999")
        assert response.status_code == 404
        assert b"Instance not found" in response.data

    def test_input_type_error_returns_404(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        # boat_status.set maps TypeError -> 404 (Section 3.12 gotcha: this route lumps
        # instance-not-found and input-validation TypeErrors together).
        response = client.post(f"/boat_status/set/{instance_id}", json=[1, 2])
        assert response.status_code == 404

    def test_input_value_error_returns_400(self, client: FlaskClient) -> None:
        instance_id = _create_instance(client)
        # set_user immutability raises ValueError (400).
        client.post(f"/instance_manager/set_user/{instance_id}/alice")
        response = client.post(f"/instance_manager/set_user/{instance_id}/bob")
        assert response.status_code == 400
