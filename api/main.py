"""
A2Apex API Server

FastAPI server for A2A protocol testing and validation.
The API behind "Where AI Agents Earn Trust".
"""

import os
import sys
import uuid
import json
import time
import sqlite3
from typing import Optional
from pathlib import Path
from datetime import datetime
from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Auth module
from api.auth import router as auth_router

# Badges module
from api.badges import router as badges_router

# Payments module (Stripe)
from api.payments import router as payments_router

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core import (
    # Validator
    AgentCardValidator,
    fetch_and_validate_agent_card,
    
    # Task Tester
    run_task_test,
    TaskTester,
    
    # Protocol Checker
    run_compliance_check,
    
    # Scenarios
    list_all_scenarios,
    get_scenario,
    get_quick_test_scenarios,
    
    # State Machine
    validate_transition,
    validate_task_history,
    get_valid_next_states,
    get_state_machine_diagram,
    
    # Live Tester
    run_live_tests,
    LiveTester,
    
    # Auth Tester
    run_auth_tests,
    
    # Error Tester
    run_error_tests,
    
    # Streaming Tester
    run_streaming_tests,
    
    # Performance Tester
    run_perf_tests
)


# ============================================================================
# RATE LIMITING & API KEY AUTH
# ============================================================================

# In-memory rate limit tracking
# Structure: {identifier: [(timestamp, count), ...]}
rate_limit_store: dict[str, list[tuple[float, int]]] = defaultdict(list)

# API keys config
API_KEYS_PATH = Path(__file__).parent.parent / "data" / "api_keys.json"
API_KEYS: dict[str, dict] = {}

# Rate limit settings
FREE_TIER_LIMIT = 10  # requests per minute
PRO_TIER_LIMIT = 100  # requests per minute
RATE_LIMIT_WINDOW = 60  # seconds

# Public endpoints that don't require auth or rate limiting
PUBLIC_ENDPOINTS = {"/", "/api/health", "/api/demo", "/api/docs", "/api/redoc", "/openapi.json", "/api/waitlist", "/api/registry", "/api/registry-page", "/api/webhook", "/api/stripe-config"}


def load_api_keys():
    """Load API keys from JSON file."""
    global API_KEYS
    if API_KEYS_PATH.exists():
        try:
            with open(API_KEYS_PATH) as f:
                data = json.load(f)
                API_KEYS = data.get("keys", {})
        except Exception as e:
            print(f"Warning: Could not load API keys: {e}")
            API_KEYS = {}
    else:
        API_KEYS = {}


def get_api_key(request: Request) -> Optional[str]:
    """Extract API key from request (header or query param)."""
    # Check X-API-Key header first
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return api_key
    
    # Check query parameter
    api_key = request.query_params.get("api_key")
    if api_key:
        return api_key
    
    return None


def get_rate_limit(api_key: Optional[str]) -> int:
    """Get rate limit for API key (or free tier if no key)."""
    if api_key and api_key in API_KEYS:
        return API_KEYS[api_key].get("rate_limit", PRO_TIER_LIMIT)
    return FREE_TIER_LIMIT


def get_client_identifier(request: Request, api_key: Optional[str]) -> str:
    """Get identifier for rate limiting (API key or IP)."""
    if api_key and api_key in API_KEYS:
        return f"key:{api_key}"
    
    # Fall back to IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    
    client_host = request.client.host if request.client else "unknown"
    return f"ip:{client_host}"


def check_rate_limit(identifier: str, limit: int) -> tuple[bool, int, int]:
    """
    Check if request is within rate limit.
    Returns: (allowed, remaining, reset_time)
    """
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    
    # Clean old entries
    rate_limit_store[identifier] = [
        (ts, count) for ts, count in rate_limit_store[identifier]
        if ts > window_start
    ]
    
    # Count requests in window
    request_count = sum(count for _, count in rate_limit_store[identifier])
    
    if request_count >= limit:
        # Calculate reset time
        if rate_limit_store[identifier]:
            oldest = min(ts for ts, _ in rate_limit_store[identifier])
            reset_time = int(oldest + RATE_LIMIT_WINDOW)
        else:
            reset_time = int(now + RATE_LIMIT_WINDOW)
        return False, 0, reset_time
    
    # Add this request
    rate_limit_store[identifier].append((now, 1))
    remaining = limit - request_count - 1
    reset_time = int(now + RATE_LIMIT_WINDOW)
    
    return True, remaining, reset_time


# Load API keys on startup
load_api_keys()


# ============================================================================
# TEST USAGE TRACKING (Free Tier 3-Test Limit)
# ============================================================================

TEST_USAGE_DB_PATH = Path(__file__).parent.parent / "data" / "test_usage.db"

# Free tier limits
FREE_TESTS_PER_MONTH = 5
ANON_TESTS_TOTAL = 5  # Anonymous users get 3 total tests ever


def init_test_usage_db():
    """Initialize the test usage database."""
    TEST_USAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(TEST_USAGE_DB_PATH)
    cursor = conn.cursor()
    
    # Table for tracking by user (logged in users)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_test_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL,
            month TEXT NOT NULL,
            test_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE(user_id, month)
        )
    """)
    
    # Table for tracking by IP (anonymous users)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS anon_test_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip_address TEXT UNIQUE NOT NULL,
            test_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    
    conn.commit()
    conn.close()


# Initialize on module load
init_test_usage_db()


def get_client_ip(request: Request) -> str:
    """Get client IP address from request."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else "unknown"


def get_user_plan(request: Request) -> tuple[Optional[str], str]:
    """
    Get user ID and plan from request.
    Returns (user_id, plan) where plan is 'free', 'pro', or 'enterprise'.
    If user_id is None, user is anonymous.
    """
    # Check for API key first
    api_key = get_api_key(request)
    if api_key and api_key in API_KEYS:
        key_data = API_KEYS[api_key]
        return key_data.get("user_id", api_key), key_data.get("plan", "pro")
    
    # Check for JWT auth token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            from api.auth import SECRET_KEY, ALGORITHM, get_user_by_id
            from jose import jwt
            token = auth_header.split(" ", 1)[1]
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = int(payload.get("sub", 0))
            if user_id:
                user = get_user_by_id(user_id)
                if user:
                    return str(user_id), user.get("plan", "free")
        except Exception:
            pass
    
    return None, "free"


