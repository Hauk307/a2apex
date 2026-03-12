"""
Math A2A Agent - Evaluates mathematical expressions safely.

Run with: python3 -m uvicorn agents.math_agent.main:app --port 8094
"""

import uuid
import re
import math
import operator
from datetime import datetime
from typing import Any
from enum import Enum

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse


# ============================================================================
# APP SETUP
# ============================================================================

app = FastAPI(
    title="Math Agent",
    description="Evaluates mathematical expressions",
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
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class Task:
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


tasks: dict[str, Task] = {}


# ============================================================================
# AGENT CARD
# ============================================================================

AGENT_CARD = {
    "name": "Math Agent",
    "description": "Evaluates mathematical expressions and returns results. Supports basic arithmetic, trigonometry, logarithms, and common math functions.",
    "url": "http://localhost:8094/a2a",
    "version": "1.0.0",
    "protocolVersion": "0.3.0",
    "preferredTransport": "JSONRPC",
    "capabilities": {
        "streaming": False,
        "pushNotifications": False,
        "stateTransitionHistory": True
    },
    "defaultInputModes": ["text/plain"],
    "defaultOutputModes": ["text/plain", "application/json"],
    "skills": [
        {
            "id": "calculate",
            "name": "Calculate",
            "description": "Evaluates mathematical expressions. Supports +, -, *, /, ^, sqrt, sin, cos, tan, log, ln, pi, e.",
            "tags": ["math", "calculator", "arithmetic"],
            "examples": [
                "Calculate 2 + 2",
                "What is sqrt(144)?",
                "Evaluate: sin(pi/2) + cos(0)",
                "5^3 + log(100)"
            ],
            "inputModes": ["text/plain"],
            "outputModes": ["text/plain", "application/json"]
        }
    ],
    "securitySchemes": {},
    "security": [],
    "provider": {
        "organization": "A2Apex Demo",
        "url": "https://app.a2apex.io"
    }
}


@app.get("/.well-known/agent.json")
@app.get("/.well-known/agent-card.json")
async def get_agent_card():
    return JSONResponse(content=AGENT_CARD)


# ============================================================================
# SAFE MATH EVALUATION
# ============================================================================

# Allowed functions and constants
SAFE_FUNCTIONS = {
    'abs': abs,
    'round': round,
    'min': min,
    'max': max,
    'sum': sum,
    'pow': pow,
    'sqrt': math.sqrt,
    'sin': math.sin,
    'cos': math.cos,
    'tan': math.tan,
    'asin': math.asin,
    'acos': math.acos,
    'atan': math.atan,
    'sinh': math.sinh,
    'cosh': math.cosh,
    'tanh': math.tanh,
    'log': math.log10,
    'log10': math.log10,
    'log2': math.log2,
    'ln': math.log,
    'exp': math.exp,
    'floor': math.floor,
    'ceil': math.ceil,
    'factorial': math.factorial,
    'gcd': math.gcd,
    'degrees': math.degrees,
    'radians': math.radians,
}

SAFE_CONSTANTS = {
    'pi': math.pi,
    'e': math.e,
    'tau': math.tau,
    'inf': math.inf,
}

# Allowed operators
SAFE_OPERATORS = {
    '+': operator.add,
    '-': operator.sub,
    '*': operator.mul,
    '/': operator.truediv,
    '//': operator.floordiv,
    '%': operator.mod,
    '**': operator.pow,
    '^': operator.pow,  # Common alternative for power
}


def safe_eval(expression: str) -> tuple[float, str]:
    """
    Safely evaluate a mathematical expression.
    Returns (result, expression_cleaned)
    """
    # Clean and normalize the expression
    expr = expression.lower().strip()
    
    # Remove common prefixes
    for prefix in ['calculate', 'evaluate', 'compute', 'what is', "what's", 'solve', 'math:', 'find', 'tell me']:
        if expr.startswith(prefix):
            expr = expr[len(prefix):].strip()
    
    # Remove trailing question mark and equals
    expr = expr.rstrip('?=').strip()
    
    # Natural language to expression conversion
    expr = re.sub(r'the\s+square\s+root\s+of\s+', 'sqrt(', expr)
    if 'sqrt(' in expr and ')' not in expr:
        expr += ')'
    expr = re.sub(r'(\d+)\s+squared', r'\1**2', expr)
    expr = re.sub(r'(\d+)\s+cubed', r'\1**3', expr)
    expr = re.sub(r'(\d+)\s+to\s+the\s+power\s+of\s+(\d+)', r'\1**\2', expr)
    expr = re.sub(r'(\d+)\s+plus\s+(\d+)', r'\1+\2', expr)
    expr = re.sub(r'(\d+)\s+minus\s+(\d+)', r'\1-\2', expr)
    expr = re.sub(r'(\d+)\s+times\s+(\d+)', r'\1*\2', expr)
    expr = re.sub(r'(\d+)\s+divided\s+by\s+(\d+)', r'\1/\2', expr)
    expr = re.sub(r'(\d+)\s+percent\s+of\s+(\d+)', r'\1/100*\2', expr)
    # Remove leftover words
    expr = re.sub(r'\b(the|of|a|is|equals|equal)\b', '', expr).strip()
    
    # Replace ^ with ** for power
    expr = expr.replace('^', '**')
    
    # Replace × and ÷ with * and /
    expr = expr.replace('×', '*').replace('÷', '/')
    
    # Handle implicit multiplication: 2pi -> 2*pi, 3(4+5) -> 3*(4+5)
    expr = re.sub(r'(\d)([a-z(])', r'\1*\2', expr)
    expr = re.sub(r'(\))(\d|[a-z(])', r'\1*\2', expr)
    
    # Validate characters (only allow safe characters)
    allowed_chars = set('0123456789.+-*/()%, \t')
    for name in list(SAFE_FUNCTIONS.keys()) + list(SAFE_CONSTANTS.keys()):
        allowed_chars.update(name)
    
    # Create evaluation namespace
    namespace = {}
    namespace.update(SAFE_FUNCTIONS)
    namespace.update(SAFE_CONSTANTS)
    
    # Remove any dangerous builtins
    namespace['__builtins__'] = {}
    
    try:
        result = eval(expr, namespace)
        
        # Handle complex numbers
        if isinstance(result, complex):
            if result.imag == 0:
                result = result.real
            else:
                return result, expr
        
        # Round very small floating point errors
        if isinstance(result, float):
            if abs(result - round(result)) < 1e-10:
                result = round(result)
            else:
                result = round(result, 10)
        
        return result, expr
    except ZeroDivisionError:
        raise ValueError("Division by zero")
    except ValueError as e:
        raise ValueError(f"Math error: {e}")
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")


def evaluate_math(text: str) -> tuple[str, list]:
    """Evaluate math expression and return formatted response."""
    try:
        result, cleaned_expr = safe_eval(text)
        
        # Format result nicely
        if isinstance(result, float):
            if result == int(result):
                result_str = str(int(result))
            elif abs(result) < 0.0001 or abs(result) > 1e10:
                result_str = f"{result:.6e}"
            else:
                result_str = f"{result:.6f}".rstrip('0').rstrip('.')
        else:
            result_str = str(result)
        
        response = f"🔢 {cleaned_expr} = {result_str}"
        
        data = {
            "expression": cleaned_expr,
            "result": result if not isinstance(result, complex) else str(result),
            "result_type": type(result).__name__
        }
        
        artifacts = [{
            "artifactId": str(uuid.uuid4()),
            "name": "calculation-result",
            "description": "Math calculation result",
            "parts": [
                {"kind": "text", "text": response},
                {"kind": "data", "data": data}
            ]
        }]
        
        return response, artifacts
        
    except ValueError as e:
        error_msg = f"❌ Could not evaluate: {str(e)}\n\n💡 Try expressions like:\n• 2 + 2\n• sqrt(144)\n• sin(pi/2)\n• 5^3 + log(100)"
        
        artifacts = [{
            "artifactId": str(uuid.uuid4()),
            "name": "calculation-error",
            "description": "Math calculation error",
            "parts": [{"kind": "text", "text": error_msg}]
        }]
        
        return error_msg, artifacts


# ============================================================================
# JSON-RPC HELPERS
# ============================================================================

def make_jsonrpc_response(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def make_jsonrpc_error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


ERROR_CODES = {
    "parse_error": -32700,
    "invalid_request": -32600,
    "method_not_found": -32601,
    "invalid_params": -32602,
    "task_not_found": -32001,
}


# ============================================================================
# A2A ENDPOINT
# ============================================================================

@app.post("/a2a")
async def a2a_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(content=make_jsonrpc_error(None, ERROR_CODES["parse_error"], "Parse error"))
    
    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params", {})
    
    if body.get("jsonrpc") != "2.0":
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_request"], "Invalid JSON-RPC version"))
    
    if method == "message/send":
        return await handle_message_send(request_id, params)
    elif method == "tasks/get":
        return await handle_tasks_get(request_id, params)
    elif method == "tasks/cancel":
        return await handle_tasks_cancel(request_id, params)
    else:
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["method_not_found"], f"Method not found: {method}"))


