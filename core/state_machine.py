"""
A2Apex State Machine Validator

Validates A2A task state transitions against the protocol specification.
Based on: a2a_protocol_deep_dive.md - Section 7: Task Lifecycle & State Machine

The A2A task state machine is critical for compliance - invalid transitions
indicate bugs in agent implementations.
"""

from typing import Optional
from dataclasses import dataclass, field
from enum import Enum


class TaskState(Enum):
    """All valid A2A task states."""
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    AUTH_REQUIRED = "auth-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"


# State categories
TERMINAL_STATES = frozenset({
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.CANCELED,
    TaskState.REJECTED
})

INTERRUPTED_STATES = frozenset({
    TaskState.INPUT_REQUIRED,
    TaskState.AUTH_REQUIRED
})

IN_PROGRESS_STATES = frozenset({
    TaskState.SUBMITTED,
    TaskState.WORKING
})

ALL_STATES = frozenset({
    TaskState.SUBMITTED,
    TaskState.WORKING,
    TaskState.INPUT_REQUIRED,
    TaskState.AUTH_REQUIRED,
    TaskState.COMPLETED,
    TaskState.FAILED,
    TaskState.CANCELED,
    TaskState.REJECTED
})


# ═══════════════════════════════════════════════════════════════════════════════
# VALID STATE TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════════════

# Map of valid transitions: from_state -> set of valid to_states
VALID_TRANSITIONS: dict[TaskState, frozenset[TaskState]] = {
    # From submitted: can go to working, rejected, or failed
    TaskState.SUBMITTED: frozenset({
        TaskState.WORKING,
        TaskState.REJECTED,
        TaskState.FAILED
    }),
    
    # From working: can complete, need input/auth, cancel, or fail
    TaskState.WORKING: frozenset({
        TaskState.INPUT_REQUIRED,
        TaskState.AUTH_REQUIRED,
        TaskState.COMPLETED,
        TaskState.CANCELED,
        TaskState.FAILED
    }),
    
    # From input-required: back to working, or terminal states
    TaskState.INPUT_REQUIRED: frozenset({
        TaskState.WORKING,
        TaskState.CANCELED,
        TaskState.FAILED
    }),
    
    # From auth-required: back to working, or terminal states
    TaskState.AUTH_REQUIRED: frozenset({
        TaskState.WORKING,
        TaskState.CANCELED,
        TaskState.FAILED
    }),
    
    # Terminal states: NO transitions allowed
    TaskState.COMPLETED: frozenset(),
    TaskState.FAILED: frozenset(),
    TaskState.CANCELED: frozenset(),
    TaskState.REJECTED: frozenset()
}


@dataclass
class TransitionViolation:
    """A single state transition violation."""
    from_state: str
    to_state: str
    reason: str
    index: Optional[int] = None  # Position in history if applicable
    spec_reference: str = "Section 7: Task Lifecycle & State Machine"


@dataclass
class StateValidationResult:
    """Result of state machine validation."""
    is_valid: bool
    violations: list[TransitionViolation] = field(default_factory=list)
    states_seen: list[str] = field(default_factory=list)
    final_state: Optional[str] = None
    reached_terminal: bool = False
    
    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "violations": [
                {
                    "from_state": v.from_state,
                    "to_state": v.to_state,
                    "reason": v.reason,
                    "index": v.index,
                    "spec_reference": v.spec_reference
                }
                for v in self.violations
            ],
            "states_seen": self.states_seen,
            "final_state": self.final_state,
            "reached_terminal": self.reached_terminal,
            "summary": f"{'✓ Valid' if self.is_valid else '✗ Invalid'} - {len(self.violations)} violation(s)"
        }