def check_test_limit(request: Request) -> tuple[bool, int, str]:
    """
    Check if user can run a test based on their plan and usage.
    
    Returns: (allowed, remaining, message)
    """
    user_id, plan = get_user_plan(request)
    
    # Pro and Enterprise have unlimited tests
    if plan in ("pro", "enterprise"):
        return True, -1, "Unlimited tests"
    
    conn = sqlite3.connect(TEST_USAGE_DB_PATH)
    cursor = conn.cursor()
    
    if user_id:
        # Logged in user - check monthly usage
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        cursor.execute("""
            SELECT test_count FROM user_test_usage 
            WHERE user_id = ? AND month = ?
        """, (user_id, current_month))
        row = cursor.fetchone()
        
        test_count = row[0] if row else 0
        remaining = FREE_TESTS_PER_MONTH - test_count
        
        conn.close()
        
        if test_count >= FREE_TESTS_PER_MONTH:
            return False, 0, f"You've used all {FREE_TESTS_PER_MONTH} free tests this month."
        
        return True, remaining, f"{remaining} tests remaining this month"
    
    else:
        # Anonymous user - check IP-based total usage
        ip_address = get_client_ip(request)
        
        cursor.execute("""
            SELECT test_count FROM anon_test_usage WHERE ip_address = ?
        """, (ip_address,))
        row = cursor.fetchone()
        
        test_count = row[0] if row else 0
        remaining = ANON_TESTS_TOTAL - test_count
        
        conn.close()
        
        if test_count >= ANON_TESTS_TOTAL:
            return False, 0, f"You've used all {ANON_TESTS_TOTAL} free tests. Sign up for more!"
        
        return True, remaining, f"{remaining} tests remaining"


def record_test_usage(request: Request) -> None:
    """Record that a test was run."""
    user_id, plan = get_user_plan(request)
    
    # Don't count for paid plans
    if plan in ("pro", "enterprise"):
        return
    
    conn = sqlite3.connect(TEST_USAGE_DB_PATH)
    cursor = conn.cursor()
    
    if user_id:
        # Logged in user - increment monthly count
        current_month = datetime.utcnow().strftime("%Y-%m")
        
        cursor.execute("""
            INSERT INTO user_test_usage (user_id, month, test_count)
            VALUES (?, ?, 1)
            ON CONFLICT(user_id, month) 
            DO UPDATE SET test_count = test_count + 1
        """, (user_id, current_month))
    else:
        # Anonymous user - increment IP-based count
        ip_address = get_client_ip(request)
        now = datetime.utcnow().isoformat() + "Z"
        
        cursor.execute("""
            INSERT INTO anon_test_usage (ip_address, test_count, created_at)
            VALUES (?, 1, ?)
            ON CONFLICT(ip_address) 
            DO UPDATE SET test_count = test_count + 1
        """, (ip_address, now))
    
    conn.commit()
    conn.close()


def free_limit_error_response():
    """Return the standard free limit reached error response."""
    return JSONResponse(
        status_code=403,
        content={
            "error": "free_limit_reached",
            "message": "You've used all 5 free tests this month. Upgrade to Pro for unlimited testing.",
            "upgrade_url": "https://app.a2apex.io"
        }
    )


def get_test_usage_info(request: Request) -> dict:
    """Get test usage info for the current user."""
    user_id, plan = get_user_plan(request)
    
    if plan in ("pro", "enterprise"):
        return {"plan": plan, "used": 0, "limit": -1, "remaining": -1, "unlimited": True}
    
    conn = sqlite3.connect(TEST_USAGE_DB_PATH)
    cursor = conn.cursor()
    
    if user_id:
        current_month = datetime.utcnow().strftime("%Y-%m")
        cursor.execute("SELECT test_count FROM user_test_usage WHERE user_id = ? AND month = ?", (user_id, current_month))
        row = cursor.fetchone()
        used = row[0] if row else 0
    else:
        ip = request.client.host if request.client else "unknown"
        cursor.execute("SELECT test_count FROM anon_test_usage WHERE ip_address = ?", (ip,))
        row = cursor.fetchone()
        used = row[0] if row else 0
    
    conn.close()
    return {"plan": "free", "used": used, "limit": FREE_TESTS_PER_MONTH, "remaining": max(0, FREE_TESTS_PER_MONTH - used), "unlimited": False}


# ============================================================================
# APP SETUP
# ============================================================================

