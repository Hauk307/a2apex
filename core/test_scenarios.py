"""
A2Apex Test Scenarios

Predefined test scenarios for testing A2A agent behavior.
"""

from typing import Optional
from dataclasses import dataclass, field
from enum import Enum


class ScenarioCategory(Enum):
    """Categories of test scenarios."""
    BASIC = "basic"             # Basic connectivity and response
    CONVERSATION = "conversation"  # Multi-turn conversations
    TASK_MANAGEMENT = "task"    # Task lifecycle handling
    ERROR_HANDLING = "error"    # Error scenarios
    CONTENT_TYPES = "content"   # Different content type handling
    PERFORMANCE = "performance" # Performance and timeout tests


class ScenarioDifficulty(Enum):
    """Difficulty level of scenarios."""
    EASY = "easy"       # Should work with any compliant agent
    MEDIUM = "medium"   # Requires good implementation
    HARD = "hard"       # Edge cases and complex scenarios


@dataclass
class TestMessage:
    """A message in a test scenario."""
    text: str
    expected_behavior: str
    wait_for_completion: bool = True
    timeout_seconds: float = 30.0


@dataclass 
class TestScenario:
    """A complete test scenario."""
    id: str
    name: str
    description: str
    category: ScenarioCategory
    difficulty: ScenarioDifficulty
    messages: list[TestMessage]
    tags: list[str] = field(default_factory=list)
    requires_capabilities: list[str] = field(default_factory=list)
    expected_final_state: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "difficulty": self.difficulty.value,
            "messages": [
                {
                    "text": m.text,
                    "expected_behavior": m.expected_behavior,
                    "wait_for_completion": m.wait_for_completion,
                    "timeout_seconds": m.timeout_seconds
                }
                for m in self.messages
            ],
            "tags": self.tags,
            "requires_capabilities": self.requires_capabilities,
            "expected_final_state": self.expected_final_state
        }


# ============================================================================
# PREDEFINED TEST SCENARIOS
# ============================================================================

BASIC_SCENARIOS = [
    TestScenario(
        id="basic.hello",
        name="Hello World",
        description="Send a simple greeting and expect a response",
        category=ScenarioCategory.BASIC,
        difficulty=ScenarioDifficulty.EASY,
        messages=[
            TestMessage(
                text="Hello!",
                expected_behavior="Agent should respond with a greeting or acknowledgment"
            )
        ],
        tags=["smoke-test", "greeting"],
        expected_final_state="completed"
    ),
    TestScenario(
        id="basic.echo",
        name="Echo Test",
        description="Send a message and verify the agent can process it",
        category=ScenarioCategory.BASIC,
        difficulty=ScenarioDifficulty.EASY,
        messages=[
            TestMessage(
                text="Please repeat this: The quick brown fox jumps over the lazy dog.",
                expected_behavior="Agent should acknowledge and process the message"
            )
        ],
        tags=["smoke-test", "processing"]
    ),
    TestScenario(
        id="basic.question",
        name="Simple Question",
        description="Ask a simple factual question",
        category=ScenarioCategory.BASIC,
        difficulty=ScenarioDifficulty.EASY,
        messages=[
            TestMessage(
                text="What is 2 + 2?",
                expected_behavior="Agent should respond with an answer (ideally '4')"
            )
        ],
        tags=["smoke-test", "qa"],
        expected_final_state="completed"
    ),
    TestScenario(
        id="basic.capabilities",
        name="Capabilities Query",
        description="Ask the agent about its capabilities",
        category=ScenarioCategory.BASIC,
        difficulty=ScenarioDifficulty.EASY,
        messages=[
            TestMessage(
                text="What can you help me with?",
                expected_behavior="Agent should describe its capabilities or skills"
            )
        ],
        tags=["capabilities", "help"]
    ),
    TestScenario(
        id="basic.empty_message",
        name="Empty Message Handling",
        description="Send an empty or whitespace-only message",
        category=ScenarioCategory.BASIC,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="   ",
                expected_behavior="Agent should handle gracefully (error or prompt for input)"
            )
        ],
        tags=["edge-case", "validation"]
    ),
]

