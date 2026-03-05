"""
A2Apex Error Handling Tester

Tests how agents handle bad input and error conditions.
Validates JSON-RPC 2.0 error response compliance.
"""

import uuid
import time
import json
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import httpx


class ErrorTestStatus(Enum):
    """Status of an error test."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class ErrorTestResult:
    """Result of a single error test."""
    test_name: str
    status: ErrorTestStatus
    message: str
    duration_ms: float = 0
    expected_code: Optional[int] = None
    actual_code: Optional[int] = None
    error: Optional[str] = None
    details: Optional[dict] = None
    suggestion: Optional[str] = None
    fix: Optional[str] = None
    code_snippet: Optional[str] = None
    spec_url: Optional[str] = None
    
    def to_dict(self) -> dict:
        result = {
            "test_name": self.test_name,
            "status": self.status.value,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "expected_code": self.expected_code,
            "actual_code": self.actual_code,
            "error": self.error,
            "details": self.details,
            "suggestion": self.suggestion
        }
        if self.fix:
            result["fix"] = self.fix
        if self.code_snippet:
            result["code_snippet"] = self.code_snippet
        if self.spec_url:
            result["spec_url"] = self.spec_url
        return result


@dataclass
class ErrorTestReport:
    """Complete report of error handling tests."""
    agent_url: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0
    results: list[ErrorTestResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def add_result(self, result: ErrorTestResult):
        self.results.append(result)
        self.total_tests += 1
        
        if result.status == ErrorTestStatus.PASSED:
            self.passed += 1
        elif result.status == ErrorTestStatus.FAILED:
            self.failed += 1
        elif result.status == ErrorTestStatus.WARNING:
            self.warnings += 1
        elif result.status == ErrorTestStatus.SKIPPED:
            self.skipped += 1
    
    @property
    def score(self) -> float:
        if self.total_tests == 0:
            return 0
        scored = self.total_tests - self.skipped; return (self.passed / scored * 100) if scored > 0 else 0
    
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
            "results": [r.to_dict() for r in self.results]
        }


# JSON-RPC 2.0 Standard Error Codes
JSONRPC_ERRORS = {
    "parse_error": -32700,
    "invalid_request": -32600,
    "method_not_found": -32601,
    "invalid_params": -32602,
    "internal_error": -32603,
}

# A2A-specific Error Codes
A2A_ERRORS = {
    "task_not_found": -32001,
    "task_not_cancelable": -32002,
    "push_notification_not_supported": -32003,
    "unsupported_operation": -32004,
    "content_type_not_supported": -32005,
    "invalid_agent_response": -32006,
}


class ErrorTester:
    """
    Error handling tester for A2A agents.
    
    Tests how agents handle various error conditions:
    - Malformed JSON
    - Invalid JSON-RPC requests
    - Unknown methods
    - Invalid parameters
    - Duplicate task IDs
    - Oversized payloads
    """
    
    def __init__(
        self,
        base_url: str,
        agent_card: Optional[dict] = None,
        timeout: float = 15.0
    ):
        """
        Initialize the error tester.
        
        Args:
            base_url: Base URL of the A2A agent
            agent_card: Agent Card JSON (if already fetched)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.agent_card = agent_card
        self.timeout = timeout
        self._endpoint_url: Optional[str] = None
    
    async def _get_endpoint_url(self) -> str:
        """Get the A2A endpoint URL."""
        if self._endpoint_url:
            return self._endpoint_url
        
        if self.agent_card:
            self._endpoint_url = self.agent_card.get("url", f"{self.base_url}/a2a")
        else:
            # Try to fetch agent card
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{self.base_url}/.well-known/agent-card.json")
                    if response.status_code == 200:
                        self.agent_card = response.json()
                        self._endpoint_url = self.agent_card.get("url", f"{self.base_url}/a2a")
                    else:
                        self._endpoint_url = f"{self.base_url}/a2a"
            except Exception:
                self._endpoint_url = f"{self.base_url}/a2a"
        
        return self._endpoint_url
    
    def _get_headers(self) -> dict:
        """Build base request headers."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "A2A-Version": "0.3"
        }
    
    def _validate_error_response(self, response: dict) -> tuple[bool, str, Optional[int]]:
        """
        Validate JSON-RPC error response structure.
        
        Returns: (is_valid, message, error_code)
        """
        if "error" not in response:
            return False, "Response missing 'error' field", None
        
        error = response["error"]
        
        if not isinstance(error, dict):
            return False, "Error field is not an object", None
        
        if "code" not in error:
            return False, "Error missing 'code' field", None
        
        if "message" not in error:
            return False, "Error missing 'message' field", None
        
        code = error.get("code")
        if not isinstance(code, int):
            return False, f"Error code must be integer, got {type(code).__name__}", None
        
        message = error.get("message")
        if not isinstance(message, str):
            return False, f"Error message must be string, got {type(message).__name__}", code
        
        return True, "Valid JSON-RPC error response", code
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ERROR HANDLING TESTS
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def test_malformed_json(self) -> ErrorTestResult:
        """
        Test: Send malformed JSON - should return Parse Error (-32700).
        """
        test_name = "malformed_json"
        expected_code = JSONRPC_ERRORS["parse_error"]
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    content="{ not valid json ][",
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                # HTTP 400 is acceptable for malformed JSON
                if response.status_code == 400:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message="Correctly rejects malformed JSON with HTTP 400",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        details={"http_status": 400}
                    )
                
                if response.status_code == 200:
                    try:
                        json_response = response.json()
                        is_valid, msg, actual_code = self._validate_error_response(json_response)
                        
                        if is_valid and actual_code == expected_code:
                            return ErrorTestResult(
                                test_name=test_name,
                                status=ErrorTestStatus.PASSED,
                                message=f"Correctly returns ParseError ({expected_code})",
                                duration_ms=duration_ms,
                                expected_code=expected_code,
                                actual_code=actual_code
                            )
                        elif is_valid:
                            return ErrorTestResult(
                                test_name=test_name,
                                status=ErrorTestStatus.WARNING,
                                message=f"Returns error but wrong code (expected {expected_code})",
                                duration_ms=duration_ms,
                                expected_code=expected_code,
                                actual_code=actual_code
                            )
                        else:
                            return ErrorTestResult(
                                test_name=test_name,
                                status=ErrorTestStatus.FAILED,
                                message=f"Invalid error response: {msg}",
                                duration_ms=duration_ms,
                                expected_code=expected_code,
                                suggestion="Error response must have 'code' (int) and 'message' (string)"
                            )
                    except json.JSONDecodeError:
                        return ErrorTestResult(
                            test_name=test_name,
                            status=ErrorTestStatus.WARNING,
                            message="Response is not valid JSON (may be acceptable)",
                            duration_ms=duration_ms
                        )
                
                return ErrorTestResult(
                    test_name=test_name,
                    status=ErrorTestStatus.WARNING,
                    message=f"Unexpected HTTP status: {response.status_code}",
                    duration_ms=duration_ms,
                    details={"http_status": response.status_code}
                )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_missing_jsonrpc_field(self) -> ErrorTestResult:
        """
        Test: Send request missing 'jsonrpc' field - should return Invalid Request (-32600).
        """
        test_name = "missing_jsonrpc_field"
        expected_code = JSONRPC_ERRORS["invalid_request"]
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        # Missing jsonrpc field
        request = {
            "method": "message/send",
            "params": {},
            "id": "test-1"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                json_response = response.json()
                is_valid, msg, actual_code = self._validate_error_response(json_response)
                
                if is_valid and actual_code == expected_code:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message=f"Correctly returns InvalidRequest ({expected_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif is_valid:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.WARNING,
                        message=f"Returns error but different code (got {actual_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif "result" in json_response:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message="Agent accepted request without 'jsonrpc' field",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        suggestion="Validate that 'jsonrpc': '2.0' is present"
                    )
                else:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message=f"Invalid error response: {msg}",
                        duration_ms=duration_ms,
                        expected_code=expected_code
                    )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_wrong_jsonrpc_version(self) -> ErrorTestResult:
        """
        Test: Send request with wrong jsonrpc version - should return Invalid Request (-32600).
        """
        test_name = "wrong_jsonrpc_version"
        expected_code = JSONRPC_ERRORS["invalid_request"]
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        # Wrong version
        request = {
            "jsonrpc": "1.0",  # Should be "2.0"
            "method": "message/send",
            "params": {},
            "id": "test-1"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                json_response = response.json()
                is_valid, msg, actual_code = self._validate_error_response(json_response)
                
                if is_valid and actual_code == expected_code:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message=f"Correctly rejects wrong jsonrpc version ({expected_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif is_valid:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.WARNING,
                        message=f"Returns error but different code (got {actual_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif "result" in json_response:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message="Agent accepted request with wrong jsonrpc version",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        suggestion="Validate that 'jsonrpc' equals '2.0'"
                    )
                else:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message=f"Invalid error response: {msg}",
                        duration_ms=duration_ms
                    )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_unknown_method(self) -> ErrorTestResult:
        """
        Test: Send request with unknown method - should return Method Not Found (-32601).
        """
        test_name = "unknown_method"
        expected_code = JSONRPC_ERRORS["method_not_found"]
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        request = {
            "jsonrpc": "2.0",
            "method": "nonexistent/method",
            "params": {},
            "id": "test-unknown"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                json_response = response.json()
                is_valid, msg, actual_code = self._validate_error_response(json_response)
                
                if is_valid and actual_code == expected_code:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message=f"Correctly returns MethodNotFound ({expected_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif is_valid:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.WARNING,
                        message=f"Returns error but different code (got {actual_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif "result" in json_response:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message="Agent accepted request with unknown method",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        suggestion="Return -32601 for unknown methods"
                    )
                else:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message=f"Invalid error response: {msg}",
                        duration_ms=duration_ms
                    )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_invalid_params_missing_message(self) -> ErrorTestResult:
        """
        Test: Send message/send without message param - should return Invalid Params (-32602).
        """
        test_name = "invalid_params_missing_message"
        expected_code = JSONRPC_ERRORS["invalid_params"]
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        # Missing required 'message' param
        request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "configuration": {"blocking": True}
            },
            "id": "test-invalid-params"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                json_response = response.json()
                is_valid, msg, actual_code = self._validate_error_response(json_response)
                
                if is_valid and actual_code == expected_code:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message=f"Correctly returns InvalidParams ({expected_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif is_valid:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.WARNING,
                        message=f"Returns error but different code (got {actual_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif "result" in json_response:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message="Agent accepted request without required 'message' param",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        suggestion="Validate required params and return -32602 when missing"
                    )
                else:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message=f"Invalid error response: {msg}",
                        duration_ms=duration_ms
                    )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_invalid_params_empty_parts(self) -> ErrorTestResult:
        """
        Test: Send message with empty parts array - verify graceful handling.
        """
        test_name = "invalid_params_empty_parts"
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [],  # Empty parts
                    "messageId": str(uuid.uuid4())
                }
            },
            "id": "test-empty-parts"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                json_response = response.json()
                
                # Either an error or a graceful handling is acceptable
                if "error" in json_response:
                    is_valid, msg, actual_code = self._validate_error_response(json_response)
                    if is_valid:
                        return ErrorTestResult(
                            test_name=test_name,
                            status=ErrorTestStatus.PASSED,
                            message=f"Properly rejects empty message parts (code: {actual_code})",
                            duration_ms=duration_ms,
                            actual_code=actual_code
                        )
                    else:
                        return ErrorTestResult(
                            test_name=test_name,
                            status=ErrorTestStatus.WARNING,
                            message=f"Returns error but invalid format: {msg}",
                            duration_ms=duration_ms
                        )
                elif "result" in json_response:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message="Agent handles empty parts gracefully",
                        duration_ms=duration_ms,
                        details={"handling": "accepted"}
                    )
                else:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.WARNING,
                        message="Unexpected response format",
                        duration_ms=duration_ms,
                        details={"response": json_response}
                    )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_task_not_found(self) -> ErrorTestResult:
        """
        Test: Request non-existent task - should return TaskNotFoundError (-32001).
        """
        test_name = "task_not_found"
        expected_code = A2A_ERRORS["task_not_found"]
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        request = {
            "jsonrpc": "2.0",
            "method": "tasks/get",
            "params": {
                "id": f"nonexistent-task-{uuid.uuid4()}"
            },
            "id": "test-not-found"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                json_response = response.json()
                is_valid, msg, actual_code = self._validate_error_response(json_response)
                
                if is_valid and actual_code == expected_code:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message=f"Correctly returns TaskNotFoundError ({expected_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif is_valid:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.WARNING,
                        message=f"Returns error but different code (got {actual_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code,
                        suggestion=f"Use A2A error code {expected_code} for TaskNotFoundError"
                    )
                elif "result" in json_response:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message="Agent returned result for non-existent task",
                        duration_ms=duration_ms,
                        expected_code=expected_code
                    )
                else:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message=f"Invalid error response: {msg}",
                        duration_ms=duration_ms
                    )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_cancel_nonexistent_task(self) -> ErrorTestResult:
        """
        Test: Cancel non-existent task - should return TaskNotFoundError (-32001).
        """
        test_name = "cancel_nonexistent_task"
        expected_code = A2A_ERRORS["task_not_found"]
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        request = {
            "jsonrpc": "2.0",
            "method": "tasks/cancel",
            "params": {
                "id": f"nonexistent-task-{uuid.uuid4()}"
            },
            "id": "test-cancel-not-found"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                json_response = response.json()
                is_valid, msg, actual_code = self._validate_error_response(json_response)
                
                if is_valid and actual_code == expected_code:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message=f"Correctly returns TaskNotFoundError for cancel ({expected_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                elif is_valid:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.WARNING,
                        message=f"Returns error but different code (got {actual_code})",
                        duration_ms=duration_ms,
                        expected_code=expected_code,
                        actual_code=actual_code
                    )
                else:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message=f"Invalid error response: {msg}",
                        duration_ms=duration_ms
                    )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_oversized_payload(self) -> ErrorTestResult:
        """
        Test: Send an oversized payload - verify graceful handling.
        """
        test_name = "oversized_payload"
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        # Create a 1MB message
        large_text = "X" * (1024 * 1024)  # 1MB of X's
        
        request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": large_text}],
                    "messageId": str(uuid.uuid4())
                }
            },
            "id": "test-oversized"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                # Any of these are acceptable responses
                if response.status_code == 413:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message="Correctly rejects oversized payload with HTTP 413",
                        duration_ms=duration_ms,
                        details={"http_status": 413}
                    )
                
                if response.status_code == 400:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.PASSED,
                        message="Rejects oversized payload with HTTP 400",
                        duration_ms=duration_ms,
                        details={"http_status": 400}
                    )
                
                try:
                    json_response = response.json()
                    
                    if "error" in json_response:
                        return ErrorTestResult(
                            test_name=test_name,
                            status=ErrorTestStatus.PASSED,
                            message="Returns JSON-RPC error for oversized payload",
                            duration_ms=duration_ms,
                            details={"error": json_response["error"]}
                        )
                    elif "result" in json_response:
                        return ErrorTestResult(
                            test_name=test_name,
                            status=ErrorTestStatus.WARNING,
                            message="Agent accepted 1MB payload (may be intentional)",
                            duration_ms=duration_ms,
                            suggestion="Consider setting max payload size limits"
                        )
                except Exception:
                    pass
                
                return ErrorTestResult(
                    test_name=test_name,
                    status=ErrorTestStatus.PASSED,
                    message=f"Handles oversized payload (HTTP {response.status_code})",
                    duration_ms=duration_ms,
                    details={"http_status": response.status_code}
                )
                
        except httpx.TimeoutException:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.WARNING,
                message="Request timed out (may indicate processing delay)",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_error_response_structure(self) -> ErrorTestResult:
        """
        Test: Verify error response matches JSON-RPC 2.0 spec.
        """
        test_name = "error_response_structure"
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        # Send a request that should return an error
        request = {
            "jsonrpc": "2.0",
            "method": "nonexistent/method",
            "params": {},
            "id": "test-structure"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                json_response = response.json()
                
                # Check full JSON-RPC 2.0 error response structure
                issues = []
                
                # Must have jsonrpc field
                if json_response.get("jsonrpc") != "2.0":
                    issues.append("Missing or invalid 'jsonrpc' field")
                
                # Must have matching id
                if json_response.get("id") != "test-structure":
                    issues.append("Response 'id' doesn't match request")
                
                # Must have error field
                if "error" not in json_response:
                    issues.append("Missing 'error' field")
                else:
                    error = json_response["error"]
                    
                    # Must have code (integer)
                    if "code" not in error:
                        issues.append("Error missing 'code'")
                    elif not isinstance(error["code"], int):
                        issues.append("Error 'code' must be integer")
                    
                    # Must have message (string)
                    if "message" not in error:
                        issues.append("Error missing 'message'")
                    elif not isinstance(error["message"], str):
                        issues.append("Error 'message' must be string")
                    
                    # data field is optional but if present, any type is valid
                
                # Must NOT have result field
                if "result" in json_response:
                    issues.append("Error response should not have 'result' field")
                
                if issues:
                    return ErrorTestResult(
                        test_name=test_name,
                        status=ErrorTestStatus.FAILED,
                        message=f"Error response has {len(issues)} structural issue(s)",
                        duration_ms=duration_ms,
                        details={"issues": issues},
                        suggestion="See JSON-RPC 2.0 spec: https://www.jsonrpc.org/specification#error_object"
                    )
                
                return ErrorTestResult(
                    test_name=test_name,
                    status=ErrorTestStatus.PASSED,
                    message="Error response follows JSON-RPC 2.0 spec",
                    duration_ms=duration_ms,
                    details={
                        "has_jsonrpc": True,
                        "has_id": True,
                        "has_code": True,
                        "has_message": True
                    }
                )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_null_request_id(self) -> ErrorTestResult:
        """
        Test: Send request with null id - verify proper handling.
        """
        test_name = "null_request_id"
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        request = {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Test"}],
                    "messageId": str(uuid.uuid4())
                }
            },
            "id": None  # Null id
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                json_response = response.json()
                
                # Response id should also be null if request id was null
                response_id = json_response.get("id")
                
                if "error" in json_response or "result" in json_response:
                    if response_id is None:
                        return ErrorTestResult(
                            test_name=test_name,
                            status=ErrorTestStatus.PASSED,
                            message="Correctly handles null request id",
                            duration_ms=duration_ms,
                            details={"response_id": response_id}
                        )
                    else:
                        return ErrorTestResult(
                            test_name=test_name,
                            status=ErrorTestStatus.WARNING,
                            message="Response id should be null when request id is null",
                            duration_ms=duration_ms,
                            details={"response_id": response_id}
                        )
                
                return ErrorTestResult(
                    test_name=test_name,
                    status=ErrorTestStatus.WARNING,
                    message="Unexpected response format",
                    duration_ms=duration_ms
                )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_batch_request_handling(self) -> ErrorTestResult:
        """
        Test: Send a batch request - verify proper handling or rejection.
        """
        test_name = "batch_request_handling"
        start = time.perf_counter()
        
        endpoint_url = await self._get_endpoint_url()
        
        # JSON-RPC batch request
        batch_request = [
            {
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Batch 1"}],
                        "messageId": str(uuid.uuid4())
                    }
                },
                "id": "batch-1"
            },
            {
                "jsonrpc": "2.0",
                "method": "message/send",
                "params": {
                    "message": {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Batch 2"}],
                        "messageId": str(uuid.uuid4())
                    }
                },
                "id": "batch-2"
            }
        ]
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=batch_request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                # Batch support is optional in A2A
                if response.status_code == 200:
                    json_response = response.json()
                    
                    if isinstance(json_response, list):
                        return ErrorTestResult(
                            test_name=test_name,
                            status=ErrorTestStatus.PASSED,
                            message=f"Supports batch requests ({len(json_response)} responses)",
                            duration_ms=duration_ms,
                            details={"batch_size": len(json_response)}
                        )
                    elif "error" in json_response:
                        return ErrorTestResult(
                            test_name=test_name,
                            status=ErrorTestStatus.PASSED,
                            message="Rejects batch requests with error (acceptable)",
                            duration_ms=duration_ms,
                            details={"error": json_response["error"]}
                        )
                
                return ErrorTestResult(
                    test_name=test_name,
                    status=ErrorTestStatus.PASSED,
                    message=f"Handles batch request (HTTP {response.status_code})",
                    duration_ms=duration_ms
                )
                
        except Exception as e:
            return ErrorTestResult(
                test_name=test_name,
                status=ErrorTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FULL TEST SUITE
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def run_all_tests(self) -> ErrorTestReport:
        """
        Run the complete error handling test suite.
        
        Returns:
            ErrorTestReport with all test results
        """
        report = ErrorTestReport(agent_url=self.base_url)
        
        # Run all error tests
        tests = [
            self.test_malformed_json,
            self.test_missing_jsonrpc_field,
            self.test_wrong_jsonrpc_version,
            self.test_unknown_method,
            self.test_invalid_params_missing_message,
            self.test_invalid_params_empty_parts,
            self.test_task_not_found,
            self.test_cancel_nonexistent_task,
            self.test_error_response_structure,
            self.test_null_request_id,
            self.test_batch_request_handling,
            self.test_oversized_payload,
        ]
        
        for test_func in tests:
            try:
                result = await test_func()
                report.add_result(result)
            except Exception as e:
                report.add_result(ErrorTestResult(
                    test_name=test_func.__name__.replace("test_", ""),
                    status=ErrorTestStatus.FAILED,
                    message=f"Test crashed: {type(e).__name__}",
                    error=str(e)
                ))
        
        return report


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def run_error_tests(
    agent_url: str,
    agent_card: Optional[dict] = None,
    timeout: float = 15.0
) -> ErrorTestReport:
    """
    Run the complete error handling test suite against an agent.
    
    Args:
        agent_url: Base URL of the A2A agent
        agent_card: Optional pre-fetched Agent Card
        timeout: Request timeout in seconds
        
    Returns:
        ErrorTestReport with all test results
    """
    tester = ErrorTester(agent_url, agent_card, timeout)
    return await tester.run_all_tests()
