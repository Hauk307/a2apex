"""
A2Apex Fix Guidance System

Provides actionable fix recommendations for every failed test.
Each guidance includes:
- What's wrong (context from the test)
- How to fix it with code snippets
- Link to relevant A2A spec section
"""

from dataclasses import dataclass
from typing import Optional


# A2A Spec base URL
A2A_SPEC_BASE = "https://google.github.io/A2A"


@dataclass
class FixGuidance:
    """Fix guidance for a failed test."""
    fix: str  # Human-readable fix instructions
    code_snippet: Optional[str] = None  # Copy-pastable code
    spec_url: str = A2A_SPEC_BASE  # Link to spec section


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT CARD VALIDATION FIX GUIDANCE
# ═══════════════════════════════════════════════════════════════════════════════

AGENT_CARD_FIXES = {
    "name_missing": FixGuidance(
        fix="Add a 'name' field to your Agent Card. This is required and should be a human-readable name for your agent.",
        code_snippet='''{
  "name": "My A2A Agent",
  "description": "A helpful AI agent",
  ...
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "url_missing": FixGuidance(
        fix="Add a 'url' field pointing to your agent's A2A endpoint (where JSON-RPC requests are sent).",
        code_snippet='''{
  "url": "https://your-agent.example.com/a2a",
  ...
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "url_invalid": FixGuidance(
        fix="The 'url' field must be a valid HTTP/HTTPS URL pointing to your A2A endpoint.",
        code_snippet='''{
  "url": "https://your-agent.example.com/a2a"
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "url_not_https": FixGuidance(
        fix="For production, use HTTPS for your agent URL. HTTP is only acceptable for localhost/development.",
        code_snippet='''{
  "url": "https://your-agent.example.com/a2a"
}''',
        spec_url=f"{A2A_SPEC_BASE}/#security"
    ),
    "version_missing": FixGuidance(
        fix="Add a 'version' field with semantic versioning (e.g., '1.0.0').",
        code_snippet='''{
  "version": "1.0.0"
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "version_invalid": FixGuidance(
        fix="Use semantic versioning format: MAJOR.MINOR.PATCH (e.g., '1.2.3').",
        code_snippet='''{
  "version": "1.0.0"
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "capabilities_missing": FixGuidance(
        fix="Add a 'capabilities' object describing what your agent supports.",
        code_snippet='''{
  "capabilities": {
    "streaming": false,
    "pushNotifications": false,
    "stateTransitionHistory": true
  }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#capabilities"
    ),
    "skills_missing": FixGuidance(
        fix="Add a 'skills' array listing what your agent can do. Each skill needs 'id' and 'name'.",
        code_snippet='''{
  "skills": [
    {
      "id": "chat",
      "name": "General Chat",
      "description": "Have a conversation with the agent",
      "tags": ["chat", "conversation"]
    }
  ]
}''',
        spec_url=f"{A2A_SPEC_BASE}/#skills"
    ),
    "skills_empty": FixGuidance(
        fix="Your agent must have at least one skill. Add skills describing what your agent can do.",
        code_snippet='''{
  "skills": [
    {
      "id": "assistant",
      "name": "AI Assistant",
      "description": "General purpose AI assistant"
    }
  ]
}''',
        spec_url=f"{A2A_SPEC_BASE}/#skills"
    ),
    "skill_id_missing": FixGuidance(
        fix="Each skill must have a unique 'id' field (string identifier).",
        code_snippet='''{
  "skills": [
    {
      "id": "unique-skill-id",
      "name": "Skill Name"
    }
  ]
}''',
        spec_url=f"{A2A_SPEC_BASE}/#skills"
    ),
    "skill_name_missing": FixGuidance(
        fix="Each skill must have a 'name' field (human-readable name).",
        code_snippet='''{
  "skills": [
    {
      "id": "my-skill",
      "name": "My Skill Name"
    }
  ]
}''',
        spec_url=f"{A2A_SPEC_BASE}/#skills"
    ),
    "description_missing": FixGuidance(
        fix="Add a 'description' field explaining what your agent does. This helps users understand your agent.",
        code_snippet='''{
  "description": "A helpful AI assistant that can answer questions and help with tasks."
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "defaultInputModes_missing": FixGuidance(
        fix="Add 'defaultInputModes' listing MIME types your agent accepts. Most agents accept 'text/plain'.",
        code_snippet='''{
  "defaultInputModes": ["text/plain", "application/json"]
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "defaultOutputModes_missing": FixGuidance(
        fix="Add 'defaultOutputModes' listing MIME types your agent outputs.",
        code_snippet='''{
  "defaultOutputModes": ["text/plain", "application/json"]
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "protocolVersion_missing": FixGuidance(
        fix="Add 'protocolVersion' to specify which A2A protocol version you implement.",
        code_snippet='''{
  "protocolVersion": "0.3"
}''',
        spec_url=f"{A2A_SPEC_BASE}/#versioning"
    ),
    "provider_missing": FixGuidance(
        fix="Add a 'provider' object with your organization info for trust and attribution.",
        code_snippet='''{
  "provider": {
    "organization": "Your Company Name",
    "url": "https://your-company.com"
  }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "securitySchemes_invalid": FixGuidance(
        fix="Security schemes must follow OpenAPI 3.0 format. Common types: 'apiKey', 'http', 'oauth2'.",
        code_snippet='''{
  "securitySchemes": {
    "apiKey": {
      "type": "apiKey",
      "name": "X-API-Key",
      "in": "header"
    }
  },
  "security": [{"apiKey": []}]
}''',
        spec_url=f"{A2A_SPEC_BASE}/#security"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# LIVE TEST FIX GUIDANCE
# ═══════════════════════════════════════════════════════════════════════════════

LIVE_TEST_FIXES = {
    "agent_card_not_found": FixGuidance(
        fix="Your agent must serve an Agent Card at /.well-known/agent-card.json. This is how other agents discover your capabilities.",
        code_snippet='''# FastAPI example
@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    return {
        "name": "My Agent",
        "url": "https://your-agent.com/a2a",
        "version": "1.0.0",
        "capabilities": {"streaming": False},
        "skills": [{"id": "chat", "name": "Chat"}]
    }''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-discovery"
    ),
    "agent_card_connection_failed": FixGuidance(
        fix="Could not connect to your agent. Ensure your server is running and accessible from the internet.",
        code_snippet='''# Check your server is running:
curl https://your-agent.example.com/.well-known/agent-card.json

# Common issues:
# - Firewall blocking requests
# - Server not running
# - DNS not configured
# - SSL certificate invalid''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-discovery"
    ),
    "agent_card_invalid_json": FixGuidance(
        fix="Your Agent Card endpoint returned invalid JSON. Ensure you're returning valid JSON with Content-Type: application/json.",
        code_snippet='''# Ensure your endpoint returns JSON:
@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    return JSONResponse(
        content={...},
        media_type="application/json"
    )''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "message_send_failed": FixGuidance(
        fix="Your agent's /a2a endpoint must accept JSON-RPC 2.0 POST requests for the message/send method.",
        code_snippet='''# Handle message/send JSON-RPC method:
@app.post("/a2a")
async def handle_a2a(request: dict):
    if request.get("method") == "message/send":
        message = request["params"]["message"]
        # Process the message...
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "id": str(uuid.uuid4()),
                "status": {"state": "completed"},
                "artifacts": [...]
            }
        }''',
        spec_url=f"{A2A_SPEC_BASE}/#message-send"
    ),
    "message_send_invalid_response": FixGuidance(
        fix="Your message/send response must be valid JSON-RPC 2.0 with a Task or Message in the result.",
        code_snippet='''{
  "jsonrpc": "2.0",
  "id": "request-id",
  "result": {
    "id": "task-uuid",
    "contextId": "context-uuid",
    "status": {
      "state": "completed",
      "timestamp": "2024-01-01T00:00:00Z"
    },
    "artifacts": [{
      "artifactId": "artifact-uuid",
      "parts": [{"kind": "text", "text": "Response text"}]
    }]
  }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#task-object"
    ),
    "invalid_task_state": FixGuidance(
        fix="Task state must be one of: submitted, working, input-required, auth-required, completed, failed, canceled, rejected.",
        code_snippet='''# Valid task states:
VALID_STATES = [
    "submitted",      # Task received
    "working",        # Agent is processing
    "input-required", # Waiting for user input
    "auth-required",  # Waiting for authentication
    "completed",      # Successfully done
    "failed",         # Error occurred
    "canceled",       # User canceled
    "rejected"        # Agent declined
]

# Example response:
{
    "status": {
        "state": "completed",
        "timestamp": "2024-01-01T00:00:00Z"
    }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#task-state"
    ),
    "task_get_failed": FixGuidance(
        fix="Implement the tasks/get method to retrieve task status by ID.",
        code_snippet='''@app.post("/a2a")
async def handle_a2a(request: dict):
    if request.get("method") == "tasks/get":
        task_id = request["params"]["id"]
        task = get_task_from_storage(task_id)
        if not task:
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {
                    "code": -32001,
                    "message": "Task not found"
                }
            }
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": task
        }''',
        spec_url=f"{A2A_SPEC_BASE}/#tasks-get"
    ),
    "task_cancel_failed": FixGuidance(
        fix="Implement the tasks/cancel method to cancel running tasks.",
        code_snippet='''@app.post("/a2a")
async def handle_a2a(request: dict):
    if request.get("method") == "tasks/cancel":
        task_id = request["params"]["id"]
        task = get_task(task_id)
        
        if task["status"]["state"] in ["completed", "failed", "canceled"]:
            return {
                "jsonrpc": "2.0",
                "id": request["id"],
                "error": {
                    "code": -32002,
                    "message": "Task cannot be canceled"
                }
            }
        
        task["status"]["state"] = "canceled"
        return {"jsonrpc": "2.0", "id": request["id"], "result": task}''',
        spec_url=f"{A2A_SPEC_BASE}/#tasks-cancel"
    ),
    "streaming_not_working": FixGuidance(
        fix="If you declare streaming support, implement Server-Sent Events (SSE) for the message/stream method.",
        code_snippet='''from sse_starlette.sse import EventSourceResponse

@app.post("/a2a")
async def handle_a2a(request: Request):
    data = await request.json()
    if data.get("method") == "message/stream":
        return EventSourceResponse(stream_response(data))

async def stream_response(request):
    task_id = str(uuid.uuid4())
    
    # Initial status
    yield {"data": json.dumps({
        "jsonrpc": "2.0",
        "result": {"statusUpdate": {"state": "working"}}
    })}
    
    # Stream content...
    yield {"data": json.dumps({
        "jsonrpc": "2.0",
        "result": {"artifact": {"parts": [{"kind": "text", "text": "..."}]}}
    })}
    
    # Final status
    yield {"data": json.dumps({
        "jsonrpc": "2.0",
        "result": {"statusUpdate": {"state": "completed", "final": True}}
    })}''',
        spec_url=f"{A2A_SPEC_BASE}/#streaming"
    ),
    "invalid_method_no_error": FixGuidance(
        fix="Return JSON-RPC error -32601 (Method not found) for unknown methods.",
        code_snippet='''@app.post("/a2a")
async def handle_a2a(request: dict):
    method = request.get("method")
    
    if method not in SUPPORTED_METHODS:
        return {
            "jsonrpc": "2.0",
            "id": request.get("id"),
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
    "invalid_json_no_error": FixGuidance(
        fix="Return JSON-RPC error -32700 (Parse error) for invalid JSON input.",
        code_snippet='''from fastapi import Request
from fastapi.responses import JSONResponse

@app.post("/a2a")
async def handle_a2a(request: Request):
    try:
        data = await request.json()
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=200,  # JSON-RPC uses 200 even for errors
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error: Invalid JSON"
                }
            }
        )''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
    
    # ═══════════════════════════════════════════════════════════════════════════
    # WARNING-SPECIFIC FIX GUIDANCE (shown for warnings, not just failures)
    # ═══════════════════════════════════════════════════════════════════════════
    
    "agent_card_validation_errors": FixGuidance(
        fix="Your Agent Card was fetched successfully but has validation errors. Review the errors and fix them for better compliance.",
        code_snippet='''# Ensure your Agent Card has all required fields:
{
  "name": "My A2A Agent",           # Required
  "url": "https://example.com/a2a",  # Required
  "version": "1.0.0",                # Required
  "capabilities": {                  # Required
    "streaming": false,
    "pushNotifications": false
  },
  "skills": [{                       # Required, at least one
    "id": "my-skill",
    "name": "My Skill"
  }]
}''',
        spec_url=f"{A2A_SPEC_BASE}/#agent-card"
    ),
    "response_unexpected_structure": FixGuidance(
        fix="The response structure doesn't match A2A spec. The result should be a Task object (with 'id' and 'status') or a Message object (with 'role' and 'parts').",
        code_snippet='''# Correct Task response:
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "result": {
    "id": "task-uuid",          # Required for Task
    "status": {                 # Required for Task
      "state": "completed",
      "timestamp": "2024-01-01T00:00:00Z"
    },
    "artifacts": [...]
  }
}

# Or correct Message response:
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "result": {
    "role": "agent",           # Required for Message
    "parts": [{"kind": "text", "text": "Hello"}]  # Required
  }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#task-object"
    ),
    "task_not_found_warning": FixGuidance(
        fix="Task was not found, possibly because it expired or was never stored. Consider implementing persistent task storage for better reliability.",
        code_snippet='''# Store tasks persistently (e.g., in Redis or database):
import redis

r = redis.Redis()

# When creating a task:
r.setex(f"task:{task_id}", 3600, json.dumps(task))  # 1 hour TTL

# When retrieving:
task_data = r.get(f"task:{task_id}")
if not task_data:
    return {"error": {"code": -32001, "message": "Task not found"}}
''',
        spec_url=f"{A2A_SPEC_BASE}/#tasks-get"
    ),
    "wrong_error_code": FixGuidance(
        fix="Use the correct JSON-RPC error codes. -32601 for method not found, -32700 for parse error, -32600 for invalid request.",
        code_snippet='''# Standard JSON-RPC error codes:
ERROR_CODES = {
    -32700: "Parse error",         # Invalid JSON
    -32600: "Invalid Request",     # Not valid JSON-RPC
    -32601: "Method not found",    # Unknown method
    -32602: "Invalid params",      # Invalid method params
    -32603: "Internal error",      # Server error
}

# A2A-specific error codes:
A2A_ERROR_CODES = {
    -32001: "Task not found",
    -32002: "Task not cancelable",
    -32003: "Push notification not supported",
    -32004: "Unsupported operation",
}''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
    "response_not_json": FixGuidance(
        fix="For invalid JSON input, return a JSON-RPC error response (not HTML or plain text). Even error responses should be valid JSON.",
        code_snippet='''# Always return JSON for JSON-RPC errors:
from fastapi import Request
from fastapi.responses import JSONResponse

@app.post("/a2a")
async def handle_a2a(request: Request):
    try:
        data = await request.json()
    except:
        # Return JSON error, not HTTP error page
        return JSONResponse(
            status_code=200,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32700,
                    "message": "Parse error: Invalid JSON"
                }
            }
        )''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# ERROR HANDLING TEST FIX GUIDANCE  
# ═══════════════════════════════════════════════════════════════════════════════

ERROR_TEST_FIXES = {
    "parse_error": FixGuidance(
        fix="Return error code -32700 for malformed JSON with a clear error message.",
        code_snippet='''{
    "jsonrpc": "2.0",
    "id": null,
    "error": {
        "code": -32700,
        "message": "Parse error: Invalid JSON"
    }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
    "invalid_request": FixGuidance(
        fix="Return error code -32600 for invalid JSON-RPC request structure.",
        code_snippet='''{
    "jsonrpc": "2.0",
    "id": "req-id",
    "error": {
        "code": -32600,
        "message": "Invalid Request: missing required field 'method'"
    }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
    "method_not_found": FixGuidance(
        fix="Return error code -32601 when the requested method doesn't exist.",
        code_snippet='''{
    "jsonrpc": "2.0",
    "id": "req-id",
    "error": {
        "code": -32601,
        "message": "Method not found: unknown/method"
    }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
    "invalid_params": FixGuidance(
        fix="Return error code -32602 when method parameters are invalid.",
        code_snippet='''{
    "jsonrpc": "2.0",
    "id": "req-id",
    "error": {
        "code": -32602,
        "message": "Invalid params: 'message' is required"
    }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
    "task_not_found": FixGuidance(
        fix="Return A2A error code -32001 when a requested task doesn't exist.",
        code_snippet='''{
    "jsonrpc": "2.0",
    "id": "req-id",
    "error": {
        "code": -32001,
        "message": "Task not found",
        "data": {"taskId": "non-existent-id"}
    }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#error-codes"
    ),
    "task_not_cancelable": FixGuidance(
        fix="Return A2A error code -32002 when trying to cancel a completed/failed task.",
        code_snippet='''{
    "jsonrpc": "2.0",
    "id": "req-id",
    "error": {
        "code": -32002,
        "message": "Task cannot be canceled",
        "data": {"taskId": "task-id", "state": "completed"}
    }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#error-codes"
    ),
    "missing_error_code": FixGuidance(
        fix="JSON-RPC error responses must include a numeric 'code' field.",
        code_snippet='''{
    "jsonrpc": "2.0",
    "id": "req-id",
    "error": {
        "code": -32600,  // Required!
        "message": "Error description"
    }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
    "missing_error_message": FixGuidance(
        fix="JSON-RPC error responses must include a 'message' string field.",
        code_snippet='''{
    "jsonrpc": "2.0",
    "id": "req-id",
    "error": {
        "code": -32600,
        "message": "Human-readable error description"  // Required!
    }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#error-handling"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# AUTH/SECURITY TEST FIX GUIDANCE
# ═══════════════════════════════════════════════════════════════════════════════

AUTH_TEST_FIXES = {
    "no_security_schemes": FixGuidance(
        fix="Define security schemes in your Agent Card if your agent requires authentication.",
        code_snippet='''{
  "securitySchemes": {
    "apiKey": {
      "type": "apiKey",
      "name": "X-API-Key",
      "in": "header",
      "description": "API key for authentication"
    }
  },
  "security": [{"apiKey": []}]
}''',
        spec_url=f"{A2A_SPEC_BASE}/#security"
    ),
    "unauthenticated_access": FixGuidance(
        fix="If you require auth, return 401 Unauthorized for requests without valid credentials.",
        code_snippet='''@app.post("/a2a")
async def handle_a2a(request: Request):
    api_key = request.headers.get("X-API-Key")
    if not api_key or not is_valid_key(api_key):
        return JSONResponse(
            status_code=401,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32000,
                    "message": "Unauthorized: Invalid or missing API key"
                }
            }
        )''',
        spec_url=f"{A2A_SPEC_BASE}/#security"
    ),
    "https_required": FixGuidance(
        fix="Production agents should use HTTPS to protect credentials in transit.",
        code_snippet='''# In your Agent Card:
{
  "url": "https://your-agent.example.com/a2a"  // Use HTTPS!
}

# Deploy with SSL/TLS:
# - Use a reverse proxy (nginx, Caddy) with Let's Encrypt
# - Or deploy to a platform with built-in HTTPS''',
        spec_url=f"{A2A_SPEC_BASE}/#security"
    ),
    "bearer_auth_invalid": FixGuidance(
        fix="For HTTP Bearer authentication, validate the token in the Authorization header.",
        code_snippet='''# Agent Card security scheme:
{
  "securitySchemes": {
    "bearerAuth": {
      "type": "http",
      "scheme": "bearer",
      "bearerFormat": "JWT"
    }
  }
}

# Server validation:
auth_header = request.headers.get("Authorization")
if auth_header and auth_header.startswith("Bearer "):
    token = auth_header[7:]
    # Validate token...''',
        spec_url=f"{A2A_SPEC_BASE}/#security"
    ),
    "oauth2_config_invalid": FixGuidance(
        fix="OAuth2 security schemes must specify valid flow configurations.",
        code_snippet='''{
  "securitySchemes": {
    "oauth2": {
      "type": "oauth2",
      "flows": {
        "authorizationCode": {
          "authorizationUrl": "https://auth.example.com/authorize",
          "tokenUrl": "https://auth.example.com/token",
          "scopes": {
            "read": "Read access",
            "write": "Write access"
          }
        }
      }
    }
  }
}''',
        spec_url=f"{A2A_SPEC_BASE}/#security"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# STREAMING TEST FIX GUIDANCE
# ═══════════════════════════════════════════════════════════════════════════════

STREAMING_TEST_FIXES = {
    "sse_not_supported": FixGuidance(
        fix="To support streaming, return Content-Type: text/event-stream and send SSE formatted events.",
        code_snippet='''from sse_starlette.sse import EventSourceResponse

@app.post("/a2a")
async def handle_a2a(request: Request):
    data = await request.json()
    if data.get("method") == "message/stream":
        return EventSourceResponse(
            stream_generator(data),
            media_type="text/event-stream"
        )''',
        spec_url=f"{A2A_SPEC_BASE}/#streaming"
    ),
    "invalid_sse_format": FixGuidance(
        fix="SSE events must have 'data:' prefix followed by JSON, with events separated by double newlines.",
        code_snippet='''# Correct SSE format:
data: {"jsonrpc":"2.0","result":{"statusUpdate":{"state":"working"}}}

data: {"jsonrpc":"2.0","result":{"artifact":{"parts":[{"kind":"text","text":"Hello"}]}}}

data: {"jsonrpc":"2.0","result":{"statusUpdate":{"state":"completed","final":true}}}
''',
        spec_url=f"{A2A_SPEC_BASE}/#streaming"
    ),
    "no_final_event": FixGuidance(
        fix="Streaming must end with a final status update where final=true.",
        code_snippet='''async def stream_response(request):
    # ... stream content ...
    
    # Always end with final status:
    yield {
        "data": json.dumps({
            "jsonrpc": "2.0",
            "result": {
                "statusUpdate": {
                    "state": "completed",
                    "final": True  # Required to signal end!
                }
            }
        })
    }''',
        spec_url=f"{A2A_SPEC_BASE}/#streaming"
    ),
    "stream_timeout": FixGuidance(
        fix="Keep streaming connections alive and send periodic heartbeats for long-running tasks.",
        code_snippet='''async def stream_response(request):
    last_event_time = time.time()
    
    while not task_complete:
        if time.time() - last_event_time > 15:
            # Send heartbeat to keep connection alive
            yield {"data": json.dumps({
                "jsonrpc": "2.0",
                "result": {"statusUpdate": {"state": "working"}}
            })}
            last_event_time = time.time()
        
        await asyncio.sleep(0.1)''',
        spec_url=f"{A2A_SPEC_BASE}/#streaming"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE TEST FIX GUIDANCE
# ═══════════════════════════════════════════════════════════════════════════════

PERF_TEST_FIXES = {
    "slow_agent_card": FixGuidance(
        fix="Agent Card should load in <500ms. Consider caching or serving from CDN.",
        code_snippet='''# Cache the agent card in memory:
AGENT_CARD = {
    "name": "My Agent",
    # ... full card ...
}

@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    return AGENT_CARD  # No DB/file read on each request''',
        spec_url=f"{A2A_SPEC_BASE}/#performance"
    ),
    "slow_message_send": FixGuidance(
        fix="For slow tasks, return immediately with status 'working' and let clients poll or stream.",
        code_snippet='''@app.post("/a2a")
async def handle_a2a(request: dict):
    if request.get("method") == "message/send":
        task_id = str(uuid.uuid4())
        
        # Start async processing
        asyncio.create_task(process_in_background(task_id, request))
        
        # Return immediately with "working" status
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "id": task_id,
                "status": {"state": "working"}
            }
        }''',
        spec_url=f"{A2A_SPEC_BASE}/#async-tasks"
    ),
    "concurrent_request_failure": FixGuidance(
        fix="Ensure your agent handles concurrent requests. Use async/await and avoid global state.",
        code_snippet='''# Use async for I/O operations:
async def process_message(message):
    async with httpx.AsyncClient() as client:
        response = await client.post(...)
    return response

# Avoid global mutable state:
# BAD:  current_task = None
# GOOD: Use per-request task storage or database''',
        spec_url=f"{A2A_SPEC_BASE}/#scalability"
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTION TO GET FIX GUIDANCE
# ═══════════════════════════════════════════════════════════════════════════════

def get_fix_guidance(test_type: str, error_key: str) -> Optional[FixGuidance]:
    """
    Get fix guidance for a specific test failure.
    
    Args:
        test_type: Type of test (agent_card, live, error, auth, streaming, perf)
        error_key: Specific error identifier
        
    Returns:
        FixGuidance object or None if not found
    """
    guidance_maps = {
        "agent_card": AGENT_CARD_FIXES,
        "live": LIVE_TEST_FIXES,
        "error": ERROR_TEST_FIXES,
        "auth": AUTH_TEST_FIXES,
        "streaming": STREAMING_TEST_FIXES,
        "perf": PERF_TEST_FIXES,
    }
    
    guidance_map = guidance_maps.get(test_type, {})
    return guidance_map.get(error_key)


def format_fix_for_result(guidance: FixGuidance) -> dict:
    """Format fix guidance for inclusion in test result."""
    result = {
        "fix": guidance.fix,
        "spec_url": guidance.spec_url,
    }
    if guidance.code_snippet:
        result["code_snippet"] = guidance.code_snippet
    return result


def get_fix_for_test(test_name: str, error: str = "", message: str = "") -> Optional[FixGuidance]:
    """
    Smart fix lookup by test name, error text, or message.
    Searches all fix guidance maps for the best match.
    """
    # Combine for searching
    search_text = f"{test_name} {error} {message}".lower()
    
    # Direct test_name lookup across all maps
    all_fixes = {}
    all_fixes.update(AGENT_CARD_FIXES)
    all_fixes.update(LIVE_TEST_FIXES)
    all_fixes.update(ERROR_TEST_FIXES)
    all_fixes.update(AUTH_TEST_FIXES)
    all_fixes.update(STREAMING_TEST_FIXES)
    all_fixes.update(PERF_TEST_FIXES)
    
    # Try exact match on test_name
    if test_name in all_fixes:
        return all_fixes[test_name]
    
    # Try matching by key substring
    for key, fix in all_fixes.items():
        if key in search_text or key.replace("_", " ") in search_text:
            return fix
    
    # Generic fallback based on common patterns
    if "404" in search_text or "not found" in search_text:
        return FixGuidance(
            fix="The endpoint returned 404 Not Found. Make sure your A2A agent is running and the URL is correct. The agent must serve an Agent Card at /.well-known/agent-card.json.",
            code_snippet='# Verify your agent is accessible\ncurl -s https://your-agent.com/.well-known/agent-card.json',
            spec_url="https://google.github.io/A2A/#agent-discovery"
        )
    
    if "connection" in search_text or "timeout" in search_text:
        return FixGuidance(
            fix="Could not connect to the agent. Verify the URL is correct and the agent is running and accessible from the internet.",
            code_snippet='# Test connectivity\ncurl -v https://your-agent.com/.well-known/agent-card.json',
            spec_url="https://google.github.io/A2A/#agent-discovery"
        )
    
    if "json" in search_text or "parse" in search_text or "decode" in search_text:
        return FixGuidance(
            fix="The response was not valid JSON. A2A agents must return JSON-RPC 2.0 responses with Content-Type: application/json.",
            code_snippet='# Your endpoint must return valid JSON-RPC 2.0\nreturn JSONResponse({\n    "jsonrpc": "2.0",\n    "id": request_id,\n    "result": task.to_dict()\n})',
            spec_url="https://google.github.io/A2A/#json-rpc"
        )
    
    if "jsonrpc" in search_text or "rpc" in search_text:
        return FixGuidance(
            fix="The response is missing required JSON-RPC 2.0 fields. Every response must include 'jsonrpc': '2.0', 'id', and either 'result' or 'error'.",
            code_snippet='{\n    "jsonrpc": "2.0",\n    "id": 1,\n    "result": { ... }\n}',
            spec_url="https://google.github.io/A2A/#json-rpc"
        )
    
    if "error" in search_text and ("code" in search_text or "handling" in search_text):
        return FixGuidance(
            fix="Your agent should return proper JSON-RPC 2.0 error responses with numeric error codes. Use standard codes: -32700 (parse error), -32600 (invalid request), -32601 (method not found), -32602 (invalid params).",
            code_snippet='# Error response format\n{\n    "jsonrpc": "2.0",\n    "id": 1,\n    "error": {\n        "code": -32601,\n        "message": "Method not found"\n    }\n}',
            spec_url="https://google.github.io/A2A/#error-handling"
        )
    
    return None
