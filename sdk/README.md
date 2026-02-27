# A2Apex 🔬

**Test, validate, and certify A2A protocol implementations.**

A2Apex is the testing toolkit for the [A2A (Agent-to-Agent) protocol](https://github.com/a2aproject/A2A) — the open standard for AI agent interoperability. Think "Postman for AI Agents."

[![PyPI version](https://badge.fury.io/py/a2apex.svg)](https://badge.fury.io/py/a2apex)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Installation

```bash
pip install a2apex
```

For rich terminal output:
```bash
pip install a2apex[rich]
```

## Quick Start

### Validate an Agent Card

```python
from a2apex import A2ApexClient

client = A2ApexClient()

# Validate from URL (fetches /.well-known/agent-card.json)
report = client.validate_card("https://agent.example.com")

print(f"Score: {report.score}/100")
print(f"Valid: {report.is_valid}")
print(f"Errors: {report.error_count}")
print(f"Warnings: {report.warning_count}")

# Show errors
for error in report.errors:
    print(f"  ✗ {error.field}: {error.message}")
    if error.suggestion:
        print(f"    💡 {error.suggestion}")
```

### Run Full Test Suite

```python
from a2apex import A2ApexClient

client = A2ApexClient()
results = client.test_agent("https://agent.example.com")

print(f"Score: {results.score}/100")
print(f"Passed: {results.passed}/{results.total_tests}")

for test in results:
    status = "✅" if test.passed else "❌"
    print(f"{status} {test.name}: {test.message}")
```

### Validate a Dict (No HTTP)

```python
from a2apex import validate_agent_card

card = {
    "name": "My Agent",
    "url": "https://api.example.com/a2a",
    "version": "1.0.0",
    "capabilities": {"streaming": True},
    "skills": [
        {"id": "chat", "name": "Chat", "description": "General conversation"}
    ]
}

report = validate_agent_card(card)
print(report)  # ✓ Valid (Score: 75/100) — 0 errors, 5 warnings
```

### Validate State Transitions

```python
from a2apex import validate_transitions, is_terminal_state

# Check if a sequence of state transitions is valid
result = validate_transitions(["submitted", "working", "completed"])
print(f"Valid: {result.is_valid}")  # True

# Invalid transition (can't go from completed to working)
result = validate_transitions(["submitted", "working", "completed", "working"])
print(f"Valid: {result.is_valid}")  # False
for v in result.violations:
    print(f"  ✗ {v.from_state} → {v.to_state}: {v.reason}")

# Check terminal states
print(is_terminal_state("completed"))  # True
print(is_terminal_state("working"))    # False
```

## Async Support

All methods have async versions:

```python
import asyncio
from a2apex import A2ApexClient

async def main():
    client = A2ApexClient()
    
    # Async validation
    report = await client.avalidate_card("https://agent.example.com")
    
    # Async testing
    results = await client.atest_agent("https://agent.example.com")
    
    print(f"Score: {results.score}/100")

asyncio.run(main())
```

## CI/CD Integration

Perfect for automated testing:

```python
from a2apex import A2ApexClient

client = A2ApexClient()
results = client.test_agent("https://agent.example.com")

# Fail CI if compliance score too low
assert results.score >= 80, f"A2A compliance too low: {results.score}/100"

# Or check specific tests
for test in results:
    if test.name in ["agent_card_fetch", "message_send"]:
        assert test.passed, f"Critical test failed: {test.name}"
```

## Export Reports

Generate JSON or HTML reports:

```python
from a2apex import A2ApexClient, export_report

client = A2ApexClient()
results = client.test_agent("https://agent.example.com")

# Export to JSON
export_report(results, "report.json")

# Export to HTML
export_report(results, "report.html")
```

## What Gets Tested

The test suite validates:

| Test | Description |
|------|-------------|
| `agent_card_fetch` | Agent Card accessible at `/.well-known/agent-card.json` |
| `message_send` | `message/send` JSON-RPC method works |
| `task_get` | `tasks/get` returns valid task status |
| `streaming` | SSE streaming works (if capability enabled) |
| `invalid_method` | Agent returns proper error for unknown methods |
| `task_cancel` | `tasks/cancel` processes correctly |

## Pydantic Models

A2Apex includes complete Pydantic v2 models for all A2A types:

```python
from a2apex import (
    AgentCard,
    Task,
    Message,
    TextPart,
    create_text_message,
)

# Parse an Agent Card
card = AgentCard.model_validate(card_dict)
print(card.name, card.capabilities.streaming)

# Create messages
msg = create_text_message("Hello!", role="user")
```

## API Reference

### A2ApexClient

The main entry point:

```python
client = A2ApexClient(
    timeout=30.0,        # Request timeout
    auth_header=None,    # Default Authorization header
)

# Sync methods
client.validate_card(url_or_dict) → ValidationReport
client.test_agent(url) → TestReport

# Async methods
await client.avalidate_card(url_or_dict) → ValidationReport
await client.atest_agent(url) → TestReport
```

### ValidationReport

```python
report.is_valid      # bool - No errors
report.score         # float - 0-100 compliance score
report.errors        # list[ValidationIssue] - Must fix
report.warnings      # list[ValidationIssue] - Should fix
report.info          # list[ValidationIssue] - Suggestions
```

### TestReport

```python
results.score           # float - 0-100
results.passed          # int - Passed tests
results.failed          # int - Failed tests
results.warnings        # int - Tests with warnings
results.total_tests     # int - Total tests run
results.results         # list[TestResult] - All results

# Iterate over results
for test in results:
    print(test.name, test.passed, test.message)
```

## Requirements

- Python 3.10+
- httpx
- pydantic >= 2.0

## Links

- 📚 [Documentation](https://docs.a2apex.io)
- 🌐 [A2Apex.io](https://a2apex.io)
- 📋 [A2A Protocol Spec](https://github.com/a2aproject/A2A)
- 🐙 [GitHub](https://github.com/a2apex/a2apex-python)

## License

Apache 2.0 - See [LICENSE](LICENSE) for details.

---

Built with 🦊 by [Apex Ventures](https://a2apex.io)
