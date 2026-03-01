"""
Sample A2A Agent - A minimal but complete A2A-compliant agent.

This agent implements the A2A protocol for testing and demos.
Run with: python3 -m uvicorn sample_agent.main:app --port 8092

Features:
- Agent Card at /.well-known/agent-card.json
- message/send (JSON-RPC 2.0)
- message/stream (SSE streaming)
- tasks/get
- tasks/cancel
- Two skills: "echo" and "weather"
"""

import asyncio
import json
import uuid
import random
from datetime import datetime
from typing import Any, Optional
from enum import Enum

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel


# ============================================================================
# APP SETUP
# ============================================================================

app = FastAPI(
    title="Sample A2A Agent",
    description="A minimal A2A-compliant agent for testing",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# DATA MODELS
# ============================================================================

class TaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    AUTH_REQUIRED = "auth-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"


class Task:
    """In-memory task storage."""
    def __init__(self, task_id: str, context_id: str, message: dict):
        self.id = task_id
        self.context_id = context_id
        self.state = TaskState.SUBMITTED
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.messages = [message]
        self.artifacts = []
        self.history = []
        self.metadata = {}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "contextId": self.context_id,
            "status": {
                "state": self.state.value,
                "timestamp": self.updated_at.isoformat() + "Z"
            },
            "artifacts": self.artifacts,
            "history": self.history,
            "metadata": self.metadata,
            "kind": "task"
        }

    def update_state(self, state: TaskState):
        self.state = state
        self.updated_at = datetime.utcnow()


# In-memory task storage
tasks: dict[str, Task] = {}
contexts: dict[str, list[str]] = {}  # context_id -> list of task_ids


# ============================================================================
# AGENT CARD
# ============================================================================

AGENT_CARD = {
    "name": "Sample A2A Agent",
    "description": "A minimal but complete A2A-compliant agent for testing and demos. Supports echo and fake weather queries.",
    "url": "http://localhost:8092/a2a",
    "version": "1.0.0",
    "protocolVersion": "0.3.0",
    "preferredTransport": "JSONRPC",
    "capabilities": {
        "streaming": True,
        "pushNotifications": False,
        "stateTransitionHistory": True
    },
    "defaultInputModes": ["text/plain", "application/json"],
    "defaultOutputModes": ["text/plain", "application/json"],
    "skills": [
        {
            "id": "echo",
            "name": "Echo",
            "description": "Echoes back whatever you send. Useful for testing basic connectivity and message passing.",
            "tags": ["testing", "debug", "utility"],
            "examples": [
                "Echo: Hello World",
                "echo test message",
                "Echo back this text"
            ],
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain"]
        },
        {
            "id": "weather",
            "name": "Weather",
            "description": "Returns fake weather data for any location. Great for testing structured data responses.",
            "tags": ["weather", "demo", "data"],
            "examples": [
                "Weather in New York",
                "What's the weather in Tokyo?",
                "weather: San Francisco"
            ],
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain", "application/json"]
        }
    ],
    "securitySchemes": {
        "apiKey": {
            "type": "apiKey",
            "name": "X-API-Key",
            "in": "header",
            "description": "Optional API key for authentication"
        }
    },
    "security": [{"apiKey": []}],
    "provider": {
        "organization": "A2Apex Demo",
        "url": "https://github.com/a2aproject/A2A"
    },
    "documentationUrl": "https://github.com/a2aproject/A2A"
}


@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    """Serve the Agent Card."""
    return JSONResponse(
        content=AGENT_CARD,
        headers={"Content-Type": "application/json"}
    )


# ============================================================================
# SKILL HANDLERS
# ============================================================================

def handle_echo(text: str) -> tuple[str, list]:
    """Echo skill - returns the input text."""
    # Extract the actual message (remove "echo:" prefix if present)
    message = text
    for prefix in ["echo:", "Echo:", "ECHO:", "echo", "Echo"]:
        if text.lower().startswith(prefix.lower()):
            message = text[len(prefix):].strip()
            break
    
    response_text = f"🔊 Echo: {message}"
    
    artifacts = [{
        "artifactId": str(uuid.uuid4()),
        "name": "echo-response",
        "description": "Echoed message",
        "parts": [{"kind": "text", "text": response_text}]
    }]
    
    return response_text, artifacts


