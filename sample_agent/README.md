# Sample A2A Agent

A minimal but **complete** A2A-compliant agent for testing and demos.

## Quick Start

```bash
# From the a2apex directory
python3 -m uvicorn sample_agent.main:app --port 8092
```

Then visit:
- Agent Card: http://localhost:8092/.well-known/agent-card.json
- Health: http://localhost:8092/health

## Features

### A2A Protocol Support

| Method | Supported | Notes |
|--------|-----------|-------|
| `message/send` | ✅ | Full JSON-RPC 2.0 |
| `message/stream` | ✅ | SSE streaming |
| `tasks/get` | ✅ | Retrieve task by ID |
| `tasks/cancel` | ✅ | Cancel in-progress tasks |

### Skills

#### 🔊 Echo
Echoes back whatever you send. Great for testing basic connectivity.

**Examples:**
- "Echo: Hello World"
- "echo test message"

#### 🌤️ Weather
Returns fake weather data for any location. Great for testing structured data.

**Examples:**
- "Weather in New York"
- "What's the weather in Tokyo?"

## API Examples

### Send a Message

```bash
curl -X POST http://localhost:8092/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "test-1",
    "method": "message/send",
    "params": {
      "message": {
        "role": "user",
        "messageId": "msg-1",
        "parts": [{"kind": "text", "text": "Weather in Paris"}],
        "kind": "message"
      }
    }
  }'
```

### Get a Task

```bash
curl -X POST http://localhost:8092/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "get-1",
    "method": "tasks/get",
    "params": {
      "id": "TASK_ID_HERE"
    }
  }'
```

### Stream a Message

```bash
curl -N http://localhost:8092/a2a \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": "stream-1",
    "method": "message/stream",
    "params": {
      "message": {
        "role": "user",
        "messageId": "msg-stream",
        "parts": [{"kind": "text", "text": "Echo: Hello streaming!"}],
        "kind": "message"
      }
    }
  }'
```

## Agent Card

The agent serves a complete Agent Card at `/.well-known/agent-card.json` with:

- **Protocol version:** 0.3.0
- **Capabilities:** streaming, stateTransitionHistory
- **Skills:** echo, weather
- **Security schemes:** API key (optional)

## Use with A2Apex

1. Start this sample agent on port 8092
2. Open A2Apex web UI
3. Click "🎮 Try Demo" to run automated tests against this agent
4. Or use "🔧 Debug Chat" tab to interact manually

## Architecture

```
sample_agent/
├── __init__.py         # Package marker
├── main.py             # FastAPI app with all endpoints
├── requirements.txt    # Dependencies
└── README.md           # This file
```

All logic is in `main.py` for simplicity. In a real agent, you'd split this into modules.

## Task States

This agent implements the full A2A task state machine:

```
submitted → working → completed
                   → failed
         → canceled
```

Terminal states (completed, failed, canceled) reject further messages.

## Notes

- This is a **demo agent** for testing A2Apex
- Weather data is **fake** - randomly generated
- Tasks are stored in-memory only (no persistence)
- No authentication required (API key scheme is declared but not enforced)
