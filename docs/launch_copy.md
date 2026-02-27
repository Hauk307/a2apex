# A2Apex Launch Copy

## Product Hunt Listing

### Tagline (60 chars max)
**Postman for AI Agents — Test A2A protocol compliance**

### Description

A2Apex is the first testing and validation tool for Google's A2A (Agent-to-Agent) protocol. Think Postman, but for AI agents that need to talk to each other.

As AI agents become the new APIs, they need a standardized way to communicate. Google's A2A protocol is emerging as that standard — but until now, there's been no way to verify your agent actually implements it correctly.

We built A2Apex because we needed it ourselves. Paste a URL, get instant compliance results. Run it in CI/CD. Ship agents that actually work together.

### Key Features

- 🔍 **Instant Validation** — Paste your agent URL, get compliance results in seconds
- ⚡ **Live Testing** — Run real protocol handshakes against your agent
- 🛠️ **CLI + SDK** — Integrate into any workflow with `pip install a2apex`
- 🔄 **CI/CD Ready** — GitHub Actions, GitLab CI, any pipeline
- 📊 **Detailed Reports** — Know exactly what's broken and how to fix it

### Maker Comment (Kyle)

Hey Product Hunt! 👋

I'm Kyle, and I built A2Apex because I got tired of manually debugging A2A integrations.

Google's A2A protocol is basically "how AI agents shake hands" — agent cards, capability discovery, task execution. It's well-designed, but the spec is 50+ pages. Implementing it correctly is tedious. Testing it is worse.

So I built the tool I wished existed: paste a URL, see what's broken, fix it, ship it.

**The stack:** Python + FastAPI backend, vanilla JS frontend, 10k+ lines of code, 113 tests passing. No magic, just thorough implementation of the spec.

**What's next:** We're working on a certification layer — a trust score for agents, so you know which ones are actually reliable before you integrate.

Try it free at a2apex.io. Would love your feedback.

— Kyle

---

## Hacker News "Show HN" Post

### Title
Show HN: A2Apex – Testing tool for Google's A2A (Agent-to-Agent) protocol

### Body

I built a testing and validation tool for Google's A2A protocol. Think of it as Postman, but for AI agents.

**What it does:**
- Validates agent cards (the JSON that describes what an agent can do)
- Runs live compliance tests against your agent endpoint
- CLI tool for CI/CD integration
- Web UI for quick checks

**Why I built it:**
I was implementing A2A for a project and kept running into protocol issues that took hours to debug. The spec is ~50 pages, and there are a lot of edge cases around authentication, capability negotiation, and task lifecycle. I wanted something that would just tell me "you're missing X" or "Y is malformed."

**Tech stack:**
- Python + FastAPI for the backend
- Vanilla JS frontend (no framework, just ~2k lines)
- The validation engine is ~4k lines covering the full A2A spec
- 113 tests, all passing

**What's working:**
- Agent card validation (schema, required fields, URLs)
- Capability discovery testing
- Authentication flow verification
- Basic task lifecycle tests

**What's next:**
- Streaming response testing
- Multi-agent interaction testing
- Trust/certification layer (publicly verifiable compliance scores)

Live at https://a2apex.io — free tier available.

Source will be on GitHub once I clean it up a bit.

Curious what protocol edge cases others have run into with A2A.

---

## X/Twitter Launch Thread

### Tweet 1 — Hook
🧵 Shipped something today: A2Apex — "Postman for AI Agents"

It's a testing tool for Google's A2A (Agent-to-Agent) protocol.

If you're building AI agents that need to talk to each other, this is for you.

### Tweet 2 — The Problem
The problem: A2A is a 50+ page spec.

Agent cards, capability discovery, auth flows, task lifecycle, streaming responses...

When something breaks, you're staring at a JSON blob trying to figure out what's wrong.

### Tweet 3 — The Solution
The solution: paste your agent URL → get instant compliance results.

What's valid ✅
What's broken ❌
How to fix it 🔧

[SCREENSHOT: Web UI showing validation results]

### Tweet 4 — Features
What you get:

→ Web UI for quick checks
→ CLI: `a2apex validate URL`
→ Python SDK: `pip install a2apex`
→ CI/CD integration (GitHub Actions snippet included)
→ Detailed error messages, not just "invalid"

### Tweet 5 — Demo
Try it now — no signup required:

🔗 https://a2apex.io

Paste any A2A agent URL. Results in seconds.

### Tweet 6 — Roadmap
What's next:

Phase 1: ✅ Web testing tool (live now)
Phase 2: CLI + SDK (in progress)
Phase 3: Trust layer — public compliance scores for agents

Think SSL certificates, but for AI agent reliability.

### Tweet 7 — CTA
If you're building A2A agents, I'd love feedback.

Try it: https://a2apex.io
Docs: https://a2apex.io/docs

And if you want early access to the trust layer, drop your email on the site.

Building in public. More updates coming. 🦊