app = FastAPI(
    title="A2Apex",
    description="Where AI Agents Earn Trust - A2A Protocol Testing Tool",
    version="0.2.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Include auth router
app.include_router(auth_router)

# Include badges router
app.include_router(badges_router)

# Include payments router (Stripe)
app.include_router(payments_router)

# Sample agent proxy — allows testing from external devices
import httpx

@app.api_route("/sample-agent/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy_sample_agent(request: Request, path: str):
    """Proxy requests to the local sample A2A agent on port 8092."""
    async with httpx.AsyncClient() as client:
        url = f"http://localhost:8092/{path}"
        body = await request.body()
        headers = {k: v for k, v in request.headers.items() 
                   if k.lower() not in ('host', 'transfer-encoding')}
        resp = await client.request(
            method=request.method,
            url=url,
            content=body,
            headers=headers,
            timeout=30.0
        )
        return JSONResponse(content=resp.json(), status_code=resp.status_code)

# CORS middleware for web UI - allow all origins (dev tool)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
)


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Rate limiting middleware."""
    path = request.url.path
    
    # Skip rate limiting for public endpoints
    if path in PUBLIC_ENDPOINTS or path.startswith("/api/docs") or path.startswith("/api/redoc") or path.startswith("/api/badge/") or path.startswith("/api/registry"):
        return await call_next(request)
    
    # Handle CORS preflight
    if request.method == "OPTIONS":
        return await call_next(request)
    
    # Get API key and rate limit
    api_key = get_api_key(request)
    limit = get_rate_limit(api_key)
    identifier = get_client_identifier(request, api_key)
    
    # Check rate limit
    allowed, remaining, reset_time = check_rate_limit(identifier, limit)
    
    if not allowed:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Too Many Requests",
                "message": f"Rate limit exceeded. Limit: {limit} requests per minute.",
                "retry_after": reset_time - int(time.time())
            },
            headers={
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time),
                "Retry-After": str(reset_time - int(time.time()))
            }
        )
    
    # Process request
    response = await call_next(request)
    
    # Add rate limit headers
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_time)
    
    return response


# In-memory store for test reports (would be Redis/DB in production)
test_reports: dict[str, dict] = {}


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class AgentCardValidationRequest(BaseModel):
    """Request to validate an Agent Card."""
    url: Optional[str] = Field(None, description="URL to fetch the Agent Card from")
    agent_card_json: Optional[dict] = Field(None, alias="json", description="Agent Card JSON to validate directly")


class TaskTestRequest(BaseModel):
    """Request to test task execution."""
    agent_url: str = Field(..., description="Base URL of the A2A agent")
    message: str = Field("Hello, this is a test message.", description="Message to send")
    auth_header: Optional[str] = Field(None, description="Authorization header value")
    full_lifecycle: bool = Field(False, description="Run full lifecycle test with polling")


class ComplianceCheckRequest(BaseModel):
    """Request to run compliance check."""
    agent_url: str = Field(..., description="Base URL of the A2A agent")
    auth_header: Optional[str] = Field(None, description="Authorization header value")
    timeout: float = Field(30.0, description="Request timeout in seconds")


class ScenarioRunRequest(BaseModel):
    """Request to run a test scenario."""
    agent_url: str = Field(..., description="Base URL of the A2A agent")
    scenario_id: str = Field(..., description="ID of the scenario to run")
    auth_header: Optional[str] = Field(None, description="Authorization header value")


class QuickTestRequest(BaseModel):
    """Request for quick test suite."""
    agent_url: str = Field(..., description="Base URL of the A2A agent")
    auth_header: Optional[str] = Field(None, description="Authorization header value")


class LiveTestRequest(BaseModel):
    """Request to run live endpoint tests."""
    agent_url: str = Field(..., description="Base URL of the A2A agent")
    auth_header: Optional[str] = Field(None, description="Authorization header value")
    timeout: float = Field(30.0, description="Request timeout in seconds")
    tests: Optional[list[str]] = Field(None, description="Specific tests to run (all if empty)")


class StateValidationRequest(BaseModel):
    """Request to validate state transitions."""
    states: Optional[list[str]] = Field(None, description="List of states to validate in order")
    from_state: Optional[str] = Field(None, description="Single from state (for single transition)")
    to_state: Optional[str] = Field(None, description="Single to state (for single transition)")


class ChatRequest(BaseModel):
    """Request to send a message to an agent."""
    agent_url: str = Field(..., description="Base URL of the A2A agent")
    message: str = Field(..., description="Message text to send")
    context_id: Optional[str] = Field(None, description="Context ID for conversation continuity")
    task_id: Optional[str] = Field(None, description="Task ID for follow-up messages")
    auth_header: Optional[str] = Field(None, description="Authorization header value")
    timeout: float = Field(30.0, description="Request timeout in seconds")


# ============================================================================
# CORE API ENDPOINTS
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "a2apex",
        "version": "0.2.0",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@app.get("/api/usage")
async def get_usage(request: Request):
    """Get current user's test usage and remaining tests."""
    return get_test_usage_info(request)


# ============================================================================
# WAITLIST
# ============================================================================

import sqlite3

WAITLIST_DB_PATH = Path(__file__).parent.parent / "data" / "waitlist.db"


def init_waitlist_db():
    """Initialize the waitlist database."""
    WAITLIST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(WAITLIST_DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS waitlist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# Initialize DB on startup
init_waitlist_db()


class WaitlistRequest(BaseModel):
    """Request to join the waitlist."""
    email: str = Field(..., description="Email address to add to waitlist")


@app.post("/api/waitlist")
async def join_waitlist(request: WaitlistRequest):
    """
    Add an email to the waitlist.
    
    Stores the email in SQLite for later use.
    """
    import re
    
    # Validate email format
    email = request.email.strip().lower()
    if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    
    try:
        conn = sqlite3.connect(WAITLIST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO waitlist (email, created_at) VALUES (?, ?)",
            (email, datetime.utcnow().isoformat() + "Z")
        )
        conn.commit()
        
        # Check if it was actually inserted or already existed
        cursor.execute("SELECT id FROM waitlist WHERE email = ?", (email,))
        row = cursor.fetchone()
        conn.close()
        
        return {
            "success": True,
            "message": "You're on the list!",
            "email": email
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add to waitlist: {str(e)}")


@app.get("/api/waitlist/count")
async def get_waitlist_count():
    """Get the current waitlist count."""
    try:
        conn = sqlite3.connect(WAITLIST_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM waitlist")
        count = cursor.fetchone()[0]
        conn.close()
        return {"count": count}
    except Exception as e:
        return {"count": 0, "error": str(e)}


@app.post("/api/validate/agent-card")
async def validate_agent_card(request: AgentCardValidationRequest):
    """
    Validate an Agent Card against the A2A specification.
    
    Provide either a URL to fetch the card from, or the JSON directly.
    Returns detailed validation results with errors, warnings, and suggestions.
    """
    if request.url:
        # Fetch and validate from URL
        report = await fetch_and_validate_agent_card(request.url)
        return report.to_dict()
    
    elif request.agent_card_json:
        # Validate provided JSON
        validator = AgentCardValidator()
        report = validator.validate(request.agent_card_json)
        return report.to_dict()
    
    else:
        raise HTTPException(
            status_code=400,
            detail="Must provide either 'url' or 'json' field"
        )


@app.post("/api/test/task")
async def test_task(request: TaskTestRequest, req: Request):
    """
    Send a test task to an A2A agent and validate the response.
    """
    # Check test limit for free users
    allowed, remaining, message = check_test_limit(req)
    if not allowed:
        return free_limit_error_response()
    
    try:
        report = await run_task_test(
            agent_url=request.agent_url,
            message=request.message,
            auth_header=request.auth_header,
            full_lifecycle=request.full_lifecycle
        )
        
        # Record usage after successful test
        record_test_usage(req)
        
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/check/compliance")
async def check_compliance(request: ComplianceCheckRequest, req: Request):
    """
    Run a comprehensive compliance check against an A2A agent.
    
    Tests multiple aspects of A2A protocol compliance including:
    - Agent Card accessibility and validity
    - Message sending and response format
    - Task lifecycle handling
    - Error handling
    - Security configuration
    """
    # Check test limit for free users
    allowed, remaining, message = check_test_limit(req)
    if not allowed:
        return free_limit_error_response()
    
    try:
        report = await run_compliance_check(
            agent_url=request.agent_url,
            auth_header=request.auth_header,
            timeout=request.timeout
        )
        
        # Record usage after successful test
        record_test_usage(req)
        
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LIVE TESTING ENDPOINTS (NEW)
# ============================================================================

@app.post("/api/live-test")
async def run_live_test(request: LiveTestRequest, req: Request):
    """
    Run live endpoint tests against an A2A agent.
    
    This actually calls the agent endpoints and validates responses.
    Tests include:
    - Agent Card fetch
    - message/send
    - tasks/get
    - tasks/cancel
    - Streaming (if supported)
    - Error handling
    """
    # Check test limit for free users
    allowed, remaining, message = check_test_limit(req)
    if not allowed:
        return free_limit_error_response()
    
    try:
        report = await run_live_tests(
            agent_url=request.agent_url,
            auth_header=request.auth_header,
            timeout=request.timeout
        )
        
        # Record usage after successful test
        record_test_usage(req)
        
        # Store report for retrieval
        report_id = str(uuid.uuid4())
        test_reports[report_id] = {
            "id": report_id,
            "created_at": datetime.utcnow().isoformat() + "Z",
            **report.to_dict()
        }
        
        result = report.to_dict()
        result["report_id"] = report_id
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/test-report/{report_id}")
async def get_test_report(report_id: str):
    """
    Get a previously generated test report by ID.
    """
    if report_id not in test_reports:
        raise HTTPException(status_code=404, detail="Report not found")
    
    return test_reports[report_id]


@app.get("/api/test-reports")
async def list_test_reports(limit: int = 20):
    """
    List recent test reports.
    """
    reports = list(test_reports.values())
    reports.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return {
        "reports": reports[:limit],
        "total": len(reports)
    }


# ============================================================================
# SPECIALIZED TEST ENDPOINTS (NEW)
# ============================================================================

class TestRequest(BaseModel):
    """Base request for specialized tests."""
    agent_url: str = Field(..., description="Base URL of the A2A agent")
    auth_header: Optional[str] = Field(None, description="Authorization header value")
    timeout: float = Field(30.0, description="Request timeout in seconds")


@app.post("/api/test/auth")
async def run_auth_test(request: TestRequest):
    """
    Run authentication and security tests against an A2A agent.
    
    Tests:
    - Security scheme declarations
    - API key authentication
    - HTTP bearer token auth
    - OAuth2 flow declarations
    - Unauthenticated request handling
    - HTTPS enforcement
    """
    try:
        report = await run_auth_tests(
            agent_url=request.agent_url,
            timeout=request.timeout
        )
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test/errors")
async def run_error_test(request: TestRequest):
    """
    Run error handling tests against an A2A agent.
    
    Tests how the agent handles:
    - Malformed JSON
    - Invalid JSON-RPC format
    - Unknown methods
    - Invalid parameters
    - Non-existent tasks
    - Oversized payloads
    
    Validates JSON-RPC 2.0 error response compliance.
    """
    try:
        report = await run_error_tests(
            agent_url=request.agent_url,
            timeout=request.timeout
        )
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test/streaming")
async def run_streaming_test(request: TestRequest):
    """
    Run streaming (SSE) tests against an A2A agent.
    
    Tests:
    - SSE connection
    - Event format validation
    - State transition order
    - Artifact streaming
    - Stream termination
    - Timeout handling
    """
    try:
        report = await run_streaming_tests(
            agent_url=request.agent_url,
            timeout=request.timeout
        )
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test/performance")
async def run_performance_test(request: TestRequest):
    """
    Run performance tests against an A2A agent.
    
    Tests:
    - Agent Card fetch latency
    - Message send latency
    - Concurrent request handling
    - Task isolation
    - Cold vs warm start comparison
    """
    try:
        report = await run_perf_tests(
            agent_url=request.agent_url,
            timeout=request.timeout
        )
        return report.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/test/full")
async def run_full_compliance_suite(request: TestRequest, req: Request):
    """
    Run the FULL compliance test suite against an A2A agent.
    
    Runs ALL available tests:
    - Agent Card Validation
    - Live Endpoint Tests
    - Auth & Security Tests
    - Error Handling Tests
    - Streaming Tests
    - Performance Tests
    
    Returns results grouped by category.
    """
    import asyncio
    
    # Check test limit
    allowed, remaining, message = check_test_limit(req)
    if not allowed:
        return free_limit_error_response()
    record_test_usage(req)
    
    try:
        # Run all test suites concurrently
        live_task = run_live_tests(request.agent_url, request.auth_header, request.timeout)
        auth_task = run_auth_tests(request.agent_url, timeout=request.timeout)
        error_task = run_error_tests(request.agent_url, timeout=request.timeout)
        streaming_task = run_streaming_tests(request.agent_url, timeout=request.timeout)
        perf_task = run_perf_tests(request.agent_url, timeout=request.timeout)
        
        results = await asyncio.gather(
            live_task, auth_task, error_task, streaming_task, perf_task,
            return_exceptions=True
        )
        
        live_report, auth_report, error_report, streaming_report, perf_report = results
        
        # Build combined report
        categories = {}
        total_passed = 0
        total_failed = 0
        total_warnings = 0
        total_skipped = 0
        total_tests = 0
        
        def add_category(name: str, report, icon: str):
            nonlocal total_passed, total_failed, total_warnings, total_skipped, total_tests
            
            if isinstance(report, Exception):
                categories[name] = {
                    "icon": icon,
                    "error": str(report),
                    "results": []
                }
                return
            
            report_dict = report.to_dict()
            summary = report_dict.get("summary", {})
            
            categories[name] = {
                "icon": icon,
                "summary": summary,
                "results": report_dict.get("results", [])
            }
            
            total_passed += summary.get("passed", 0)
            total_failed += summary.get("failed", 0)
            total_warnings += summary.get("warnings", 0)
            total_skipped += summary.get("skipped", 0)
            total_tests += summary.get("total", 0)
        
        add_category("Live Endpoint Tests", live_report, "⚡")
        add_category("Auth & Security", auth_report, "🔒")
        add_category("Error Handling", error_report, "❌")
        add_category("Streaming", streaming_report, "📡")
        add_category("Performance", perf_report, "⏱️")
        
        # Auto-attach fix guidance to any failed/warning result missing it
        from core.fix_guidance import get_fix_for_test
        for cat_name, cat_data in categories.items():
            for result in cat_data.get("results", []):
                if result.get("status") in ("failed", "warning") and not result.get("fix"):
                    fix = get_fix_for_test(result.get("test_name", ""), result.get("error", ""), result.get("message", ""))
                    if fix:
                        result["fix"] = fix.fix
                        result["code_snippet"] = fix.code_snippet
                        result["spec_url"] = fix.spec_url
        
        # Calculate overall score
        overall_score = (total_passed / total_tests * 100) if total_tests > 0 else 0
        
        return {
            "agent_url": request.agent_url,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "summary": {
                "total": total_tests,
                "passed": total_passed,
                "failed": total_failed,
                "warnings": total_warnings,
                "skipped": total_skipped,
                "score": round(overall_score, 1)
            },
            "categories": categories
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CHAT ENDPOINT (Debug Chat)
# ============================================================================

@app.post("/api/chat")
async def chat_with_agent(request: ChatRequest):
    """
    Send a chat message to an A2A agent and return structured results.
    
    This endpoint wraps the message/send JSON-RPC call and returns:
    - The raw request JSON
    - The raw response JSON
    - Parsed result (task ID, status, agent message, artifacts)
    """
    import httpx
    
    # Build the JSON-RPC request
    message_id = str(uuid.uuid4())
    jsonrpc_request = {
        "jsonrpc": "2.0",
        "id": message_id,
        "method": "message/send",
        "params": {
            "message": {
                "role": "user",
                "messageId": message_id,
                "parts": [{"kind": "text", "text": request.message}],
                "kind": "message"
            },
            "configuration": {
                "acceptedOutputModes": ["text/plain", "application/json"],
                "blocking": True
            }
        }
    }
    
    # Add context/task IDs if provided
    if request.context_id:
        jsonrpc_request["params"]["message"]["contextId"] = request.context_id
    if request.task_id:
        jsonrpc_request["params"]["message"]["taskId"] = request.task_id
    
    # Build headers
    headers = {
        "Content-Type": "application/json",
        "A2A-Version": "0.3"
    }
    if request.auth_header:
        headers["Authorization"] = request.auth_header
    
    # Determine A2A endpoint URL
    base_url = request.agent_url.rstrip("/")
    
    # Rewrite proxied sample-agent URL back to localhost
    if "/sample-agent/" in base_url or base_url.endswith("/sample-agent"):
        base_url = base_url.replace("https://app.a2apex.io/sample-agent", "http://localhost:8092")
        base_url = base_url.replace("http://app.a2apex.io/sample-agent", "http://localhost:8092")
    
    if base_url.endswith("/a2a"):
        a2a_url = base_url
    else:
        a2a_url = f"{base_url}/a2a"
    
    # Send request
    start_time = datetime.utcnow()
    try:
        async with httpx.AsyncClient(timeout=request.timeout) as client:
            response = await client.post(
                a2a_url,
                json=jsonrpc_request,
                headers=headers
            )
            response_json = response.json()
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
    except httpx.TimeoutException:
        return {
            "success": False,
            "error": "Request timed out",
            "raw_request": jsonrpc_request,
            "raw_response": None,
            "duration_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "raw_request": jsonrpc_request,
            "raw_response": None,
            "duration_ms": (datetime.utcnow() - start_time).total_seconds() * 1000
        }
    
    # Parse the response
    result = {
        "success": True,
        "raw_request": jsonrpc_request,
        "raw_response": response_json,
        "duration_ms": round(duration_ms, 2),
        "http_status": response.status_code,
        "parsed": {}
    }
    
    # Extract parsed data
    if "error" in response_json:
        result["success"] = False
        result["parsed"]["error"] = response_json["error"]
    elif "result" in response_json:
        res = response_json["result"]
        
        # Handle task response
        if "task" in res:
            task = res["task"]
            result["parsed"]["task_id"] = task.get("id")
            result["parsed"]["context_id"] = task.get("contextId")
            result["parsed"]["status"] = task.get("status", {}).get("state")
            
            # Extract artifacts
            artifacts = task.get("artifacts", [])
            result["parsed"]["artifacts"] = []
            for artifact in artifacts:
                art_info = {
                    "id": artifact.get("artifactId"),
                    "name": artifact.get("name"),
                    "parts": []
                }
                for part in artifact.get("parts", []):
                    if part.get("kind") == "text":
                        art_info["parts"].append({"type": "text", "content": part.get("text")})
                    elif part.get("kind") == "data":
                        art_info["parts"].append({"type": "data", "content": part.get("data")})
                    elif part.get("kind") == "file":
                        art_info["parts"].append({"type": "file", "content": part.get("file")})
                result["parsed"]["artifacts"].append(art_info)
            
            # Extract agent message from history
            history = task.get("history", [])
            agent_messages = [m for m in history if m.get("role") == "agent"]
            if agent_messages:
                last_agent_msg = agent_messages[-1]
                text_parts = [p.get("text", "") for p in last_agent_msg.get("parts", []) if p.get("kind") == "text"]
                result["parsed"]["agent_message"] = " ".join(text_parts)
        
        # Handle direct message response
        elif "message" in res:
            msg = res["message"]
            text_parts = [p.get("text", "") for p in msg.get("parts", []) if p.get("kind") == "text"]
            result["parsed"]["agent_message"] = " ".join(text_parts)
            result["parsed"]["context_id"] = msg.get("contextId")
    
    return result


@app.post("/api/demo")
async def run_demo_tests():
    """
    Run demo tests against the sample agent at localhost:8092.
    
    Returns a sequence of test results showing the agent capabilities.
    """
    import httpx
    
    demo_url = "http://localhost:8092"
    results = []
    
    # Test 1: Fetch Agent Card
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{demo_url}/.well-known/agent-card.json")
            if response.status_code == 200:
                card = response.json()
                results.append({
                    "test": "fetch_agent_card",
                    "name": "Fetch Agent Card",
                    "status": "passed",
                    "message": f"Found agent: {card.get('name')}",
                    "details": {
                        "name": card.get("name"),
                        "description": card.get("description"),
                        "skills": [s.get("name") for s in card.get("skills", [])],
                        "capabilities": card.get("capabilities")
                    }
                })
            else:
                results.append({
                    "test": "fetch_agent_card",
                    "name": "Fetch Agent Card",
                    "status": "failed",
                    "message": f"HTTP {response.status_code}"
                })
    except Exception as e:
        results.append({
            "test": "fetch_agent_card",
            "name": "Fetch Agent Card",
            "status": "failed",
            "message": f"Connection failed: {e}. Make sure sample agent is running on port 8092."
        })
        return {"success": False, "results": results, "error": "Sample agent not running"}
    
    # Test 2: Echo skill
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            req = {
                "jsonrpc": "2.0",
                "id": "echo-test",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "messageId": "echo-test-msg",
                        "parts": [{"kind": "text", "text": "Echo: Hello A2Apex!"}],
                        "kind": "message"
                    }
                }
            }
            response = await client.post(f"{demo_url}/a2a", json=req)
            resp_json = response.json()
            
            result = resp_json.get("result", {})
            # A2A spec: result should be the Task directly OR wrapped in {"task": ...}
            task = result.get("task", result) if isinstance(result, dict) else None
            
            if task and "id" in task and "status" in task:
                status = task.get("status", {}).get("state")
                artifacts = task.get("artifacts", [])
                
                results.append({
                    "test": "echo_skill",
                    "name": "Echo Skill",
                    "status": "passed" if status == "completed" else "warning",
                    "message": f"Task {status}, got {len(artifacts)} artifact(s)",
                    "details": {
                        "task_id": task.get("id"),
                        "artifacts": artifacts
                    }
                })
            else:
                results.append({
                    "test": "echo_skill",
                    "name": "Echo Skill",
                    "status": "failed",
                    "message": resp_json.get("error", {}).get("message", "Unknown error")
                })
    except Exception as e:
        results.append({
            "test": "echo_skill",
            "name": "Echo Skill",
            "status": "failed",
            "message": str(e)
        })
    
    # Test 3: Weather skill
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            req = {
                "jsonrpc": "2.0",
                "id": "weather-test",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "messageId": "weather-test-msg",
                        "parts": [{"kind": "text", "text": "Weather in Tokyo"}],
                        "kind": "message"
                    }
                }
            }
            response = await client.post(f"{demo_url}/a2a", json=req)
            resp_json = response.json()
            
            result = resp_json.get("result", {})
            # A2A spec: result should be the Task directly OR wrapped in {"task": ...}
            task = result.get("task", result) if isinstance(result, dict) else None
            
            if task and "id" in task and "status" in task:
                status = task.get("status", {}).get("state")
                artifacts = task.get("artifacts", [])
                
                # Check for weather data
                has_data = False
                for art in artifacts:
                    for part in art.get("parts", []):
                        if part.get("kind") == "data":
                            has_data = True
                
                results.append({
                    "test": "weather_skill",
                    "name": "Weather Skill",
                    "status": "passed" if status == "completed" and has_data else "warning",
                    "message": f"Task {status}, structured data: {'Yes' if has_data else 'No'}",
                    "details": {
                        "task_id": task.get("id"),
                        "artifacts": artifacts
                    }
                })
            else:
                results.append({
                    "test": "weather_skill",
                    "name": "Weather Skill",
                    "status": "failed",
                    "message": resp_json.get("error", {}).get("message", "Unknown error")
                })
    except Exception as e:
        results.append({
            "test": "weather_skill",
            "name": "Weather Skill",
            "status": "failed",
            "message": str(e)
        })
    
    # Test 4: tasks/get
    if len(results) >= 2 and results[1].get("details", {}).get("task_id"):
        task_id = results[1]["details"]["task_id"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                req = {
                    "jsonrpc": "2.0",
                    "id": "get-test",
                    "method": "tasks/get",
                    "params": {"id": task_id}
                }
                response = await client.post(f"{demo_url}/a2a", json=req)
                resp_json = response.json()
                
                result = resp_json.get("result", {})
                # A2A spec: result should be the Task directly OR wrapped in {"task": ...}
                task = result.get("task", result) if isinstance(result, dict) else None
                
                if task and "id" in task and "status" in task:
                    results.append({
                        "test": "tasks_get",
                        "name": "tasks/get",
                        "status": "passed",
                        "message": f"Successfully retrieved task {task_id[:8]}..."
                    })
                else:
                    results.append({
                        "test": "tasks_get",
                        "name": "tasks/get",
                        "status": "failed",
                        "message": resp_json.get("error", {}).get("message", "Unknown error")
                    })
        except Exception as e:
            results.append({
                "test": "tasks_get",
                "name": "tasks/get",
                "status": "failed",
                "message": str(e)
            })
    
    # Test 5: tasks/cancel (create a new task just to cancel it)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Create a task
            req = {
                "jsonrpc": "2.0",
                "id": "cancel-setup",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "messageId": "cancel-test-msg",
                        "parts": [{"kind": "text", "text": "Test for cancel"}],
                        "kind": "message"
                    }
                }
            }
            response = await client.post(f"{demo_url}/a2a", json=req)
            resp_json = response.json()
            
            # A2A spec: result should be the Task directly OR wrapped in {"task": ...}
            result = resp_json.get("result", {})
            task = result.get("task", result) if isinstance(result, dict) else None
            task_id = task.get("id") if task and isinstance(task, dict) else None
            
            if task_id:
                # Try to cancel (will fail because task is already completed - that's expected)
                cancel_req = {
                    "jsonrpc": "2.0",
                    "id": "cancel-test",
                    "method": "tasks/cancel",
                    "params": {"id": task_id}
                }
                cancel_response = await client.post(f"{demo_url}/a2a", json=cancel_req)
                cancel_json = cancel_response.json()
                
                # Either success (rare) or "task already completed" error (expected)
                if "error" in cancel_json:
                    err_code = cancel_json["error"].get("code")
                    if err_code == -32002:  # TaskNotCancelableError
                        results.append({
                            "test": "tasks_cancel",
                            "name": "tasks/cancel",
                            "status": "passed",
                            "message": "Correctly rejected cancel on completed task"
                        })
                    else:
                        results.append({
                            "test": "tasks_cancel",
                            "name": "tasks/cancel",
                            "status": "warning",
                            "message": cancel_json["error"].get("message", "Unknown error")
                        })
                else:
                    results.append({
                        "test": "tasks_cancel",
                        "name": "tasks/cancel",
                        "status": "passed",
                        "message": "Task canceled successfully"
                    })
    except Exception as e:
        results.append({
            "test": "tasks_cancel",
            "name": "tasks/cancel",
            "status": "failed",
            "message": str(e)
        })
    
    # Test 6: Error handling - Unknown method
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            req = {
                "jsonrpc": "2.0",
                "id": "error-test",
                "method": "nonexistent/method",
                "params": {}
            }
            response = await client.post(f"{demo_url}/a2a", json=req)
            resp_json = response.json()
            
            if "error" in resp_json:
                error_code = resp_json["error"].get("code")
                if error_code == -32601:  # Method not found
                    results.append({
                        "test": "error_method_not_found",
                        "name": "Error: Method Not Found",
                        "status": "passed",
                        "message": f"Correctly returns -32601 for unknown method"
                    })
                else:
                    results.append({
                        "test": "error_method_not_found",
                        "name": "Error: Method Not Found",
                        "status": "warning",
                        "message": f"Returns error but wrong code: {error_code}"
                    })
            else:
                results.append({
                    "test": "error_method_not_found",
                    "name": "Error: Method Not Found",
                    "status": "failed",
                    "message": "No error returned for unknown method"
                })
    except Exception as e:
        results.append({
            "test": "error_method_not_found",
            "name": "Error: Method Not Found",
            "status": "failed",
            "message": str(e)
        })
    
    # Test 7: Error handling - Invalid JSON
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{demo_url}/a2a",
                content="{ invalid json [",
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 400:
                results.append({
                    "test": "error_invalid_json",
                    "name": "Error: Invalid JSON",
                    "status": "passed",
                    "message": "Correctly rejects invalid JSON with HTTP 400"
                })
            elif response.status_code == 200:
                resp_json = response.json()
                if "error" in resp_json:
                    error_code = resp_json["error"].get("code")
                    results.append({
                        "test": "error_invalid_json",
                        "name": "Error: Invalid JSON",
                        "status": "passed",
                        "message": f"Returns JSON-RPC error for invalid JSON (code: {error_code})"
                    })
                else:
                    results.append({
                        "test": "error_invalid_json",
                        "name": "Error: Invalid JSON",
                        "status": "failed",
                        "message": "Accepted invalid JSON without error"
                    })
            else:
                results.append({
                    "test": "error_invalid_json",
                    "name": "Error: Invalid JSON",
                    "status": "passed",
                    "message": f"Rejects invalid JSON with HTTP {response.status_code}"
                })
    except Exception as e:
        results.append({
            "test": "error_invalid_json",
            "name": "Error: Invalid JSON",
            "status": "failed",
            "message": str(e)
        })
    
    # Test 8: Task Not Found error
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            req = {
                "jsonrpc": "2.0",
                "id": "notfound-test",
                "method": "tasks/get",
                "params": {"id": "nonexistent-task-12345"}
            }
            response = await client.post(f"{demo_url}/a2a", json=req)
            resp_json = response.json()
            
            if "error" in resp_json:
                error_code = resp_json["error"].get("code")
                if error_code == -32001:  # Task not found
                    results.append({
                        "test": "error_task_not_found",
                        "name": "Error: Task Not Found",
                        "status": "passed",
                        "message": "Correctly returns -32001 for missing task"
                    })
                else:
                    results.append({
                        "test": "error_task_not_found",
                        "name": "Error: Task Not Found",
                        "status": "warning",
                        "message": f"Returns error but code is {error_code}, expected -32001"
                    })
            else:
                results.append({
                    "test": "error_task_not_found",
                    "name": "Error: Task Not Found",
                    "status": "failed",
                    "message": "No error returned for non-existent task"
                })
    except Exception as e:
        results.append({
            "test": "error_task_not_found",
            "name": "Error: Task Not Found",
            "status": "failed",
            "message": str(e)
        })
    
    # Test 9: Streaming support check
    try:
        streaming_supported = card.get("capabilities", {}).get("streaming", False)
        if streaming_supported:
            results.append({
                "test": "streaming_declared",
                "name": "Streaming Support",
                "status": "passed",
                "message": "Streaming capability declared in Agent Card"
            })
        else:
            results.append({
                "test": "streaming_declared",
                "name": "Streaming Support",
                "status": "warning",
                "message": "Streaming not declared (optional capability)"
            })
    except Exception as e:
        results.append({
            "test": "streaming_declared",
            "name": "Streaming Support",
            "status": "warning",
            "message": f"Could not check streaming: {e}"
        })
    
    # Test 10: Security schemes check
    try:
        security_schemes = card.get("securitySchemes", {})
        if security_schemes:
            results.append({
                "test": "security_schemes",
                "name": "Security Schemes",
                "status": "passed",
                "message": f"Declares {len(security_schemes)} security scheme(s)",
                "details": {"schemes": list(security_schemes.keys())}
            })
        else:
            results.append({
                "test": "security_schemes",
                "name": "Security Schemes",
                "status": "warning",
                "message": "No security schemes declared (agent is public)"
            })
    except Exception as e:
        results.append({
            "test": "security_schemes",
            "name": "Security Schemes",
            "status": "warning",
            "message": f"Could not check security: {e}"
        })
    
    # Calculate summary
    passed = sum(1 for r in results if r["status"] == "passed")
    failed = sum(1 for r in results if r["status"] == "failed")
    warnings = sum(1 for r in results if r["status"] == "warning")
    
    return {
        "success": failed == 0,
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "warnings": warnings,
            "score": round(passed / len(results) * 100) if results else 0
        },
        "results": results,
        "agent_url": demo_url
    }


