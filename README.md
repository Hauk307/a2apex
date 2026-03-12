<p align="center">
  <img src="brand/a2apex-mark-256.png" alt="A2Apex" width="128">
</p>

<h1 align="center">A2Apex</h1>

<p align="center">
  <strong>The trust layer for AI agents. Test, certify, and discover A2A protocol agents.</strong>
</p>

<p align="center">
  <a href="https://a2apex.io"><img src="https://img.shields.io/badge/live-a2apex.io-00e5a0" alt="Live"></a>
  <a href="https://app.a2apex.io"><img src="https://img.shields.io/badge/app-app.a2apex.io-blue" alt="App"></a>
  <a href="https://github.com/Hauk307/a2apex/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-Apache%202.0-blue" alt="License"></a>
</p>

<p align="center">
  <a href="https://a2apex.io">Website</a> · 
  <a href="https://app.a2apex.io/api/docs">API Docs</a> · 
  <a href="#quick-start">Quick Start</a> · 
  <a href="#features">Features</a>
</p>

---

## What is A2Apex?

A2Apex is a testing, certification, and discovery platform for AI agents built on [Google's A2A (Agent-to-Agent) protocol](https://github.com/google/A2A).

Think of it as **SSL Labs** (testing) + **npm** (directory) + **LinkedIn** (profiles) for AI agents.

- **Test** — Point it at any A2A agent URL. 50+ automated compliance checks run against the spec: agent card validation, live endpoint testing, state machine verification, streaming, auth, error handling.
- **Certify** — Agents earn a 0-100 trust score with Gold, Silver, or Bronze certification badges you can embed in your README or docs.
- **Discover** — Every tested agent gets a public profile in the Agent Directory with trust scores, skills, test history, and embeddable badges.

Try it free at **[app.a2apex.io](https://app.a2apex.io)**

## Quick Start

### Web (no install)

Go to [app.a2apex.io](https://app.a2apex.io), paste an agent URL, and hit Test.

### Python SDK

```bash
pip install a2apex
```

```python
from a2apex import A2Apex

client = A2Apex(api_key="your_key")

# Validate an agent card
result = client.validate("https://your-agent.example.com")
print(f"Score: {result.score}/100")
print(f"Level: {result.certification_level}")

# Run full compliance test suite
report = client.test("https://your-agent.example.com")
for check in report.checks:
    status = "✓" if check.passed else "✗"
    print(f"  {status} {check.name}")
```

## Features

| Feature | Description |
|---------|-------------|
| **Agent Card Validator** | Schema compliance, required fields, URL validation, capability checks |
| **Live Endpoint Testing** | Real protocol handshakes against your running agent |
| **State Machine Validation** | Verify correct task lifecycle transitions |
| **Streaming Tests** | SSE streaming response compliance |
| **Auth Testing** | API key, Bearer token, OAuth2 flow validation |
| **Error Handling** | Graceful failure and edge case coverage |
| **Trust Scores** | 0-100 weighted score across all test categories |
| **Certification Badges** | Embeddable Gold/Silver/Bronze SVG badges |
| **Agent Profiles** | Public profile pages with history and capabilities |
| **Agent Directory** | Searchable directory of tested agents |
| **Performance Testing** | Response time and throughput benchmarks |
| **Demo Mode** | Try the full test suite without a real agent |

## Architecture

```
a2apex/
├── api/                 # FastAPI backend (REST API, auth, payments, profiles)
├── core/                # Testing engine
│   ├── agent_card_validator.py
│   ├── live_tester.py
│   ├── state_machine_tester.py
│   ├── streaming_tester.py
│   ├── auth_tester.py
│   ├── error_handler_tester.py
│   ├── performance_tester.py
│   └── certification.py
├── web/                 # Frontend (vanilla JS, no frameworks)
├── landing/             # Landing page (a2apex.io)
├── sdk/                 # Python SDK
├── sample_agent/        # Sample A2A agent for testing
├── data/                # SQLite databases (gitignored)
└── docs/                # Documentation
```

**Stack:** Python, FastAPI, vanilla JavaScript, SQLite. No frameworks, no build tools. Runs on a Mac mini.

## Self-Hosting

```bash
git clone https://github.com/Hauk307/a2apex.git
cd a2apex
pip install -r requirements.txt
python -m api.main
```

The app starts on `http://localhost:8091`. The sample agent runs on port 8092.

## Pricing

A2Apex is open source and free to self-host. The hosted version at [a2apex.io](https://a2apex.io) offers managed plans:

| Plan | Price | Tests/mo | Profiles | Certifications |
|------|-------|----------|----------|----------------|
| Free | $0 | 5 | 1 | 1 (90-day) |
| Pro | $29/mo | 50 | 5 | 3 |
| Startup | $99/mo | 500 | 15 | 20 |
| Enterprise | $499/mo | Unlimited | Unlimited | Unlimited |

## API

Full API docs at [app.a2apex.io/api/docs](https://app.a2apex.io/api/docs) (Swagger UI).

```bash
# Validate an agent card
curl -X POST https://app.a2apex.io/api/validate/agent-card \
  -H "Content-Type: application/json" \
  -d '{"url": "https://your-agent.example.com/.well-known/agent.json"}'
```

## Contributing

Contributions welcome. Open an issue first for anything non-trivial.

```bash
git clone https://github.com/Hauk307/a2apex.git
cd a2apex
pip install -r requirements.txt
python -m pytest
```

## The Story

I'm a dragline operator at a coal mine in Wyoming. I built A2Apex in two weeks because I saw Google's A2A protocol gaining traction and nobody was building developer tools for it. The AI agent market is projected to hit $236B by 2034, and every agent will need a way to prove it works. A2Apex is that proof.

Built with Claude on a Mac mini. From Wyoming. 🤠

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <a href="https://a2apex.io">Website</a> · 
  <a href="https://app.a2apex.io">App</a> · 
  <a href="https://app.a2apex.io/api/docs">API Docs</a> · 
  <a href="https://x.com/HAUK_777">Twitter</a>
</p>

<p align="center">
  Built by <a href="https://a2apex.io">A2Apex Ventures LLC</a>, Wyoming
</p>
