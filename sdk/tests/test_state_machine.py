"""Tests for the state machine validator."""

import pytest

from a2apex import (
    validate_transition,
    validate_transitions,
    get_valid_next_states,
    is_terminal_state,
    is_valid_state,
    StateMachineValidator,
    TaskState,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLE TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════════


class TestSingleTransitions:
    def test_submitted_to_working(self):
        assert validate_transition("submitted", "working") is True

    def test_submitted_to_rejected(self):
        assert validate_transition("submitted", "rejected") is True

    def test_submitted_to_failed(self):
        assert validate_transition("submitted", "failed") is True

    def test_working_to_completed(self):
        assert validate_transition("working", "completed") is True

    def test_working_to_failed(self):
        assert validate_transition("working", "failed") is True

    def test_working_to_canceled(self):
        assert validate_transition("working", "canceled") is True

    def test_working_to_input_required(self):
        assert validate_transition("working", "input-required") is True

    def test_working_to_auth_required(self):
        assert validate_transition("working", "auth-required") is True

    def test_input_required_to_working(self):
        assert validate_transition("input-required", "working") is True

    def test_auth_required_to_working(self):
        assert validate_transition("auth-required", "working") is True

    def test_same_state_is_valid(self):
        """Staying in the same state is allowed (no-op)."""
        assert validate_transition("working", "working") is True
        assert validate_transition("submitted", "submitted") is True


# ═══════════════════════════════════════════════════════════════════════════════
# INVALID TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════════


class TestInvalidTransitions:
    def test_completed_to_working(self):
        """Can't go from terminal state to working."""
        assert validate_transition("completed", "working") is False

    def test_completed_to_submitted(self):
        assert validate_transition("completed", "submitted") is False

    def test_failed_to_working(self):
        assert validate_transition("failed", "working") is False

    def test_canceled_to_working(self):
        assert validate_transition("canceled", "working") is False

    def test_rejected_to_working(self):
        assert validate_transition("rejected", "working") is False

    def test_submitted_to_completed(self):
        """Can't skip working and go directly to completed."""
        assert validate_transition("submitted", "completed") is False

    def test_submitted_to_input_required(self):
        """Can't go to input-required without going through working."""
        assert validate_transition("submitted", "input-required") is False

    def test_working_to_submitted(self):
        """Can't go backwards to submitted."""
        assert validate_transition("working", "submitted") is False

    def test_working_to_rejected(self):
        """Rejected is only reachable from submitted."""
        assert validate_transition("working", "rejected") is False


# ═══════════════════════════════════════════════════════════════════════════════
# TERMINAL STATES
# ═══════════════════════════════════════════════════════════════════════════════


class TestTerminalStates:
    def test_completed_is_terminal(self):
        assert is_terminal_state("completed") is True

    def test_failed_is_terminal(self):
        assert is_terminal_state("failed") is True

    def test_canceled_is_terminal(self):
        assert is_terminal_state("canceled") is True

    def test_rejected_is_terminal(self):
        assert is_terminal_state("rejected") is True

    def test_working_not_terminal(self):
        assert is_terminal_state("working") is False

    def test_submitted_not_terminal(self):
        assert is_terminal_state("submitted") is False

    def test_input_required_not_terminal(self):
        assert is_terminal_state("input-required") is False

    def test_auth_required_not_terminal(self):
        assert is_terminal_state("auth-required") is False

    def test_terminal_has_no_next_states(self):
        """Terminal states should have no valid next states."""
        assert get_valid_next_states("completed") == []
        assert get_valid_next_states("failed") == []
        assert get_valid_next_states("canceled") == []
        assert get_valid_next_states("rejected") == []


# ═══════════════════════════════════════════════════════════════════════════════
# VALID NEXT STATES
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetValidNextStates:
    def test_from_submitted(self):
        nexts = get_valid_next_states("submitted")
        assert "working" in nexts
        assert "rejected" in nexts
        assert "failed" in nexts
        assert "completed" not in nexts

    def test_from_working(self):
        nexts = get_valid_next_states("working")
        assert "completed" in nexts
        assert "failed" in nexts
        assert "canceled" in nexts
        assert "input-required" in nexts
        assert "auth-required" in nexts
        assert "submitted" not in nexts
        assert "rejected" not in nexts

    def test_from_input_required(self):
        nexts = get_valid_next_states("input-required")
        assert "working" in nexts
        assert "canceled" in nexts
        assert "failed" in nexts
        assert "completed" not in nexts

    def test_from_auth_required(self):
        nexts = get_valid_next_states("auth-required")
        assert "working" in nexts
        assert "canceled" in nexts
        assert "failed" in nexts

    def test_invalid_state(self):
        """Invalid state should return empty list."""
        assert get_valid_next_states("not-a-state") == []


# ═══════════════════════════════════════════════════════════════════════════════
# STATE VALIDITY
# ═══════════════════════════════════════════════════════════════════════════════


class TestIsValidState:
    def test_all_valid_states(self):
        valid = [
            "submitted",
            "working",
            "input-required",
            "auth-required",
            "completed",
            "failed",
            "canceled",
            "rejected",
        ]
        for s in valid:
            assert is_valid_state(s) is True

    def test_invalid_states(self):
        invalid = [
            "pending",
            "running",
            "done",
            "error",
            "in_progress",
            "",
            "COMPLETED",  # Case sensitive
        ]
        for s in invalid:
            assert is_valid_state(s) is False


# ═══════════════════════════════════════════════════════════════════════════════
# SEQUENCE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestSequenceValidation:
    def test_valid_simple_sequence(self):
        """Simple happy path."""
        result = validate_transitions(["submitted", "working", "completed"])
        assert result.is_valid
        assert len(result.violations) == 0
        assert result.reached_terminal is True
        assert result.final_state == "completed"

    def test_valid_with_input_required(self):
        """Multi-turn conversation path."""
        result = validate_transitions([
            "submitted",
            "working",
            "input-required",
            "working",
            "completed",
        ])
        assert result.is_valid
        assert result.reached_terminal is True

    def test_valid_with_auth_required(self):
        """Auth flow path."""
        result = validate_transitions([
            "submitted",
            "working",
            "auth-required",
            "working",
            "completed",
        ])
        assert result.is_valid

    def test_valid_failed_path(self):
        """Failure path."""
        result = validate_transitions(["submitted", "working", "failed"])
        assert result.is_valid
        assert result.final_state == "failed"

    def test_valid_rejected_path(self):
        """Immediate rejection."""
        result = validate_transitions(["submitted", "rejected"])
        assert result.is_valid
        assert result.final_state == "rejected"

    def test_valid_canceled_path(self):
        """Cancellation during work."""
        result = validate_transitions(["submitted", "working", "canceled"])
        assert result.is_valid
        assert result.final_state == "canceled"

    def test_valid_multiple_loops(self):
        """Multiple input-required loops."""
        result = validate_transitions([
            "submitted",
            "working",
            "input-required",
            "working",
            "input-required",
            "working",
            "completed",
        ])
        assert result.is_valid


class TestInvalidSequences:
    def test_invalid_from_terminal(self):
        """Can't continue from terminal state."""
        result = validate_transitions([
            "submitted",
            "working",
            "completed",
            "working",  # Invalid!
        ])
        assert not result.is_valid
        assert len(result.violations) == 1
        assert result.violations[0].from_state == "completed"

    def test_invalid_skip_working(self):
        """Can't skip working."""
        result = validate_transitions(["submitted", "completed"])
        assert not result.is_valid

    def test_invalid_state_in_sequence(self):
        """Invalid state name in sequence."""
        result = validate_transitions(["submitted", "working", "done"])  # "done" invalid
        assert not result.is_valid
        assert any("done" in v.to_state for v in result.violations)

    def test_empty_sequence(self):
        """Empty sequence is invalid."""
        result = validate_transitions([])
        assert not result.is_valid

    def test_wrong_start_state(self):
        """Starting in wrong state should be flagged."""
        result = validate_transitions(["completed"])
        assert not result.is_valid

    def test_multiple_violations(self):
        """Multiple invalid transitions."""
        result = validate_transitions([
            "submitted",
            "completed",  # Invalid: skip working
            "working",  # Invalid: from terminal
        ])
        assert not result.is_valid
        assert len(result.violations) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# RESULT OBJECT
# ═══════════════════════════════════════════════════════════════════════════════


class TestResultObject:
    def test_to_dict(self):
        result = validate_transitions(["submitted", "working", "completed"])
        d = result.to_dict()
        assert "is_valid" in d
        assert "violations" in d
        assert "states_seen" in d
        assert "final_state" in d
        assert "reached_terminal" in d
        assert d["is_valid"] is True

    def test_violation_details(self):
        result = validate_transitions(["submitted", "completed"])  # Invalid
        assert len(result.violations) > 0
        v = result.violations[0]
        assert v.from_state == "submitted"
        assert v.to_state == "completed"
        assert v.reason is not None
        assert v.spec_reference is not None

    def test_states_seen(self):
        result = validate_transitions(["submitted", "working", "completed"])
        assert result.states_seen == ["submitted", "working", "completed"]


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATOR CLASS
# ═══════════════════════════════════════════════════════════════════════════════


class TestValidatorClass:
    def test_parse_state(self):
        validator = StateMachineValidator()
        assert validator.parse_state("working") == TaskState.WORKING
        assert validator.parse_state("invalid") is None

    def test_validate_transition_method(self):
        validator = StateMachineValidator()
        valid, error = validator.validate_transition("submitted", "working")
        assert valid is True
        assert error is None

        valid, error = validator.validate_transition("completed", "working")
        assert valid is False
        assert error is not None
        assert "terminal" in error.lower()

    def test_reusable(self):
        """Validator should be reusable."""
        validator = StateMachineValidator()

        r1 = validator.validate_transitions(["submitted", "working"])
        r2 = validator.validate_transitions(["submitted", "rejected"])

        assert r1.is_valid
        assert r2.is_valid
        assert r1.final_state == "working"
        assert r2.final_state == "rejected"
