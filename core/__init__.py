"""
A2Apex Core Module

Core functionality for A2A protocol testing and validation.
"""

from .agent_card_validator import (
    AgentCardValidator,
    AgentCardValidationReport,
    ValidationResult,
    ValidationSeverity,
    fetch_and_validate_agent_card
)

from .task_tester import (
    TaskTester,
    TaskTestReport,
    TestResult,
    TaskState,
    run_task_test
)

from .protocol_checker import (
    ProtocolChecker,
    ComplianceReport,
    ComplianceCheck,
    CheckCategory,
    CheckStatus,
    run_compliance_check
)

from .test_scenarios import (
    TestScenario,
    TestMessage,
    ScenarioCategory,
    ScenarioDifficulty,
    ALL_SCENARIOS,
    get_scenario,
    get_scenarios_by_category,
    get_scenarios_by_difficulty,
    get_scenarios_by_tag,
    list_all_scenarios,
    get_quick_test_scenarios,
    get_comprehensive_test_scenarios
)

from .state_machine import (
    StateMachineValidator,
    StateValidationResult,
    TransitionViolation,
    TaskState as StateMachineTaskState,
    TERMINAL_STATES,
    IN_PROGRESS_STATES,
    INTERRUPTED_STATES,
    VALID_TRANSITIONS,
    validate_transition,
    validate_task_history,
    get_valid_next_states,
    is_terminal_state,
    get_state_machine_diagram
)

from .live_tester import (
    LiveTester,
    LiveTestReport,
    LiveTestResult,
    TestStatus,
    run_live_tests,
    test_agent_card,
    test_message_send
)

from .auth_tester import (
    AuthTester,
    AuthTestReport,
    AuthTestResult,
    AuthTestStatus,
    run_auth_tests
)

from .error_tester import (
    ErrorTester,
    ErrorTestReport,
    ErrorTestResult,
    ErrorTestStatus,
    run_error_tests,
    JSONRPC_ERRORS,
    A2A_ERRORS
)

from .streaming_tester import (
    StreamingTester,
    StreamTestReport,
    StreamTestResult,
    StreamTestStatus,
    run_streaming_tests
)

from .perf_tester import (
    PerfTester,
    PerfTestReport,
    PerfTestResult,
    PerfTestStatus,
    run_perf_tests
)

__all__ = [
    # Validator
    "AgentCardValidator",
    "AgentCardValidationReport", 
    "ValidationResult",
    "ValidationSeverity",
    "fetch_and_validate_agent_card",
    
    # Task Tester
    "TaskTester",
    "TaskTestReport",
    "TestResult",
    "TaskState",
    "run_task_test",
    
    # Protocol Checker
    "ProtocolChecker",
    "ComplianceReport",
    "ComplianceCheck",
    "CheckCategory",
    "CheckStatus",
    "run_compliance_check",
    
    # Test Scenarios
    "TestScenario",
    "TestMessage",
    "ScenarioCategory",
    "ScenarioDifficulty",
    "ALL_SCENARIOS",
    "get_scenario",
    "get_scenarios_by_category",
    "get_scenarios_by_difficulty",
    "get_scenarios_by_tag",
    "list_all_scenarios",
    "get_quick_test_scenarios",
    "get_comprehensive_test_scenarios",
    
    # State Machine
    "StateMachineValidator",
    "StateValidationResult",
    "TransitionViolation",
    "StateMachineTaskState",
    "TERMINAL_STATES",
    "IN_PROGRESS_STATES",
    "INTERRUPTED_STATES",
    "VALID_TRANSITIONS",
    "validate_transition",
    "validate_task_history",
    "get_valid_next_states",
    "is_terminal_state",
    "get_state_machine_diagram",
    
    # Live Tester
    "LiveTester",
    "LiveTestReport",
    "LiveTestResult",
    "TestStatus",
    "run_live_tests",
    "test_agent_card",
    "test_message_send",
    
    # Auth Tester
    "AuthTester",
    "AuthTestReport",
    "AuthTestResult",
    "AuthTestStatus",
    "run_auth_tests",
    
    # Error Tester
    "ErrorTester",
    "ErrorTestReport",
    "ErrorTestResult",
    "ErrorTestStatus",
    "run_error_tests",
    "JSONRPC_ERRORS",
    "A2A_ERRORS",
    
    # Streaming Tester
    "StreamingTester",
    "StreamTestReport",
    "StreamTestResult",
    "StreamTestStatus",
    "run_streaming_tests",
    
    # Performance Tester
    "PerfTester",
    "PerfTestReport",
    "PerfTestResult",
    "PerfTestStatus",
    "run_perf_tests"
]
