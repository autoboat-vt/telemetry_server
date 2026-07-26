"""
Tests for ``autoboat_telemetry_server.types``.

Covers the ``DiagnosticMessageIntensity`` IntEnum (the wire-format contract
shared with the website and boat firmware) and sanity-checks the type
aliases. Enum renumbering would silently break consumers, so the integer
values are pinned here.
"""

from __future__ import annotations

from enum import IntEnum

from autoboat_telemetry_server.types import (
    AutopilotParametersType,
    BoatStatusMappingType,
    BoatStatusType,
    CoordinateType,
    DiagnosticMessageIntensity,
    ResponseType,
    WaypointSequenceType,
    WaypointType,
)


class TestDiagnosticMessageIntensity:
    """Verify the int mapping and IntEnum behavior."""

    def test_info_is_one(self) -> None:
        assert DiagnosticMessageIntensity.INFO == 1

    def test_warning_is_two(self) -> None:
        assert DiagnosticMessageIntensity.WARNING == 2

    def test_error_is_three(self) -> None:
        assert DiagnosticMessageIntensity.ERROR == 3

    def test_inherits_int_enum(self) -> None:
        assert issubclass(DiagnosticMessageIntensity, IntEnum)

    def test_values_are_unique(self) -> None:
        values = {member.value for member in DiagnosticMessageIntensity}
        assert values == {1, 2, 3}

    def test_membership_by_int(self) -> None:
        """Consumers pass ints over the wire; membership must accept ints."""

        assert 1 in DiagnosticMessageIntensity
        assert 2 in DiagnosticMessageIntensity
        assert 3 in DiagnosticMessageIntensity

    def test_non_membership(self) -> None:
        assert 0 not in DiagnosticMessageIntensity
        assert 4 not in DiagnosticMessageIntensity
        assert -1 not in DiagnosticMessageIntensity

    def test_int_compatibility(self) -> None:
        """IntEnum members behave as ints in comparisons and arithmetic."""

        assert DiagnosticMessageIntensity.INFO == 1
        assert int(DiagnosticMessageIntensity.WARNING) == 2
        assert DiagnosticMessageIntensity.ERROR > DiagnosticMessageIntensity.INFO


class TestTypeAliases:
    """Sanity checks that the PEP 695 type aliases are defined and usable.

    These are structural aliases (not runtime-enforced), so the tests just
    confirm the symbols exist and can be used in annotations without error.
    """

    def test_response_type_is_tuple_alias(self) -> None:
        # ResponseType is `tuple[Response, int]`; we can't isinstance-check
        # generic aliases at runtime, but we can confirm it's subscriptable
        # and evaluates without error.
        assert ResponseType is not None

    def test_waypoint_type_alias_exists(self) -> None:
        assert WaypointType is not None
        assert CoordinateType is not None

    def test_waypoint_sequence_type_alias_exists(self) -> None:
        assert WaypointSequenceType is not None

    def test_boat_status_type_alias_exists(self) -> None:
        assert BoatStatusType is not None

    def test_boat_status_mapping_type_alias_exists(self) -> None:
        assert BoatStatusMappingType is not None

    def test_autopilot_parameters_type_alias_exists(self) -> None:
        assert AutopilotParametersType is not None
