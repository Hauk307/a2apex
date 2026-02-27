<!-- Logo placeholder -->
<p align="center">
  <img src="docs/assets/logo.png" alt="A2Apex Logo" width="200">
</p>

<h1 align="center">A2Apex</h1>

<p align="center">
  <strong>Postman for AI Agents — Test A2A protocol compliance</strong>
</p>

<p align="center">
  <a href="https://github.com/apex-ventures/a2apex/actions"><img src="https://img.shields.io/github/actions/workflow/status/apex-ventures/a2apex/ci.yml?branch=main" alt="Build Status"></a>
  <a href="https://pypi.org/project/a2apex/"><img src="https://img.shields.io/pypi/v/a2apex" alt="PyPI Version"></a>
  <a href="https://github.com/apex-ventures/a2apex/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License"></a>
  <a href="https://a2apex.io"><img src="https://img.shields.io/badge/demo-a2apex.io-brightgreen" alt="Live Demo"></a>
</p>

<p align="center">
  <a href="https://a2apex.io">Website</a> •
  <a href="https://a2apex.io/docs">Documentation</a> •
  <a href="#quick-start">Quick Start</a> •
  <a href="#features">Features</a>
</p>

---

<!-- Screenshot placeholder -->
<p align="center">
  <img src="docs/assets/screenshot.png" alt="A2Apex Screenshot" width="800">
</p>

---

## What is A2Apex?

A2Apex is the first testing and validation tool for [Google's A2A (Agent-to-Agent) protocol](https://google.github.io/A2A/). 

A2A is the emerging standard for how AI agents communicate — agent cards, capability discovery, task execution, streaming responses. A2Apex helps you verify your agent implements it correctly.

**No more guessing. No more manual debugging. Paste a URL, get results.**

## Quick Start

```bash
# Install
pip install a2apex

# Validate an agent card
a2apex validate https://your-agent.example.com/.well-known/agent.json

# Run full compliance tests
a2apex test https://your-agent.example.com
```

Or try it instantly at **[a2apex.io](https://a2apex.io)** — no installation required.

## Features

- **🔍 Agent Card Validation** — Schema compliance, required fields, URL validation
- **⚡ Live Protocol Testing** — Real handshakes against your agent endpoint
- **🛠️ CLI Tool** — `a2apex validate` and `a2apex test` for any workflow
- **📦 Python SDK** — Programmatic access for custom integrations
- **🔄 CI/CD Ready** — GitHub Actions, GitLab CI, any pipeline
- **📊 Detailed Reports** — JSON, JUnit, human-readable output formats
- **🌐 Web UI** — Zero-install browser-based testing

## Installation

### PyPI (Recommended)

```bash
pip install a2apex
```

### From Source

```bash
git clone https://github.com/apex-ventures/a2apex.git
cd a2apex
pip install -e .
```

## Usage

### CLI

```bash
# Validate agent card
a2apex validate https://example.com/.well-known/agent.json

# Run compliance tests
a2apex test https://example.com

# Output as JSON
a2apex test https://example.com --format json

# Output as JUnit (for CI)
a2apex test https://example.com --format junit --output results.xml
```

### Python SDK

```python
from a2apex import validate, test

# Validate an agent card
result = validate("https://example.com/.well-known/agent.json")
print(f"Valid: {result.valid}")
print(f"Errors: {result.errors}")

# Run full compliance tests
results = test("https://example.com")
for test_result in results:
    status = "✓" if test_result.passed else "✗"
    print(f"{status} {test_result.name}")
```

### Web UI

Visit **[a2apex.io](https://a2apex.io)** and paste your agent URL.

## Architecture

```
a2apex/
├── a2apex/              # Python package
│   ├── cli/             # CLI commands
│   ├── core/            # Validation engine
│   ├── sdk/             # Public SDK interface
│   └── tests/           # Test suites
├── api/                 # FastAPI backend
├── web/                 # Vanilla JS frontend
├── docs/                # Documentation
└── examples/            # Example agents and configs
```

## CI/CD Integration

### GitHub Actions

```yaml
- name: A2A Compliance Test
  run: |
    pip install a2apex
    a2apex test ${{ secrets.AGENT_URL }} --format junit --output results.xml
```

See [full CI/CD guide](https://a2apex.io/docs/ci-cd) for more examples.

## Roadmap

- [x] **Phase 1:** Web testing tool
- [ ] **Phase 2:** CLI + SDK (public release)
- [ ] **Phase 3:** Trust & certification layer

## Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) before submitting a PR.

```bash
# Setup dev environment
git clone https://github.com/apex-ventures/a2apex.git
cd a2apex
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .
```

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

## Links

- 🌐 **Website:** [a2apex.io](https://a2apex.io)
- 📖 **Documentation:** [a2apex.io/docs](https://a2apex.io/docs)
- 🐛 **Issues:** [GitHub Issues](https://github.com/apex-ventures/a2apex/issues)
- 💬 **Discord:** [Join Community](https://discord.gg/a2apex)
- 🐦 **Twitter:** [@a2apex_io](https://twitter.com/a2apex_io)

---

<p align="center">
  Built by <a href="https://apexventures.io">Apex Ventures LLC</a>
</p>
