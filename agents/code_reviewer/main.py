"""
Code Reviewer A2A Agent - Reviews code snippets using pattern matching.

Run with: python3 -m uvicorn agents.code_reviewer.main:app --port 8093
"""

import uuid
import re
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
    title="Code Reviewer Agent",
    description="Reviews code snippets and provides feedback",
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
    "name": "Code Reviewer Agent",
    "description": "Analyzes code snippets and provides review feedback including style issues, potential bugs, and improvement suggestions. Uses pattern matching - no LLM required.",
    "url": "http://localhost:8093/a2a",
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
            "id": "review",
            "name": "Code Review",
            "description": "Reviews code for style issues, potential bugs, and suggests improvements.",
            "tags": ["code", "review", "lint", "quality"],
            "examples": [
                "Review this Python code: def foo(x): return x+1",
                "Check this JavaScript: let x = 1; var y = 2;",
                "Review: for i in range(len(arr)): print(arr[i])"
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
# CODE REVIEW LOGIC
# ============================================================================

def review_code(code: str) -> tuple[str, list]:
    """Review code and return feedback."""
    issues = []
    suggestions = []
    
    # Check if this looks like actual code or just a plain message
    code_indicators = ['def ', 'import ', 'print(', 'class ', 'function ', 'var ', 'let ', 'const ',
                       'if(', 'for(', 'while(', '= {', '= [', '=>', '->', '();', '{}', '()', '==',
                       'return ', '#include', 'public ', 'private ', 'void ', 'int ', 'string ']
    is_code = any(indicator in code for indicator in code_indicators) or code.count('\n') > 2
    
    if not is_code:
        summary = "👋 Send me some code and I'll review it!\n\nI can analyze Python, JavaScript, and general code for:\n• Bugs and common mistakes\n• Style issues\n• Performance suggestions\n• Security concerns\n\nJust paste your code and I'll give you a score out of 100."
        artifacts = [{
            "artifactId": str(uuid.uuid4()),
            "name": "code-review",
            "description": "Code review instructions",
            "parts": [
                {"kind": "text", "text": summary},
                {"kind": "data", "data": {"score": None, "is_code": False}}
            ]
        }]
        return summary, artifacts
    
    # Python-specific checks
    if "def " in code or "import " in code or "print(" in code:
        # Check for range(len()) anti-pattern
        if re.search(r'range\s*\(\s*len\s*\(', code):
            issues.append({
                "severity": "warning",
                "type": "style",
                "message": "Consider using enumerate() instead of range(len())"
            })
        
        # Check for mutable default arguments
        if re.search(r'def\s+\w+\s*\([^)]*=\s*(\[\]|\{\})', code):
            issues.append({
                "severity": "error",
                "type": "bug",
                "message": "Mutable default argument detected - this can cause unexpected behavior"
            })
        
        # Check for bare except
        if re.search(r'except\s*:', code):
            issues.append({
                "severity": "warning",
                "type": "style",
                "message": "Bare except clause - consider catching specific exceptions"
            })
        
        # Check for print statements in functions
        if "def " in code and "print(" in code:
            suggestions.append("Consider using logging instead of print statements")
        
        # Check for missing docstrings
        if re.search(r'def\s+\w+\s*\([^)]*\)\s*:', code) and '"""' not in code and "'''" not in code:
            suggestions.append("Consider adding docstrings to functions")
        
        # Check for single-letter variable names
        if re.search(r'\b[a-z]\s*=', code):
            suggestions.append("Consider using more descriptive variable names")
    
    # JavaScript-specific checks
    if "var " in code or "let " in code or "const " in code or "function " in code:
        # Check for var usage
        if "var " in code:
            issues.append({
                "severity": "warning",
                "type": "style",
                "message": "Consider using 'let' or 'const' instead of 'var'"
            })
        
        # Check for == instead of ===
        if re.search(r'[^=!]==[^=]', code):
            issues.append({
                "severity": "warning",
                "type": "bug",
                "message": "Consider using === instead of == for strict equality"
            })
        
        # Check for console.log
        if "console.log" in code:
            suggestions.append("Remove console.log statements before production")
    
    # General checks
    if len(code) > 0:
        lines = code.split('\n')
        
        # Check for long lines
        long_lines = [i+1 for i, line in enumerate(lines) if len(line) > 100]
        if long_lines:
            issues.append({
                "severity": "info",
                "type": "style",
                "message": f"Long lines detected (>100 chars) at lines: {long_lines[:3]}"
            })
        
        # Check for trailing whitespace
        trailing_ws = [i+1 for i, line in enumerate(lines) if line != line.rstrip()]
        if trailing_ws:
            suggestions.append(f"Remove trailing whitespace at lines: {trailing_ws[:3]}")
        
        # Check for TODO/FIXME
        todos = re.findall(r'(TODO|FIXME|XXX|HACK)[:\s].*', code, re.IGNORECASE)
        if todos:
            issues.append({
                "severity": "info",
                "type": "todo",
                "message": f"Found {len(todos)} TODO/FIXME comments"
            })
    
    # Build response
    if not issues and not suggestions:
        summary = "✅ Code looks good! No issues detected."
        score = 100
    else:
        error_count = len([i for i in issues if i["severity"] == "error"])
        warning_count = len([i for i in issues if i["severity"] == "warning"])
        info_count = len([i for i in issues if i["severity"] == "info"])
        
        score = max(0, 100 - (error_count * 20) - (warning_count * 10) - (info_count * 2) - (len(suggestions) * 5))
        
        summary = f"🔍 Code Review Complete\n\nScore: {score}/100\n"
        if error_count:
            summary += f"❌ {error_count} error(s)\n"
        if warning_count:
            summary += f"⚠️ {warning_count} warning(s)\n"
        if info_count:
            summary += f"ℹ️ {info_count} info\n"
        
        if issues:
            summary += "\n📋 Issues:\n"
            for issue in issues:
                icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue["severity"], "•")
                summary += f"  {icon} [{issue['type']}] {issue['message']}\n"
        
        if suggestions:
            summary += "\n💡 Suggestions:\n"
            for sug in suggestions:
                summary += f"  • {sug}\n"
    
    review_data = {
        "score": score,
        "issues": issues,
        "suggestions": suggestions,
        "lines_analyzed": len(code.split('\n')),
        "characters_analyzed": len(code)
    }
    
    artifacts = [{
        "artifactId": str(uuid.uuid4()),
        "name": "code-review",
        "description": "Code review results",
        "parts": [
            {"kind": "text", "text": summary},
            {"kind": "data", "data": review_data}
        ]
    }]
    
    return summary, artifacts


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
    message_text = " ".join(text_parts).strip() or "No code provided"
    
    context_id = message.get("contextId") or str(uuid.uuid4())
    task_id = str(uuid.uuid4())
    
    task = Task(task_id, context_id, message)
    tasks[task_id] = task
    
    task.update_state(TaskState.WORKING)
    
    try:
        response_text, artifacts = review_code(message_text)
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
    return {"status": "healthy", "service": "code-reviewer-agent", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    print("🔍 Starting Code Reviewer Agent on http://localhost:8093")
    uvicorn.run(app, host="0.0.0.0", port=8093)