def handle_weather(text: str) -> tuple[str, list]:
    """Weather skill - returns fake weather data."""
    # Extract location
    location = "Unknown Location"
    for pattern in ["weather in ", "weather for ", "weather: ", "weather "]:
        if pattern in text.lower():
            idx = text.lower().index(pattern) + len(pattern)
            location = text[idx:].strip().rstrip("?").strip()
            break
    
    # If location still unknown, just use the whole text minus "weather"
    if location == "Unknown Location" and "weather" in text.lower():
        location = text.lower().replace("weather", "").strip()
        if not location:
            location = "Unknown Location"
    
    location = location.title()
    
    # Generate fake weather
    conditions = ["Sunny", "Cloudy", "Partly Cloudy", "Rainy", "Stormy", "Snowy", "Foggy", "Windy"]
    condition = random.choice(conditions)
    temp_c = random.randint(-10, 40)
    temp_f = round(temp_c * 9/5 + 32)
    humidity = random.randint(20, 95)
    wind_speed = random.randint(0, 50)
    
    weather_data = {
        "location": location,
        "condition": condition,
        "temperature": {
            "celsius": temp_c,
            "fahrenheit": temp_f
        },
        "humidity": humidity,
        "wind_speed_kmh": wind_speed,
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "note": "This is fake demo data - not real weather!"
    }
    
    emoji_map = {
        "Sunny": "☀️", "Cloudy": "☁️", "Partly Cloudy": "⛅",
        "Rainy": "🌧️", "Stormy": "⛈️", "Snowy": "❄️",
        "Foggy": "🌫️", "Windy": "💨"
    }
    emoji = emoji_map.get(condition, "🌡️")
    
    response_text = f"""{emoji} Weather in {location}

Condition: {condition}
Temperature: {temp_c}°C / {temp_f}°F
Humidity: {humidity}%
Wind: {wind_speed} km/h

⚠️ Note: This is fake demo data for testing purposes."""
    
    artifacts = [{
        "artifactId": str(uuid.uuid4()),
        "name": "weather-data",
        "description": f"Weather data for {location}",
        "parts": [
            {"kind": "text", "text": response_text},
            {"kind": "data", "data": weather_data}
        ]
    }]
    
    return response_text, artifacts


def detect_skill(text: str) -> str:
    """Detect which skill to use based on input text."""
    text_lower = text.lower()
    
    if any(word in text_lower for word in ["weather", "temperature", "forecast"]):
        return "weather"
    elif any(word in text_lower for word in ["echo", "repeat", "say back"]):
        return "echo"
    else:
        # Default to echo for anything else
        return "echo"


def process_message(text: str) -> tuple[str, list]:
    """Process a message and return response text and artifacts."""
    skill = detect_skill(text)
    
    if skill == "weather":
        return handle_weather(text)
    else:
        return handle_echo(text)


# ============================================================================
# JSON-RPC HELPERS
# ============================================================================

def make_jsonrpc_response(request_id: Any, result: dict) -> dict:
    """Create a JSON-RPC 2.0 success response."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": result
    }


def make_jsonrpc_error(request_id: Any, code: int, message: str, data: dict = None) -> dict:
    """Create a JSON-RPC 2.0 error response."""
    error = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": error
    }


# A2A-specific error codes
ERROR_CODES = {
    "parse_error": -32700,
    "invalid_request": -32600,
    "method_not_found": -32601,
    "invalid_params": -32602,
    "internal_error": -32603,
    "task_not_found": -32001,
    "task_not_cancelable": -32002,
    "unsupported_operation": -32004,
}


# ============================================================================
# A2A ENDPOINT
# ============================================================================

@app.post("/a2a")
async def a2a_endpoint(request: Request):
    """
    Main A2A JSON-RPC endpoint.
    
    Supports:
    - message/send: Send a message and get a task
    - message/stream: Send a message and stream updates (returns SSE)
    - tasks/get: Get task by ID
    - tasks/cancel: Cancel a task
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            content=make_jsonrpc_error(None, ERROR_CODES["parse_error"], "Parse error"),
            status_code=200
        )
    
    # Validate JSON-RPC request
    jsonrpc = body.get("jsonrpc")
    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})
    
    if jsonrpc != "2.0":
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_request"], 
                                       "Invalid request: jsonrpc must be '2.0'"),
            status_code=200
        )
    
    if not method:
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_request"], 
                                       "Invalid request: method is required"),
            status_code=200
        )
    
    # Route to handler
    if method == "message/send":
        return await handle_message_send(request_id, params)
    elif method == "message/stream":
        return await handle_message_stream(request_id, params)
    elif method == "tasks/get":
        return await handle_tasks_get(request_id, params)
    elif method == "tasks/cancel":
        return await handle_tasks_cancel(request_id, params)
    else:
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["method_not_found"],
                                       f"Method not found: {method}"),
            status_code=200
        )