CONVERSATION_SCENARIOS = [
    TestScenario(
        id="conversation.context",
        name="Context Retention",
        description="Test if agent maintains context across messages",
        category=ScenarioCategory.CONVERSATION,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="My name is Alice.",
                expected_behavior="Agent should acknowledge"
            ),
            TestMessage(
                text="What is my name?",
                expected_behavior="Agent should remember and respond with 'Alice'"
            )
        ],
        tags=["context", "memory"]
    ),
    TestScenario(
        id="conversation.followup",
        name="Follow-up Questions",
        description="Test handling of follow-up questions",
        category=ScenarioCategory.CONVERSATION,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="Tell me about the capital of France.",
                expected_behavior="Agent should provide information about Paris"
            ),
            TestMessage(
                text="What's the population?",
                expected_behavior="Agent should understand this refers to Paris and provide population info"
            )
        ],
        tags=["context", "followup"]
    ),
    TestScenario(
        id="conversation.correction",
        name="Correction Handling",
        description="Test how agent handles corrections",
        category=ScenarioCategory.CONVERSATION,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="The capital of Australia is Sydney.",
                expected_behavior="Agent may correct this or acknowledge"
            ),
            TestMessage(
                text="Actually, I meant the capital of Australia. What is it?",
                expected_behavior="Agent should provide the correct answer (Canberra)"
            )
        ],
        tags=["correction", "factual"]
    ),
]

TASK_MANAGEMENT_SCENARIOS = [
    TestScenario(
        id="task.simple",
        name="Simple Task Completion",
        description="Send a task and verify it completes",
        category=ScenarioCategory.TASK_MANAGEMENT,
        difficulty=ScenarioDifficulty.EASY,
        messages=[
            TestMessage(
                text="What is the current date?",
                expected_behavior="Task should complete with a response",
                wait_for_completion=True
            )
        ],
        tags=["task", "completion"],
        expected_final_state="completed"
    ),
    TestScenario(
        id="task.long_running",
        name="Long Running Task",
        description="Test a task that may take longer to complete",
        category=ScenarioCategory.TASK_MANAGEMENT,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="Write a short story about a robot learning to paint.",
                expected_behavior="Task should transition through working state to completed",
                wait_for_completion=True,
                timeout_seconds=60.0
            )
        ],
        tags=["task", "long-running"],
        expected_final_state="completed"
    ),
    TestScenario(
        id="task.input_required",
        name="Input Required State",
        description="Test if agent properly requests additional input",
        category=ScenarioCategory.TASK_MANAGEMENT,
        difficulty=ScenarioDifficulty.HARD,
        messages=[
            TestMessage(
                text="Help me plan a trip.",
                expected_behavior="Agent may request more details (destination, dates, etc.)"
            ),
            TestMessage(
                text="I want to go to Paris for a week in June.",
                expected_behavior="Agent should use the additional info to continue"
            )
        ],
        tags=["task", "input-required", "multi-turn"]
    ),
]

ERROR_HANDLING_SCENARIOS = [
    TestScenario(
        id="error.invalid_request",
        name="Invalid Request Handling",
        description="Test how agent handles malformed or invalid requests",
        category=ScenarioCategory.ERROR_HANDLING,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="@#$%^&*()!~`",
                expected_behavior="Agent should handle gracefully without crashing"
            )
        ],
        tags=["error", "validation", "edge-case"]
    ),
    TestScenario(
        id="error.unsupported",
        name="Unsupported Request",
        description="Request something clearly outside agent's capabilities",
        category=ScenarioCategory.ERROR_HANDLING,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="Please transfer $1000 from my bank account.",
                expected_behavior="Agent should decline or explain it cannot perform this action"
            )
        ],
        tags=["error", "capability-boundary"]
    ),
    TestScenario(
        id="error.very_long",
        name="Very Long Message",
        description="Send a very long message to test input limits",
        category=ScenarioCategory.ERROR_HANDLING,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="Test message " * 1000,  # 12000+ characters
                expected_behavior="Agent should handle or return appropriate error"
            )
        ],
        tags=["error", "limits", "edge-case"]
    ),
]

