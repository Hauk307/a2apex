"""
A2Apex Live Endpoint Tester

Actually calls A2A agent endpoints and validates responses.
This is the live testing functionality for A2A protocol compliance.

Tests:
- Agent Card fetch
- message/send (JSON-RPC)
- tasks/get (JSON-RPC)
- tasks/cancel (JSON-RPC)
- message/stream (SSE)
"""

import uuid
import json
import asyncio
import time
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import httpx

from .agent_card_validator import AgentCardValidator, ValidationSeverity
from .state_machine import StateMachineValidator, is_terminal_state
from .fix_guidance import LIVE_TEST_FIXES, FixGuidance


class TestStatus(Enum):
    """Status of a single test."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class LiveTestResult:
    """Result of a single live test."""
    test_name: str
    status: TestStatus
    message: str
    duration_ms: float = 0
    request: Optional[dict] = None
    response: Optional[dict] = None
    error: Optional[str] = None
    details: Optional[dict] = None
    fix: Optional[str] = None
    code_snippet: Optional[str] = None
    spec_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        result = {
            "test_name": self.test_name,
            "status": self.status.value,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "details": self.details,
            "request": self.request,
            "response": self.response
        }
        # Only include fix fields if they have values
        if self.fix:
            result["fix"] = self.fix
        if self.code_snippet:
            result["code_snippet"] = self.code_snippet
        if self.spec_url:
            result["spec_url"] = self.spec_url
        return result


@dataclass  
class LiveTestReport:
    """Complete report of live testing."""
    agent_url: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0
    score: float = 0.0
    results: list[LiveTestResult] = field(default_factory=list)
    agent_card: Optional[dict] = None
    total_duration_ms: float = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def add_result(self, result: LiveTestResult):
        self.results.append(result)
        self.total_tests += 1
        
        if result.status == TestStatus.PASSED:
            self.passed += 1
        elif result.status == TestStatus.FAILED:
            self.failed += 1
        elif result.status == TestStatus.WARNING:
            self.warnings += 1
        elif result.status == TestStatus.SKIPPED:
            self.skipped += 1
        
        # Update score
        if self.total_tests > 0:
            self.score = (self.passed / self.total_tests) * 100
    
    def to_dict(self) -> dict:
        return {
            "agent_url": self.agent_url,
            "timestamp": self.timestamp,
            "summary": {
                "total": self.total_tests,
                "passed": self.passed,
                "failed": self.failed,
                "warnings": self.warnings,
                "skipped": self.skipped,
                "score": round(self.score, 1)
            },
            "total_duration_ms": round(self.total_duration_ms, 2),
            "results": [r.to_dict() for r in self.results],
            "agent_card": self.agent_card
        }


class LiveTester:
    """
    Live endpoint tester for A2A agents.
    
    Tests actual HTTP connectivity and protocol compliance by
    making real requests to the agent.
    """
    
    def __init__(
        self,
        base_url: str,
        auth_header: Optional[str] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the live tester.
        
        Args:
            base_url: Base URL of the A2A agent
            auth_header: Optional Authorization header value
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.auth_header = auth_header
        self.timeout = timeout
        self.agent_card: Optional[dict] = None
        self._client: Optional[httpx.AsyncClient] = None
    
    def _get_headers(self, extra: Optional[dict] = None) -> dict:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "A2A-Version": "0.3"
        }
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        if extra:
            headers.update(extra)
        return headers
    
    def _build_jsonrpc_request(
        self,
        method: str,
        params: dict,
        request_id: Optional[str] = None
    ) -> dict:
        """Build a JSON-RPC 2.0 request."""
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id or str(uuid.uuid4())
        }
    
    def _build_message(
        self,
        text: str,
        context_id: Optional[str] = None,
        task_id: Optional[str] = None
    ) -> dict:
        """Build an A2A message object."""
        message = {
            "role": "user",
            "parts": [{"kind": "text", "text": text}],
            "messageId": str(uuid.uuid4())
        }
        if context_id:
            message["contextId"] = context_id
        if task_id:
            message["taskId"] = task_id
        return message
    
    async def _request(
        self,
        method: str,
        url: str,
        json_data: Optional[dict] = None,
        headers: Optional[dict] = None
    ) -> tuple[Optional[httpx.Response], Optional[Exception], float]:
        """Make an HTTP request and return (response, error, duration_ms)."""
        start = time.perf_counter()
        
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True
            ) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers or self._get_headers())
                else:
                    response = await client.post(
                        url,
                        json=json_data,
                        headers=headers or self._get_headers()
                    )
                
                duration_ms = (time.perf_counter() - start) * 1000
                return response, None, duration_ms
                
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            return None, e, duration_ms
    
    # ═══════════════════════════════════════════════════════════════════════════
    # INDIVIDUAL TESTS
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def test_agent_card_fetch(self) -> LiveTestResult:
        """
        Test: Fetch Agent Card from /.well-known/agent-card.json
        
        Validates:
        - HTTP 200 response
        - Valid JSON
        - Content-Type header
        - Basic structure validation
        """
        test_name = "agent_card_fetch"
        url = f"{self.base_url}/.well-known/agent-card.json"
        
        response, error, duration_ms = await self._request("GET", url)
        
        if error:
            fix = LIVE_TEST_FIXES.get("agent_card_connection_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"Failed to connect: {type(error).__name__}",
                duration_ms=duration_ms,
                error=str(error),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        # Check HTTP status
        if response.status_code == 404:
            fix = LIVE_TEST_FIXES.get("agent_card_not_found")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Agent Card not found at /.well-known/agent-card.json",
                duration_ms=duration_ms,
                error="HTTP 404 Not Found",
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        if response.status_code != 200:
            fix = LIVE_TEST_FIXES.get("agent_card_not_found")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"Unexpected HTTP status: {response.status_code}",
                duration_ms=duration_ms,
                error=f"HTTP {response.status_code}",
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        # Check Content-Type
        content_type = response.headers.get("content-type", "")
        content_type_ok = "application/json" in content_type
        
        # Parse JSON
        try:
            agent_card = response.json()
        except json.JSONDecodeError as e:
            fix = LIVE_TEST_FIXES.get("agent_card_invalid_json")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Response is not valid JSON",
                duration_ms=duration_ms,
                error=str(e),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        # Store for later tests
        self.agent_card = agent_card
        
        # Basic structure check
        validator = AgentCardValidator()
        report = validator.validate(agent_card)
        
        details = {
            "url": url,
            "content_type": content_type,
            "content_type_valid": content_type_ok,
            "agent_name": agent_card.get("name"),
            "validation_errors": report.error_count,
            "validation_warnings": report.warning_count
        }
        
        if report.error_count > 0:
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.WARNING,
                message=f"Agent Card has {report.error_count} validation errors",
                duration_ms=duration_ms,
                response=agent_card,
                details=details
            )
        
        return LiveTestResult(
            test_name=test_name,
            status=TestStatus.PASSED,
            message=f"Agent Card fetched successfully ({report.warning_count} warnings)",
            duration_ms=duration_ms,
            response=agent_card,
            details=details
        )
    
    async def test_message_send(
        self,
        message_text: str = "Hello! This is a test message from A2Apex.",
        blocking: bool = True
    ) -> LiveTestResult:
        """
        Test: Send a message using message/send JSON-RPC method
        
        Validates:
        - HTTP 200 response
        - Valid JSON-RPC 2.0 response
        - Response contains either Task or Message
        - Task has valid structure if present
        """
        test_name = "message_send"
        
        # Build request
        message = self._build_message(message_text)
        params = {
            "message": message,
            "configuration": {
                "blocking": blocking,
                "acceptedOutputModes": ["text/plain", "application/json"]
            }
        }
        request = self._build_jsonrpc_request("message/send", params)
        
        # Get the A2A endpoint URL (from agent card if available)
        endpoint_url = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        
        response, error, duration_ms = await self._request("POST", endpoint_url, request)
        
        if error:
            fix = LIVE_TEST_FIXES.get("message_send_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"Request failed: {type(error).__name__}",
                duration_ms=duration_ms,
                request=request,
                error=str(error),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        if response.status_code != 200:
            fix = LIVE_TEST_FIXES.get("message_send_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"HTTP {response.status_code}",
                duration_ms=duration_ms,
                request=request,
                error=f"Expected HTTP 200, got {response.status_code}",
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        # Parse response
        try:
            json_response = response.json()
        except json.JSONDecodeError as e:
            fix = LIVE_TEST_FIXES.get("message_send_invalid_response")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Invalid JSON response",
                duration_ms=duration_ms,
                request=request,
                error=str(e),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        # Validate JSON-RPC format
        if "jsonrpc" not in json_response or json_response.get("jsonrpc") != "2.0":
            fix = LIVE_TEST_FIXES.get("message_send_invalid_response")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Response is not valid JSON-RPC 2.0",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                error="Missing or invalid 'jsonrpc' field",
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        # Check for error response
        if "error" in json_response:
            error_obj = json_response["error"]
            fix = LIVE_TEST_FIXES.get("message_send_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"JSON-RPC error: {error_obj.get('message', 'Unknown')}",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                error=f"Code {error_obj.get('code')}: {error_obj.get('message')}",
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        # Validate result
        if "result" not in json_response:
            fix = LIVE_TEST_FIXES.get("message_send_invalid_response")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Response missing 'result' field",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                error="No result in response",
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        result = json_response["result"]
        
        # Determine if it's a Task or Message response
        is_task = "id" in result and "status" in result
        is_message = "role" in result and "parts" in result
        
        details = {
            "response_type": "task" if is_task else ("message" if is_message else "unknown"),
            "endpoint": endpoint_url
        }
        
        if is_task:
            details["task_id"] = result.get("id")
            details["task_state"] = result.get("status", {}).get("state")
            details["context_id"] = result.get("contextId")
            
            # Validate task state
            state = result.get("status", {}).get("state")
            valid_states = ["submitted", "working", "input-required", "auth-required", 
                          "completed", "failed", "canceled", "rejected"]
            
            if state not in valid_states:
                fix = LIVE_TEST_FIXES.get("invalid_task_state")
                return LiveTestResult(
                    test_name=test_name,
                    status=TestStatus.FAILED,
                    message=f"Invalid task state: {state}",
                    duration_ms=duration_ms,
                    request=request,
                    response=json_response,
                    details=details,
                    error=f"State '{state}' not in valid states",
                    fix=fix.fix if fix else None,
                    code_snippet=fix.code_snippet if fix else None,
                    spec_url=fix.spec_url if fix else None
                )
            
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.PASSED,
                message=f"Task created (state: {state})",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                details=details
            )
        
        elif is_message:
            details["message_role"] = result.get("role")
            details["parts_count"] = len(result.get("parts", []))
            
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.PASSED,
                message="Direct message response received",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                details=details
            )
        
        return LiveTestResult(
            test_name=test_name,
            status=TestStatus.WARNING,
            message="Response has unexpected structure",
            duration_ms=duration_ms,
            request=request,
            response=json_response,
            details=details
        )
    
    async def test_task_get(self, task_id: str) -> LiveTestResult:
        """
        Test: Get task status using tasks/get JSON-RPC method
        
        Args:
            task_id: The task ID to retrieve
        """
        test_name = "task_get"
        
        request = self._build_jsonrpc_request("tasks/get", {"id": task_id})
        endpoint_url = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        
        response, error, duration_ms = await self._request("POST", endpoint_url, request)
        
        if error:
            fix = LIVE_TEST_FIXES.get("task_get_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"Request failed: {type(error).__name__}",
                duration_ms=duration_ms,
                request=request,
                error=str(error),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        if response.status_code != 200:
            fix = LIVE_TEST_FIXES.get("task_get_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"HTTP {response.status_code}",
                duration_ms=duration_ms,
                request=request,
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        try:
            json_response = response.json()
        except json.JSONDecodeError as e:
            fix = LIVE_TEST_FIXES.get("task_get_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Invalid JSON response",
                duration_ms=duration_ms,
                request=request,
                error=str(e),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        # Check for TaskNotFound error
        if "error" in json_response:
            error_obj = json_response["error"]
            code = error_obj.get("code")
            
            if code == -32001:  # TaskNotFoundError
                return LiveTestResult(
                    test_name=test_name,
                    status=TestStatus.WARNING,
                    message="Task not found (may have expired)",
                    duration_ms=duration_ms,
                    request=request,
                    response=json_response,
                    details={"error_code": code}
                )
            
            fix = LIVE_TEST_FIXES.get("task_get_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"JSON-RPC error: {error_obj.get('message')}",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                error=f"Code {code}",
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        if "result" not in json_response:
            fix = LIVE_TEST_FIXES.get("task_get_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Response missing 'result'",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        result = json_response["result"]
        state = result.get("status", {}).get("state")
        
        return LiveTestResult(
            test_name=test_name,
            status=TestStatus.PASSED,
            message=f"Task retrieved (state: {state})",
            duration_ms=duration_ms,
            request=request,
            response=json_response,
            details={
                "task_id": result.get("id"),
                "state": state,
                "has_artifacts": len(result.get("artifacts", [])) > 0
            }
        )
    
    async def test_task_cancel(self, task_id: str) -> LiveTestResult:
        """
        Test: Cancel a task using tasks/cancel JSON-RPC method
        
        Args:
            task_id: The task ID to cancel
        """
        test_name = "task_cancel"
        
        request = self._build_jsonrpc_request("tasks/cancel", {"id": task_id})
        endpoint_url = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        
        response, error, duration_ms = await self._request("POST", endpoint_url, request)
        
        if error:
            fix = LIVE_TEST_FIXES.get("task_cancel_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"Request failed: {type(error).__name__}",
                duration_ms=duration_ms,
                request=request,
                error=str(error),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        if response.status_code != 200:
            fix = LIVE_TEST_FIXES.get("task_cancel_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"HTTP {response.status_code}",
                duration_ms=duration_ms,
                request=request,
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        try:
            json_response = response.json()
        except json.JSONDecodeError as e:
            fix = LIVE_TEST_FIXES.get("task_cancel_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Invalid JSON response",
                duration_ms=duration_ms,
                request=request,
                error=str(e),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        if "error" in json_response:
            error_obj = json_response["error"]
            code = error_obj.get("code")
            
            # TaskNotCancelable (-32002) means task already finished
            if code == -32002:
                return LiveTestResult(
                    test_name=test_name,
                    status=TestStatus.PASSED,
                    message="Task not cancelable (already terminal)",
                    duration_ms=duration_ms,
                    request=request,
                    response=json_response,
                    details={"error_code": code, "reason": "Task already completed or failed"}
                )
            
            if code == -32001:  # TaskNotFound
                return LiveTestResult(
                    test_name=test_name,
                    status=TestStatus.WARNING,
                    message="Task not found",
                    duration_ms=duration_ms,
                    request=request,
                    response=json_response,
                    details={"error_code": code}
                )
            
            fix = LIVE_TEST_FIXES.get("task_cancel_failed")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"JSON-RPC error: {error_obj.get('message')}",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        result = json_response.get("result", {})
        state = result.get("status", {}).get("state")
        
        return LiveTestResult(
            test_name=test_name,
            status=TestStatus.PASSED,
            message=f"Cancel request processed (state: {state})",
            duration_ms=duration_ms,
            request=request,
            response=json_response,
            details={"final_state": state}
        )
    
    async def test_streaming(
        self,
        message_text: str = "Please count from 1 to 5 slowly."
    ) -> LiveTestResult:
        """
        Test: Streaming via message/stream (SSE)
        
        Validates:
        - Server responds with SSE stream
        - Events have correct format
        - Stream terminates properly
        """
        test_name = "streaming"
        
        # Check if streaming is supported
        if self.agent_card:
            capabilities = self.agent_card.get("capabilities", {})
            if not capabilities.get("streaming"):
                return LiveTestResult(
                    test_name=test_name,
                    status=TestStatus.SKIPPED,
                    message="Streaming not supported (capabilities.streaming=false)",
                    duration_ms=0,
                    details={"streaming_supported": False}
                )
        
        # Build request
        message = self._build_message(message_text)
        params = {
            "message": message,
            "configuration": {
                "acceptedOutputModes": ["text/plain"]
            }
        }
        request = self._build_jsonrpc_request("message/stream", params)
        endpoint_url = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        
        events_received = []
        start = time.perf_counter()
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = self._get_headers({"Accept": "text/event-stream"})
                
                async with client.stream("POST", endpoint_url, json=request, headers=headers) as response:
                    if response.status_code != 200:
                        duration_ms = (time.perf_counter() - start) * 1000
                        fix = LIVE_TEST_FIXES.get("streaming_not_working")
                        return LiveTestResult(
                            test_name=test_name,
                            status=TestStatus.FAILED,
                            message=f"HTTP {response.status_code}",
                            duration_ms=duration_ms,
                            request=request,
                            fix=fix.fix if fix else None,
                            code_snippet=fix.code_snippet if fix else None,
                            spec_url=fix.spec_url if fix else None
                        )
                    
                    # Check content type
                    content_type = response.headers.get("content-type", "")
                    is_sse = "text/event-stream" in content_type
                    
                    # Read events
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        
                        # Parse SSE events
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            
                            # Parse event
                            event_data = None
                            for line in event_text.split("\n"):
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    try:
                                        event_data = json.loads(data_str)
                                        events_received.append(event_data)
                                    except json.JSONDecodeError:
                                        pass
                            
                            # Check for terminal state
                            if event_data and isinstance(event_data, dict):
                                result = event_data.get("result", {})
                                
                                # Check status update
                                if "statusUpdate" in result:
                                    update = result["statusUpdate"]
                                    if update.get("final"):
                                        break
                                
                                # Check task state
                                if "task" in result:
                                    state = result["task"].get("status", {}).get("state")
                                    if is_terminal_state(state):
                                        break
                        
                        # Limit events
                        if len(events_received) > 50:
                            break
                    
                    duration_ms = (time.perf_counter() - start) * 1000
                    
                    if not events_received:
                        fix = LIVE_TEST_FIXES.get("streaming_not_working")
                        return LiveTestResult(
                            test_name=test_name,
                            status=TestStatus.FAILED,
                            message="No SSE events received",
                            duration_ms=duration_ms,
                            request=request,
                            details={"content_type": content_type, "is_sse": is_sse},
                            fix=fix.fix if fix else None,
                            code_snippet=fix.code_snippet if fix else None,
                            spec_url=fix.spec_url if fix else None
                        )
                    
                    return LiveTestResult(
                        test_name=test_name,
                        status=TestStatus.PASSED,
                        message=f"Streaming works ({len(events_received)} events)",
                        duration_ms=duration_ms,
                        request=request,
                        details={
                            "events_count": len(events_received),
                            "content_type": content_type,
                            "is_sse": is_sse,
                            "first_event": events_received[0] if events_received else None
                        }
                    )
                    
        except httpx.ReadTimeout:
            duration_ms = (time.perf_counter() - start) * 1000
            if events_received:
                return LiveTestResult(
                    test_name=test_name,
                    status=TestStatus.PASSED,
                    message=f"Stream timed out but received {len(events_received)} events",
                    duration_ms=duration_ms,
                    request=request,
                    details={"events_count": len(events_received)}
                )
            fix = LIVE_TEST_FIXES.get("streaming_not_working")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Stream timed out with no events",
                duration_ms=duration_ms,
                request=request,
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            fix = LIVE_TEST_FIXES.get("streaming_not_working")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"Streaming failed: {type(e).__name__}",
                duration_ms=duration_ms,
                request=request,
                error=str(e),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
    
    async def test_invalid_method(self) -> LiveTestResult:
        """
        Test: Agent handles invalid method gracefully
        
        Should return JSON-RPC MethodNotFoundError (-32601)
        """
        test_name = "invalid_method"
        
        request = self._build_jsonrpc_request("nonexistent/method", {})
        endpoint_url = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        
        response, error, duration_ms = await self._request("POST", endpoint_url, request)
        
        if error:
            fix = LIVE_TEST_FIXES.get("invalid_method_no_error")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"Request failed: {type(error).__name__}",
                duration_ms=duration_ms,
                request=request,
                error=str(error),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        try:
            json_response = response.json()
        except json.JSONDecodeError:
            fix = LIVE_TEST_FIXES.get("invalid_method_no_error")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Response is not valid JSON",
                duration_ms=duration_ms,
                request=request,
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        if "error" not in json_response:
            fix = LIVE_TEST_FIXES.get("invalid_method_no_error")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message="Agent did not return error for invalid method",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
        
        error_obj = json_response["error"]
        code = error_obj.get("code")
        
        # -32601 is MethodNotFoundError
        if code == -32601:
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.PASSED,
                message="Correctly returns MethodNotFoundError (-32601)",
                duration_ms=duration_ms,
                request=request,
                response=json_response,
                details={"error_code": code}
            )
        
        return LiveTestResult(
            test_name=test_name,
            status=TestStatus.WARNING,
            message=f"Returns error but wrong code (expected -32601, got {code})",
            duration_ms=duration_ms,
            request=request,
            response=json_response,
            details={"error_code": code, "expected_code": -32601}
        )
    
    async def test_invalid_json(self) -> LiveTestResult:
        """
        Test: Agent handles invalid JSON gracefully
        
        Should return JSON-RPC JSONParseError (-32700)
        """
        test_name = "invalid_json"
        
        endpoint_url = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    content="{ not valid json",
                    headers={"Content-Type": "application/json", "A2A-Version": "0.3"}
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                if response.status_code >= 400:
                    # HTTP error is acceptable for invalid JSON
                    return LiveTestResult(
                        test_name=test_name,
                        status=TestStatus.PASSED,
                        message=f"Correctly rejects invalid JSON (HTTP {response.status_code})",
                        duration_ms=duration_ms,
                        details={"http_status": response.status_code}
                    )
                
                try:
                    json_response = response.json()
                    
                    if "error" in json_response:
                        code = json_response["error"].get("code")
                        if code == -32700:
                            return LiveTestResult(
                                test_name=test_name,
                                status=TestStatus.PASSED,
                                message="Correctly returns JSONParseError (-32700)",
                                duration_ms=duration_ms,
                                response=json_response,
                                details={"error_code": code}
                            )
                        
                        return LiveTestResult(
                            test_name=test_name,
                            status=TestStatus.WARNING,
                            message=f"Returns error but unexpected code (got {code})",
                            duration_ms=duration_ms,
                            response=json_response,
                            details={"error_code": code, "expected_code": -32700}
                        )
                    
                    fix = LIVE_TEST_FIXES.get("invalid_json_no_error")
                    return LiveTestResult(
                        test_name=test_name,
                        status=TestStatus.FAILED,
                        message="Agent accepted invalid JSON",
                        duration_ms=duration_ms,
                        response=json_response,
                        fix=fix.fix if fix else None,
                        code_snippet=fix.code_snippet if fix else None,
                        spec_url=fix.spec_url if fix else None
                    )
                except json.JSONDecodeError:
                    return LiveTestResult(
                        test_name=test_name,
                        status=TestStatus.WARNING,
                        message="Response is not JSON (may be acceptable)",
                        duration_ms=duration_ms
                    )
                    
        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            fix = LIVE_TEST_FIXES.get("invalid_json_no_error")
            return LiveTestResult(
                test_name=test_name,
                status=TestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=duration_ms,
                error=str(e),
                fix=fix.fix if fix else None,
                code_snippet=fix.code_snippet if fix else None,
                spec_url=fix.spec_url if fix else None
            )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FULL TEST SUITE
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def run_all_tests(self) -> LiveTestReport:
        """
        Run the complete live test suite.
        
        Returns:
            LiveTestReport with all test results
        """
        report = LiveTestReport(agent_url=self.base_url)
        start = time.perf_counter()
        
        # Test 1: Agent Card Fetch
        result = await self.test_agent_card_fetch()
        report.add_result(result)
        
        if result.status == TestStatus.FAILED:
            # Can't continue without agent card
            report.total_duration_ms = (time.perf_counter() - start) * 1000
            return report
        
        report.agent_card = self.agent_card
        
        # Test 2: Message Send
        send_result = await self.test_message_send()
        report.add_result(send_result)
        
        # Extract task ID if available
        task_id = None
        if send_result.details:
            task_id = send_result.details.get("task_id")
        
        # Test 3: Task Get (if we have a task ID)
        if task_id:
            result = await self.test_task_get(task_id)
            report.add_result(result)
        else:
            report.add_result(LiveTestResult(
                test_name="task_get",
                status=TestStatus.SKIPPED,
                message="No task ID from message/send",
                duration_ms=0
            ))
        
        # Test 4: Streaming
        result = await self.test_streaming()
        report.add_result(result)
        
        # Test 5: Error handling - Invalid Method
        result = await self.test_invalid_method()
        report.add_result(result)
        
        # Test 6: Error handling - Invalid JSON
        result = await self.test_invalid_json()
        report.add_result(result)
        
        # Test 7: Task Cancel (if we have a task and it's not terminal)
        if task_id:
            result = await self.test_task_cancel(task_id)
            report.add_result(result)
        else:
            report.add_result(LiveTestResult(
                test_name="task_cancel",
                status=TestStatus.SKIPPED,
                message="No task ID available",
                duration_ms=0
            ))
        
        report.total_duration_ms = (time.perf_counter() - start) * 1000
        return report


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def run_live_tests(
    agent_url: str,
    auth_header: Optional[str] = None,
    timeout: float = 30.0
) -> LiveTestReport:
    """
    Run the complete live test suite against an agent.
    
    Args:
        agent_url: Base URL of the A2A agent
        auth_header: Optional Authorization header value
        timeout: Request timeout in seconds
        
    Returns:
        LiveTestReport with all test results
    """
    tester = LiveTester(agent_url, auth_header, timeout)
    return await tester.run_all_tests()


async def test_agent_card(url: str, timeout: float = 30.0) -> LiveTestResult:
    """Quick test just the Agent Card fetch."""
    tester = LiveTester(url, timeout=timeout)
    return await tester.test_agent_card_fetch()


async def test_message_send(
    url: str,
    message: str = "Hello!",
    auth_header: Optional[str] = None,
    timeout: float = 30.0
) -> LiveTestResult:
    """Quick test message/send."""
    tester = LiveTester(url, auth_header, timeout)
    # Fetch agent card first
    await tester.test_agent_card_fetch()
    return await tester.test_message_send(message)