# ============================================================================
# MESSAGE/SEND
# ============================================================================

async def handle_message_send(request_id: Any, params: dict) -> JSONResponse:
    """Handle message/send - create a task and process the message."""
    message = params.get("message")
    if not message:
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_params"],
                                       "Invalid params: message is required"),
            status_code=200
        )
    
    # Extract message text
    parts = message.get("parts", [])
    text_parts = [p.get("text", "") for p in parts if p.get("kind") == "text"]
    message_text = " ".join(text_parts).strip()
    
    if not message_text:
        message_text = "No text provided"
    
    # Get or create context
    context_id = message.get("contextId") or params.get("contextId") or str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    
    # Check if this is a follow-up to an existing task
    existing_task_id = message.get("taskId")
    if existing_task_id:
        if existing_task_id not in tasks:
            return JSONResponse(
                content=make_jsonrpc_error(request_id, ERROR_CODES["task_not_found"],
                                           f"Task not found: {existing_task_id}"),
                status_code=200
            )
        existing_task = tasks[existing_task_id]
        if existing_task.state in [TaskState.COMPLETED, TaskState.FAILED, 
                                   TaskState.CANCELED, TaskState.REJECTED]:
            return JSONResponse(
                content=make_jsonrpc_error(request_id, ERROR_CODES["unsupported_operation"],
                                           f"Cannot send message to {existing_task.state.value} task"),
                status_code=200
            )
        # Continue with existing task's context
        context_id = existing_task.context_id
    
    # Create task
    task = Task(task_id, context_id, message)
    tasks[task_id] = task
    
    # Track context
    if context_id not in contexts:
        contexts[context_id] = []
    contexts[context_id].append(task_id)
    
    # Process message
    task.update_state(TaskState.WORKING)
    
    try:
        response_text, artifacts = process_message(message_text)
        
        # Update task
        task.artifacts = artifacts
        task.history = [
            message,
            {
                "role": "agent",
                "messageId": str(uuid.uuid4()),
                "parts": [{"kind": "text", "text": response_text}],
                "kind": "message"
            }
        ]
        task.update_state(TaskState.COMPLETED)
        
    except Exception as e:
        task.update_state(TaskState.FAILED)
        task.metadata["error"] = str(e)
    
    return JSONResponse(
        content=make_jsonrpc_response(request_id, {"task": task.to_dict()}),
        status_code=200
    )


# ============================================================================
# MESSAGE/STREAM (SSE)
# ============================================================================