CONTENT_TYPE_SCENARIOS = [
    TestScenario(
        id="content.json_request",
        name="JSON Data Request",
        description="Request structured JSON data",
        category=ScenarioCategory.CONTENT_TYPES,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="Give me a JSON object with the fields 'name' and 'age' for a person named Bob who is 30.",
                expected_behavior="Agent should return structured JSON data"
            )
        ],
        tags=["content", "json"],
        requires_capabilities=[]
    ),
    TestScenario(
        id="content.markdown",
        name="Markdown Formatting",
        description="Request formatted markdown content",
        category=ScenarioCategory.CONTENT_TYPES,
        difficulty=ScenarioDifficulty.MEDIUM,
        messages=[
            TestMessage(
                text="Create a markdown document with a header, bullet list, and code block showing how to print 'hello' in Python.",
                expected_behavior="Agent should return properly formatted markdown"
            )
        ],
        tags=["content", "markdown", "formatting"]
    ),
]

PERFORMANCE_SCENARIOS = [
    TestScenario(
        id="perf.quick_response",
        name="Quick Response Time",
        description="Test agent response time for simple queries",
        category=ScenarioCategory.PERFORMANCE,
        difficulty=ScenarioDifficulty.EASY,
        messages=[
            TestMessage(
                text="Hi",
                expected_behavior="Agent should respond within 5 seconds",
                timeout_seconds=5.0
            )
        ],
        tags=["performance", "latency"]
    ),
    TestScenario(
        id="perf.concurrent",
        name="Concurrent Requests",
        description="Test handling of multiple concurrent requests",
        category=ScenarioCategory.PERFORMANCE,
        difficulty=ScenarioDifficulty.HARD,
        messages=[
            TestMessage(
                text="Count from 1 to 5.",
                expected_behavior="Each request should complete independently"
            )
        ],
        tags=["performance", "concurrency"]
    ),
]


# Collect all scenarios
ALL_SCENARIOS = (
    BASIC_SCENARIOS +
    CONVERSATION_SCENARIOS +
    TASK_MANAGEMENT_SCENARIOS +
    ERROR_HANDLING_SCENARIOS +
    CONTENT_TYPE_SCENARIOS +
    PERFORMANCE_SCENARIOS
)

# Index scenarios by ID
SCENARIOS_BY_ID = {s.id: s for s in ALL_SCENARIOS}

# Index scenarios by category
SCENARIOS_BY_CATEGORY = {}
for scenario in ALL_SCENARIOS:
    cat = scenario.category.value
    if cat not in SCENARIOS_BY_CATEGORY:
        SCENARIOS_BY_CATEGORY[cat] = []
    SCENARIOS_BY_CATEGORY[cat].append(scenario)


def get_scenario(scenario_id: str) -> Optional[TestScenario]:
    """Get a scenario by ID."""
    return SCENARIOS_BY_ID.get(scenario_id)


def get_scenarios_by_category(category: str) -> list[TestScenario]:
    """Get all scenarios in a category."""
    return SCENARIOS_BY_CATEGORY.get(category, [])


def get_scenarios_by_difficulty(difficulty: str) -> list[TestScenario]:
    """Get all scenarios of a given difficulty."""
    return [s for s in ALL_SCENARIOS if s.difficulty.value == difficulty]


def get_scenarios_by_tag(tag: str) -> list[TestScenario]:
    """Get all scenarios with a given tag."""
    return [s for s in ALL_SCENARIOS if tag in s.tags]


def list_all_scenarios() -> list[dict]:
    """List all available scenarios."""
    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "category": s.category.value,
            "difficulty": s.difficulty.value,
            "tags": s.tags
        }
        for s in ALL_SCENARIOS
    ]


def get_quick_test_scenarios() -> list[TestScenario]:
    """Get a quick set of scenarios for basic validation."""
    quick_ids = [
        "basic.hello",
        "basic.question",
        "task.simple",
        "error.invalid_request"
    ]
    return [s for s in ALL_SCENARIOS if s.id in quick_ids]


def get_comprehensive_test_scenarios() -> list[TestScenario]:
    """Get a comprehensive set of scenarios for thorough testing."""
    return [s for s in ALL_SCENARIOS if s.difficulty != ScenarioDifficulty.HARD]
