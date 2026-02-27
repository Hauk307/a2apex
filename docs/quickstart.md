# Quick Start Guide

Get up and running with A2Apex in under 5 minutes.

## Installation

```bash
pip install a2apex
```

## Quick Validation

Validate an A2A agent card in 5 lines:

```python
from a2apex import validate

result = validate("https://your-agent.example.com/.well-known/agent.json")
print(f"Valid: {result.valid}")
print(f"Errors: {result.errors}")
print(f"Warnings: {result.warnings}")
```

## Live Testing

Run live compliance tests against your agent:

```python
from a2apex import test

results = test("https://your-agent.example.com")
print(f"Passed: {results.passed}/{results.total}")
for failure in results.failures:
    print(f"  ✗ {failure.name}: {failure.reason}")
```

## CLI Usage

### Validate an agent card

```bash
a2apex validate https://your-agent.example.com/.well-known/agent.json
```

### Run full compliance tests

```bash
a2apex test https://your-agent.example.com
```

### Output options

```bash
a2apex test https://your-agent.example.com --format json
a2apex test https://your-agent.example.com --format junit
a2apex validate https://your-agent.example.com --verbose
```

## Web UI

Try A2Apex instantly — no installation required:

👉 **[a2apex.io](https://a2apex.io)**

Paste your agent URL, get results in seconds.

## CI/CD Integration

### GitHub Actions

```yaml
name: A2A Compliance

on: [push, pull_request]

jobs:
  a2a-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install A2Apex
        run: pip install a2apex
      
      - name: Run A2A compliance tests
        run: a2apex test ${{ secrets.AGENT_URL }} --format junit --output results.xml
      
      - name: Upload test results
        uses: actions/upload-artifact@v4
        with:
          name: a2a-compliance-results
          path: results.xml
```

### GitLab CI

```yaml
a2a-compliance:
  image: python:3.11
  script:
    - pip install a2apex
    - a2apex test $AGENT_URL --format junit --output results.xml
  artifacts:
    reports:
      junit: results.xml
```

## What's Next

- [Full API Documentation](https://a2apex.io/docs)
- [A2A Protocol Reference](https://a2apex.io/docs/a2a-protocol)
- [Example Agents](https://github.com/apex-ventures/a2apex/tree/main/examples)
- [Troubleshooting Guide](https://a2apex.io/docs/troubleshooting)

## Need Help?

- 📖 [Documentation](https://a2apex.io/docs)
- 💬 [Discord Community](https://discord.gg/a2apex)
- 🐛 [Report Issues](https://github.com/apex-ventures/a2apex/issues)