# ============================================================================
# STATE MACHINE ENDPOINTS (NEW)
# ============================================================================

@app.post("/api/validate/state-transition")
async def validate_state_transition(request: StateValidationRequest):
    """
    Validate A2A task state transitions.
    
    Either provide:
    - `states`: Array of states to validate as a sequence
    - OR `from_state` + `to_state`: Single transition to validate
    """
    if request.from_state and request.to_state:
        # Single transition validation
        is_valid = validate_transition(request.from_state, request.to_state)
        valid_next = get_valid_next_states(request.from_state)
        
        return {
            "is_valid": is_valid,
            "from_state": request.from_state,
            "to_state": request.to_state,
            "valid_next_states": valid_next,
            "message": "Valid transition" if is_valid else f"Invalid: from '{request.from_state}' can only go to {valid_next}"
        }
    
    elif request.states:
        # Sequence validation
        result = validate_task_history(request.states)
        return result.to_dict()
    
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide either 'states' array or 'from_state'+'to_state'"
        )


@app.get("/api/state-machine/diagram")
async def get_state_machine():
    """
    Get the A2A state machine diagram and valid transitions.
    """
    from core.state_machine import VALID_TRANSITIONS, TaskState
    
    transitions = {
        state.value: [s.value for s in targets]
        for state, targets in VALID_TRANSITIONS.items()
    }
    
    return {
        "states": [s.value for s in TaskState],
        "terminal_states": ["completed", "failed", "canceled", "rejected"],
        "interrupted_states": ["input-required", "auth-required"],
        "initial_state": "submitted",
        "transitions": transitions,
        "ascii_diagram": get_state_machine_diagram()
    }


