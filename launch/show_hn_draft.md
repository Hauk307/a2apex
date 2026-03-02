# A2Apex - Hacker News Show HN Draft

## Title

**Show HN: A2Apex – Compliance testing and certification for Google's A2A protocol**

---

## Body Text

I built A2Apex (https://a2apex.io) to solve a gap in the A2A ecosystem: there's no authoritative way to verify an agent actually implements the protocol correctly.

Google's A2A (Agent-to-Agent) protocol is positioning to become the standard for inter-agent communication. But Google has no incentive to build a tool that tells developers "your implementation fails"—that's bad marketing for their own protocol.

**What A2Apex does:**

1. Runs your agent against a comprehensive A2A compliance test suite
2. Issues tiered certification badges (Bronze/Silver/Gold) based on compliance depth
3. Lists certified agents in a public registry

**Technical details:**

- Tests cover the full Agent Card spec, task lifecycle, streaming responses, and error handling
- Bronze = basic handshake + task execution
- Silver = proper state management, cancellation handling, artifact streaming
- Gold = full spec compliance including edge cases and graceful degradation

The badge is an embeddable SVG you can drop in your README. The registry is queryable—you can programmatically check if an agent you're about to interact with has been certified.

**Why this matters:**

The agent economy is growing fast. When Agent A needs to delegate work to Agent B, there's currently no trust signal. Our badges work like the SSL padlock—a quick visual indicator that says "this agent has been independently verified."

**Pricing:** Free tier (3 tests/mo), Pro ($29/mo unlimited), Enterprise ($499/mo permanent badges).

Built this solo with AI assistance in about a week. The core insight was simple: certification is a different product than debugging. Google will build great debugging tools. They won't build the thing that fails their users.

Happy to answer questions about the test suite, the badge system, or the A2A protocol itself.

---

## Prepared FAQ Answers

### "Why would I trust your certification over just running my own tests?"

Fair question. Two reasons:

1. **Standardization** – We maintain a canonical test suite that evolves with the spec. You could build your own, but then you're maintaining it forever.

2. **Third-party verification** – Same reason code audits exist. "I tested my own code" means less than "an independent party tested it." The badge is a signal to *other* developers, not to you.

That said, if you want to run our tests locally without certification, the test specs are documented. We're not trying to be a black box.

---

### "What's the actual test coverage? How do I know it's comprehensive?"

Current coverage:

- Agent Card validation (schema, required fields, capability declarations)
- Task lifecycle (create, execute, cancel, status queries)
- Streaming protocol compliance (SSE format, event types, chunking)
- Error handling (malformed requests, timeout behavior, state recovery)
- Multi-turn conversation handling
- Artifact management

Gold tier adds edge cases: concurrent task limits, graceful degradation under load, proper 4xx/5xx responses.

We publish a changelog when we add new tests. The spec evolves; we evolve with it.

---

### "Is this just a cash grab before A2A even has adoption?"

A2A is early, agreed. But certification infrastructure *has* to exist before mass adoption, not after. If we wait until there are 10,000 A2A agents, the trust problem is already entrenched.

Also: free tier exists. Test 3 agents/month for $0. We're not paywalling the problem—we're paywalling scale.

---

### "Why badges? Feels gimmicky."

The badge is a delivery mechanism for trust. It's not about gamification—it's about having a machine-readable, embeddable artifact that says "verified."

Same reason npm has verified publisher badges. Same reason GitHub shows the green checkmark on signed commits. Quick visual trust signals matter in ecosystems.

---

### "How do you prevent people from gaming the tests?"

Tests run against your live endpoint. We don't accept pre-recorded responses. The test suite includes randomized elements (task IDs, payloads, timing) so you can't just replay a passing run.

For Gold certification, we also do periodic re-verification. Your badge can expire if your agent stops passing.

---

### "Solo founder building trust infrastructure? That's a risk."

It is. I'm not pretending otherwise. But the alternative is waiting for Google to do it (they won't) or for a VC-backed company to care (they'll optimize for enterprise first).

The code is straightforward. The value is in the test suite and the registry network effect. If this takes off, I'll hire. If not, the free tier keeps running and the problem stays solved for hobby projects.

---

### "What's preventing Google from just copying this?"

Nothing. But they'd have to build something that tells their own users "you failed." That's a brand problem for them, not a technical one.

Also: we're not competing with Google. We're filling a gap they structurally can't fill. If they did build this, I'd probably just use theirs. But I don't think they will.

---

### "What's your stack?"

[Fill in based on actual stack—HN loves technical details]

Example: "Next.js frontend, Go backend for the test runner, Postgres for registry data, deployed on [provider]. The test runner is stateless—spins up per test, runs the suite, records results, tears down."

---

### "Are you open source?"

[Adjust based on actual plans]

Option A (if yes): "Test suite is open source. Registry and badge infrastructure are hosted services. You can run the tests yourself; you pay us for the certification and listing."

Option B (if no): "Not currently. The test specs are documented so you can see what we're checking, but the runner itself is proprietary. Open to revisiting if there's demand."