class StateMachineValidator:
    """
    Validates A2A task state transitions.
    
    The A2A protocol defines a strict state machine:
    - Tasks start in 'submitted'
    - Progress through 'working' (may loop with interrupted states)
    - End in a terminal state (completed, failed, canceled, rejected)
    
    Terminal states are FINAL - no transitions allowed out of them.
    """
    
    @staticmethod
    def parse_state(state_str: str) -> Optional[TaskState]:
        """Parse a state string to TaskState enum."""
        try:
            return TaskState(state_str)
        except ValueError:
            return None
    
    @staticmethod
    def is_terminal(state: str | TaskState) -> bool:
        """Check if a state is terminal."""
        if isinstance(state, str):
            state = StateMachineValidator.parse_state(state)
        return state in TERMINAL_STATES
    
    @staticmethod
    def is_valid_state(state: str) -> bool:
        """Check if a string is a valid state name."""
        return StateMachineValidator.parse_state(state) is not None
    
    @staticmethod
    def get_valid_next_states(current_state: str | TaskState) -> list[str]:
        """Get list of valid next states from current state."""
        if isinstance(current_state, str):
            state = StateMachineValidator.parse_state(current_state)
            if state is None:
                return []
        else:
            state = current_state
        
        return [s.value for s in VALID_TRANSITIONS.get(state, frozenset())]
    
    def validate_transition(
        self,
        from_state: str,
        to_state: str
    ) -> tuple[bool, Optional[str]]:
        """
        Validate a single state transition.
        
        Args:
            from_state: The current state
            to_state: The proposed next state
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Parse states
        from_enum = self.parse_state(from_state)
        to_enum = self.parse_state(to_state)
        
        # Check both states are valid
        if from_enum is None:
            return False, f"Invalid source state: '{from_state}'"
        
        if to_enum is None:
            return False, f"Invalid target state: '{to_state}'"
        
        # Same state is technically valid (no-op)
        if from_enum == to_enum:
            return True, None
        
        # Check if transition is allowed
        valid_targets = VALID_TRANSITIONS.get(from_enum, frozenset())
        
        if to_enum not in valid_targets:
            # Provide helpful error message
            if from_enum in TERMINAL_STATES:
                return False, f"Cannot transition from terminal state '{from_state}'"
            else:
                valid_list = [s.value for s in valid_targets]
                return False, f"Invalid transition: '{from_state}' → '{to_state}'. Valid targets: {valid_list}"
        
        return True, None
    
    def validate_task_history(
        self,
        states: list[str],
        require_submitted_start: bool = True
    ) -> StateValidationResult:
        """
        Validate a sequence of task state transitions.
        
        Args:
            states: List of states in chronological order
            require_submitted_start: Whether first state must be 'submitted'
            
        Returns:
            StateValidationResult with any violations found
        """
        violations = []
        
        if not states:
            return StateValidationResult(
                is_valid=False,
                violations=[TransitionViolation(
                    from_state="",
                    to_state="",
                    reason="Empty state history"
                )]
            )
        
        # Validate first state
        first_state = states[0]
        first_enum = self.parse_state(first_state)
        
        if first_enum is None:
            violations.append(TransitionViolation(
                from_state="",
                to_state=first_state,
                reason=f"Invalid initial state: '{first_state}'",
                index=0
            ))
        elif require_submitted_start and first_enum != TaskState.SUBMITTED:
            # Warn but don't fail - some agents skip submitted
            if first_enum != TaskState.WORKING:
                violations.append(TransitionViolation(
                    from_state="",
                    to_state=first_state,
                    reason=f"Task should start in 'submitted' or 'working', got '{first_state}'",
                    index=0
                ))
        
        # Validate each transition
        for i in range(1, len(states)):
            from_state = states[i - 1]
            to_state = states[i]
            
            is_valid, error = self.validate_transition(from_state, to_state)
            
            if not is_valid:
                violations.append(TransitionViolation(
                    from_state=from_state,
                    to_state=to_state,
                    reason=error or f"Invalid transition: '{from_state}' → '{to_state}'",
                    index=i
                ))
        
        # Check final state
        final_state = states[-1]
        final_enum = self.parse_state(final_state)
        reached_terminal = final_enum in TERMINAL_STATES if final_enum else False
        
        return StateValidationResult(
            is_valid=len(violations) == 0,
            violations=violations,
            states_seen=states,
            final_state=final_state,
            reached_terminal=reached_terminal
        )
    
    def visualize_state_machine(self) -> str:
        """Generate ASCII visualization of the state machine."""
        return """
A2A Task State Machine
═════════════════════════════════════════════════════════════════

                         ┌────────────────┐
                         │   submitted    │ (initial)
                         └───────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌──────────┐ ┌─────────┐ ┌────────────┐
              │ rejected │ │ working │ │   failed   │
              └──────────┘ └────┬────┘ └────────────┘
               (terminal)       │        (terminal)
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          ▼                     ▼                     ▼
    ┌─────────────┐      ┌─────────────┐      ┌─────────────┐
    │   input-    │      │   auth-     │      │  completed  │
    │  required   │      │  required   │      └─────────────┘
    └──────┬──────┘      └──────┬──────┘       (terminal)
           │                    │
           └────────┬───────────┘
                    │ (after input/auth provided)
                    ▼
              ┌─────────┐
              │ working │ ◄──── (loop back)
              └─────────┘
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐
    │ canceled │ │  failed  │ │completed │
    └──────────┘ └──────────┘ └──────────┘
     (terminal)   (terminal)   (terminal)

═════════════════════════════════════════════════════════════════
Legend:
  • (initial)    - Task starts here
  • (terminal)   - No transitions allowed out
  • working      - Main processing state
  • input-required / auth-required - Awaiting client action

Valid Transitions:
  submitted     → working, rejected, failed
  working       → input-required, auth-required, completed, canceled, failed
  input-required→ working, canceled, failed
  auth-required → working, canceled, failed
  completed     → (none - terminal)
  failed        → (none - terminal)
  canceled      → (none - terminal)
  rejected      → (none - terminal)
"""


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def validate_transition(from_state: str, to_state: str) -> bool:
    """
    Quick check if a transition is valid.
    
    Args:
        from_state: Current state string
        to_state: Target state string
        
    Returns:
        True if transition is valid, False otherwise
    """
    validator = StateMachineValidator()
    is_valid, _ = validator.validate_transition(from_state, to_state)
    return is_valid


def validate_task_history(states: list[str]) -> StateValidationResult:
    """
    Validate a complete task state history.
    
    Args:
        states: List of states in chronological order
        
    Returns:
        StateValidationResult with validation details
    """
    validator = StateMachineValidator()
    return validator.validate_task_history(states)


def get_valid_next_states(current_state: str) -> list[str]:
    """
    Get list of valid next states from current state.
    
    Args:
        current_state: Current state string
        
    Returns:
        List of valid next state strings
    """
    return StateMachineValidator.get_valid_next_states(current_state)


def is_terminal_state(state: str) -> bool:
    """Check if a state is terminal (no further transitions allowed)."""
    return StateMachineValidator.is_terminal(state)


def get_state_machine_diagram() -> str:
    """Get ASCII diagram of the A2A state machine."""
    return StateMachineValidator().visualize_state_machine()