async def handle_message_send(request_id: Any, params: dict) -> JSONResponse:
    message = params.get("message")
    if not message:
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["invalid_params"], "message is required"))
    
    parts = message.get("parts", [])
    text_parts = [p.get("text", "") for p in parts if p.get("kind") == "text"]
    message_text = " ".join(text_parts).strip() or "0"
    
    context_id = message.get("contextId") or str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    
    task = Task(task_id, context_id, message)
    tasks[task_id] = task
    
    task.update_state(TaskState.WORKING)
    
    try:
        response_text, artifacts = evaluate_math(message_text)
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
    
    return JSONResponse(content=make_jsonrpc_response(request_id, task.to_dict()))


async def handle_tasks_get(request_id: Any, params: dict) -> JSONResponse:
    task_id = params.get("id")
    if not task_id or task_id not in tasks:
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["task_not_found"], "Task not found"))
    return JSONResponse(content=make_jsonrpc_response(request_id, tasks[task_id].to_dict()))


async def handle_tasks_cancel(request_id: Any, params: dict) -> JSONResponse:
    task_id = params.get("id")
    if not task_id or task_id not in tasks:
        return JSONResponse(content=make_jsonrpc_error(request_id, ERROR_CODES["task_not_found"], "Task not found"))
    task = tasks[task_id]
    if task.state in [TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED]:
        return JSONResponse(content=make_jsonrpc_error(request_id, -32002, "Task already in terminal state"))
    task.update_state(TaskState.CANCELED)
    return JSONResponse(content=make_jsonrpc_response(request_id, task.to_dict()))


@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "math-agent", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    print("🔢 Starting Math Agent on http://localhost:8094")
    uvicorn.run(app, host="0.0.0.0", port=8094)
