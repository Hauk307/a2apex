"""
A2Apex - The trust layer for AI agents. Test, certify, and build reputation for A2A agents.

The A2Apex SDK provides tools for testing and validating agents that implement
the A2A (Agent-to-Agent) protocol.

Quick Start:
    from a2apex import A2ApexClient

    client = A2ApexClient()

    # Validate an Agent Card
    report = client.validate_card("https://agent.example.com")
    print(f"Score: {report.score}/100")

    # Run full test suite
    results = client.test_agent("https://agent.example.com")
    for test in results:
        print(f"{'✅' if test.passed else '❌'} {test.name}: {test.message}")

Standalone Functions:
    from a2apex import validate_agent_card, validate_transitions

    # Validate just a card dict
    report = validate_agent_card({"name": "My Agent", ...})

    # Validate state transitions
    result = validate_transitions(["submitted", "working", "completed"])
"""

__version__ = "0.1.0"
__author__ = "Apex Ventures LLC"

# Main client
from .client import A2ApexClient, test_agent, validate_card

# Validator
from .validator import (
    AgentCardValidator,
    Severity,
    ValidationIssue,
    ValidationReport,
    validate_agent_card,
)

# Tester
from .tester import (
    LiveTester,
    TestReport,
    TestResult,
    TestStatus,
    test_agent_card_fetch,
    test_message_send,
)

# State machine
from .state_machine import (
    StateMachineValidator,
    TransitionValidationResult,
    TransitionViolation,
    get_valid_next_states,
    is_terminal_state,
    is_valid_state,
    validate_transition,
    validate_transitions,
)

# Models
from .models import (
    # Core types
    AgentCard,
    AgentCapabilities,
    AgentExtension,
    AgentInterface,
    AgentProvider,
    AgentSkill,
    Artifact,
    Message,
    MessageRole,
    Part,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
    FilePart,
    DataPart,
    FileWithBytes,
    FileWithUri,
    # Events
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
    # Security
    ApiKeySecurityScheme,
    HttpSecurityScheme,
    OAuth2SecurityScheme,
    OpenIdConnectSecurityScheme,
    MutualTLSSecurityScheme,
    SecurityScheme,
    # Config
    MessageSendConfiguration,
    PushNotificationConfig,
    # JSON-RPC
    JsonRpcError,
    JsonRpcRequest,
    JsonRpcResponse,
    A2AErrorCode,
    # Helpers
    create_jsonrpc_request,
    create_text_message,
    is_interrupted_state,
)

# Reports
from .report import (
    export_html_test_report,
    export_html_validation_report,
    export_json,
    export_report,
)


__all__ = [
    # Version
    "__version__",
    # Main client
    "A2ApexClient",
    "validate_card",
    "test_agent",
    # Validator
    "AgentCardValidator",
    "ValidationReport",
    "ValidationIssue",
    "Severity",
    "validate_agent_card",
    # Tester
    "LiveTester",
    "TestReport",
    "TestResult",
    "TestStatus",
    "test_agent_card_fetch",
    "test_message_send",
    # State machine
    "StateMachineValidator",
    "TransitionValidationResult",
    "TransitionViolation",
    "validate_transition",
    "validate_transitions",
    "get_valid_next_states",
    "is_terminal_state",
    "is_valid_state",
    # Models - Core
    "AgentCard",
    "AgentCapabilities",
    "AgentExtension",
    "AgentInterface",
    "AgentProvider",
    "AgentSkill",
    "Artifact",
    "Message",
    "MessageRole",
    "Part",
    "Task",
    "TaskState",
    "TaskStatus",
    "TextPart",
    "FilePart",
    "DataPart",
    "FileWithBytes",
    "FileWithUri",
    # Models - Events
    "TaskArtifactUpdateEvent",
    "TaskStatusUpdateEvent",
    # Models - Security
    "ApiKeySecurityScheme",
    "HttpSecurityScheme",
    "OAuth2SecurityScheme",
    "OpenIdConnectSecurityScheme",
    "MutualTLSSecurityScheme",
    "SecurityScheme",
    # Models - Config
    "MessageSendConfiguration",
    "PushNotificationConfig",
    # Models - JSON-RPC
    "JsonRpcError",
    "JsonRpcRequest",
    "JsonRpcResponse",
    "A2AErrorCode",
    # Models - Helpers
    "create_jsonrpc_request",
    "create_text_message",
    "is_interrupted_state",
    # Reports
    "export_json",
    "export_html_test_report",
    "export_html_validation_report",
    "export_report",
]