@app.get("/api/state-machine/next/{current_state}")
async def get_next_states(current_state: str):
    """
    Get valid next states from a given state.
    """
    valid_next = get_valid_next_states(current_state)
    
    if not valid_next and current_state not in ["completed", "failed", "canceled", "rejected"]:
        raise HTTPException(status_code=400, detail=f"Invalid state: {current_state}")
    
    return {
        "current_state": current_state,
        "valid_next_states": valid_next,
        "is_terminal": len(valid_next) == 0
    }


# ============================================================================
# SCENARIOS ENDPOINTS
# ============================================================================

@app.get("/api/scenarios")
async def list_scenarios():
    """
    List all available test scenarios.
    """
    return {
        "scenarios": list_all_scenarios(),
        "total": len(list_all_scenarios())
    }


@app.get("/api/scenarios/{scenario_id}")
async def get_scenario_detail(scenario_id: str):
    """
    Get details of a specific test scenario.
    """
    scenario = get_scenario(scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {scenario_id}")
    return scenario.to_dict()


@app.post("/api/scenarios/run")
async def run_scenario(request: ScenarioRunRequest):
    """
    Run a specific test scenario against an agent.
    """
    scenario = get_scenario(request.scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail=f"Scenario not found: {request.scenario_id}")
    
    tester = TaskTester(request.agent_url, request.auth_header)
    results = []
    
    context_id = None
    task_id = None
    
    for i, msg in enumerate(scenario.messages):
        try:
            # For multi-turn, reuse context
            response = await tester.send_message(
                text=msg.text,
                context_id=context_id,
                task_id=task_id if not msg.wait_for_completion else None,
                blocking=msg.wait_for_completion
            )
            
            # Extract context/task IDs for continuation
            if "result" in response:
                result = response["result"]
                if "contextId" in result:
                    context_id = result["contextId"]
                if "id" in result:
                    task_id = result["id"]
            
            results.append({
                "message_index": i,
                "message_text": msg.text[:100] + "..." if len(msg.text) > 100 else msg.text,
                "expected_behavior": msg.expected_behavior,
                "success": "error" not in response,
                "response": response
            })
            
        except Exception as e:
            results.append({
                "message_index": i,
                "message_text": msg.text[:100] + "..." if len(msg.text) > 100 else msg.text,
                "expected_behavior": msg.expected_behavior,
                "success": False,
                "error": str(e)
            })
    
    return {
        "scenario": scenario.to_dict(),
        "results": results,
        "success": all(r.get("success", False) for r in results)
    }


@app.post("/api/quick-test")
async def quick_test(request: QuickTestRequest):
    """
    Run a quick test suite against an agent.
    
    This runs a small set of essential scenarios to quickly validate
    basic A2A compliance.
    """
    scenarios = get_quick_test_scenarios()
    tester = TaskTester(request.agent_url, request.auth_header)
    
    results = []
    for scenario in scenarios:
        try:
            # Just run the first message of each scenario
            msg = scenario.messages[0]
            response = await tester.send_message(msg.text, blocking=True)
            
            results.append({
                "scenario_id": scenario.id,
                "scenario_name": scenario.name,
                "success": "error" not in response and "result" in response,
                "response_received": "result" in response or "error" in response
            })
        except Exception as e:
            results.append({
                "scenario_id": scenario.id,
                "scenario_name": scenario.name,
                "success": False,
                "error": str(e)
            })
    
    passed = sum(1 for r in results if r.get("success", False))
    
    return {
        "agent_url": request.agent_url,
        "summary": {
            "total": len(results),
            "passed": passed,
            "failed": len(results) - passed
        },
        "results": results
    }


# ============================================================================
# WEB UI
# ============================================================================

# Get the web directory path
WEB_DIR = Path(__file__).parent.parent / "web"


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the main web UI."""
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return HTMLResponse(
            content=index_path.read_text(), 
            status_code=200,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"}
        )
    else:
        return HTMLResponse(
            content="<h1>A2Apex</h1><p>Web UI not found. API available at /api/docs</p>",
            status_code=200
        )


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "path": str(request.url)
        }
    )


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8091)