async def handle_message_stream(request_id: Any, params: dict):
    """Handle message/stream - stream task updates via SSE."""
    message = params.get("message")
    if not message:
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_params"],
                                       "Invalid params: message is required"),
            status_code=200
        )
    
    # Extract message text
    parts = message.get("parts", [])
    text_parts = [p.get("text", "") for p in parts if p.get("kind") == "text"]
    message_text = " ".join(text_parts).strip() or "No text provided"
    
    # Create task
    context_id = message.get("contextId") or str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    task = Task(task_id, context_id, message)
    tasks[task_id] = task
    
    if context_id not in contexts:
        contexts[context_id] = []
    contexts[context_id].append(task_id)
    
    async def event_generator():
        # First event: task created
        yield f"event: message\ndata: {json.dumps(make_jsonrpc_response(request_id, {'task': task.to_dict()}))}\n\n"
        
        await asyncio.sleep(0.1)
        
        # Status update: working
        task.update_state(TaskState.WORKING)
        status_event = {
            "kind": "status-update",
            "taskId": task.id,
            "contextId": task.context_id,
            "status": {"state": task.state.value, "timestamp": task.updated_at.isoformat() + "Z"},
            "final": False
        }
        yield f"event: message\ndata: {json.dumps(make_jsonrpc_response(request_id, {'statusUpdate': status_event}))}\n\n"
        
        # Simulate processing time
        await asyncio.sleep(0.3)
        
        # Process the message
        try:
            response_text, artifacts = process_message(message_text)
            
            # Stream artifacts one by one
            for i, artifact in enumerate(artifacts):
                task.artifacts.append(artifact)
                artifact_event = {
                    "kind": "artifact-update",
                    "taskId": task.id,
                    "contextId": task.context_id,
                    "artifact": artifact,
                    "append": False,
                    "lastChunk": True
                }
                yield f"event: message\ndata: {json.dumps(make_jsonrpc_response(request_id, {'artifactUpdate': artifact_event}))}\n\n"
                await asyncio.sleep(0.1)
            
            # Final status: completed
            task.update_state(TaskState.COMPLETED)
            task.history = [
                message,
                {
                    "role": "agent",
                    "messageId": str(uuid.uuid4()),
                    "parts": [{"kind": "text", "text": response_text}],
                    "kind": "message"
                }
            ]
            
            final_event = {
                "kind": "status-update",
                "taskId": task.id,
                "contextId": task.context_id,
                "status": {"state": task.state.value, "timestamp": task.updated_at.isoformat() + "Z"},
                "final": True
            }
            yield f"event: message\ndata: {json.dumps(make_jsonrpc_response(request_id, {'statusUpdate': final_event}))}\n\n"
            
        except Exception as e:
            task.update_state(TaskState.FAILED)
            task.metadata["error"] = str(e)
            
            error_event = {
                "kind": "status-update",
                "taskId": task.id,
                "contextId": task.context_id,
                "status": {
                    "state": task.state.value,
                    "timestamp": task.updated_at.isoformat() + "Z",
                    "message": {"role": "agent", "parts": [{"kind": "text", "text": f"Error: {e}"}]}
                },
                "final": True
            }
            yield f"event: message\ndata: {json.dumps(make_jsonrpc_response(request_id, {'statusUpdate': error_event}))}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ============================================================================
# TASKS/GET
# ============================================================================

async def handle_tasks_get(request_id: Any, params: dict) -> JSONResponse:
    """Handle tasks/get - retrieve a task by ID."""
    task_id = params.get("id")
    if not task_id:
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_params"],
                                       "Invalid params: id is required"),
            status_code=200
        )
    
    if task_id not in tasks:
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["task_not_found"],
                                       f"Task not found: {task_id}"),
            status_code=200
        )
    
    task = tasks[task_id]
    
    # Apply history length limit if specified
    history_length = params.get("historyLength")
    task_dict = task.to_dict()
    
    if history_length is not None and history_length >= 0:
        task_dict["history"] = task.history[-history_length:] if history_length > 0 else []
    else:
        task_dict["history"] = task.history
    
    return JSONResponse(
        content=make_jsonrpc_response(request_id, {"task": task_dict}),
        status_code=200
    )


# ============================================================================
# TASKS/CANCEL
# ============================================================================

async def handle_tasks_cancel(request_id: Any, params: dict) -> JSONResponse:
    """Handle tasks/cancel - cancel a task."""
    task_id = params.get("id")
    if not task_id:
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_params"],
                                       "Invalid params: id is required"),
            status_code=200
        )
    
    if task_id not in tasks:
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["task_not_found"],
                                       f"Task not found: {task_id}"),
            status_code=200
        )
    
    task = tasks[task_id]
    
    # Check if task is already in terminal state
    terminal_states = [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED, TaskState.REJECTED]
    if task.state in terminal_states:
        return JSONResponse(
            content=make_jsonrpc_error(request_id, ERROR_CODES["task_not_cancelable"],
                                       f"Task already in terminal state: {task.state.value}"),
            status_code=200
        )
    
    # Cancel the task
    task.update_state(TaskState.CANCELED)
    
    return JSONResponse(
        content=make_jsonrpc_response(request_id, {"task": task.to_dict()}),
        status_code=200
    )


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "sample-a2a-agent",
        "version": "1.0.0",
        "active_tasks": len(tasks),
        "active_contexts": len(contexts)
    }


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Sample A2A Agent on http://localhost:8092")
    print("📋 Agent Card: http://localhost:8092/.well-known/agent-card.json")
    print("🔌 A2A Endpoint: http://localhost:8092/a2a")
    uvicorn.run(app, host="0.0.0.0", port=8092)
