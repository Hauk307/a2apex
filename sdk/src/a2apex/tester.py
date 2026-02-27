"""
A2A Live Endpoint Tester

Test actual A2A agent endpoints by making real HTTP requests.
Validates response format, protocol compliance, and error handling.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import httpx

from .models import TaskState
from .state_machine import is_terminal_state
from .validator import AgentCardValidator


# ═══════════════════════════════════════════════════════════════════════════════
# TEST RESULT TYPES
# ═══════════════════════════════════════════════════════════════════════════════


class TestStatus(str, Enum):
    """Status of a single test."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class TestResult:
    """Result of a single live test."""

    name: str
    status: TestStatus
    message: str
    passed: bool = field(init=False)
    duration_ms: float = 0
    request: dict | None = None
    response: dict | None = None
    error: str | None = None
    details: dict | None = None

    def __post_init__(self) -> None:
        self.passed = self.status == TestStatus.PASSED

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status.value,
            "passed": self.passed,
            "message": self.message,
            "duration_ms": round(self.duration_ms, 2),
            "error": self.error,
            "details": self.details,
            "request": self.request,
            "response": self.response,
        }


@dataclass
class TestReport:
    """Complete test report for an agent."""

    agent_url: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0
    score: float = 0.0
    results: list[TestResult] = field(default_factory=list)
    agent_card: dict | None = None
    total_duration_ms: float = 0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def add_result(self, result: TestResult) -> None:
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
                "score": round(self.score, 1),
            },
            "total_duration_ms": round(self.total_duration_ms, 2),
            "results": [r.to_dict() for r in self.results],
            "agent_card": self.agent_card,
        }

    def __iter__(self):
        """Allow iteration over test results."""
        return iter(self.results)

    def __len__(self) -> int:
        return len(self.results)


# ═══════════════════════════════════════════════════════════════════════════════
# LIVE TESTER
# ═══════════════════════════════════════════════════════════════════════════════


class LiveTester:
    """
    Live endpoint tester for A2A agents.

    Tests actual HTTP connectivity and protocol compliance.
    """

    def __init__(
        self,
        base_url: str,
        auth_header: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize the tester.

        Args:
            base_url: Base URL of the A2A agent
            auth_header: Optional Authorization header value
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.auth_header = auth_header
        self.timeout = timeout
        self.agent_card: dict | None = None

    def _headers(self, extra: dict | None = None) -> dict:
        """Build request headers."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "A2A-Version": "0.3",
        }
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        if extra:
            headers.update(extra)
        return headers

    def _jsonrpc_request(
        self,
        method: str,
        params: dict,
        request_id: str | None = None,
    ) -> dict:
        """Build a JSON-RPC 2.0 request."""
        return {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": request_id or str(uuid.uuid4()),
        }

    def _build_message(
        self,
        text: str,
        context_id: str | None = None,
        task_id: str | None = None,
    ) -> dict:
        """Build an A2A message object."""
        message = {
            "role": "user",
            "parts": [{"kind": "text", "text": text}],
            "messageId": str(uuid.uuid4()),
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
        json_data: dict | None = None,
        headers: dict | None = None,
    ) -> tuple[httpx.Response | None, Exception | None, float]:
        """Make HTTP request, return (response, error, duration_ms)."""
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers or self._headers())
                else:
                    response = await client.post(
                        url,
                        json=json_data,
                        headers=headers or self._headers(),
                    )
                duration = (time.perf_counter() - start) * 1000
                return response, None, duration
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return None, e, duration

    # ═══════════════════════════════════════════════════════════════════════════
    # INDIVIDUAL TESTS
    # ═══════════════════════════════════════════════════════════════════════════

    async def test_agent_card_fetch(self) -> TestResult:
        """
        Test: Fetch Agent Card from /.well-known/agent-card.json

        Validates:
        - HTTP 200 response
        - Valid JSON
        - Content-Type header
        - Basic structure
        """
        test_name = "agent_card_fetch"
        url = f"{self.base_url}/.well-known/agent-card.json"

        response, error, duration = await self._request("GET", url)

        if error:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"Connection failed: {type(error).__name__}",
                duration_ms=duration,
                error=str(error),
            )

        if response.status_code == 404:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Agent Card not found at /.well-known/agent-card.json",
                duration_ms=duration,
                error="HTTP 404",
            )

        if response.status_code != 200:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"HTTP {response.status_code}",
                duration_ms=duration,
                error=f"Expected 200, got {response.status_code}",
            )

        # Parse JSON
        try:
            agent_card = response.json()
        except json.JSONDecodeError as e:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Response is not valid JSON",
                duration_ms=duration,
                error=str(e),
            )

        self.agent_card = agent_card

        # Validate structure
        validator = AgentCardValidator()
        report = validator.validate(agent_card)

        content_type = response.headers.get("content-type", "")
        details = {
            "url": url,
            "content_type": content_type,
            "agent_name": agent_card.get("name"),
            "validation_errors": report.error_count,
            "validation_warnings": report.warning_count,
        }

        if report.error_count > 0:
            return TestResult(
                name=test_name,
                status=TestStatus.WARNING,
                message=f"Agent Card has {report.error_count} validation errors",
                duration_ms=duration,
                response=agent_card,
                details=details,
            )

        return TestResult(
            name=test_name,
            status=TestStatus.PASSED,
            message=f"Agent Card fetched successfully",
            duration_ms=duration,
            response=agent_card,
            details=details,
        )

    async def test_message_send(
        self,
        message_text: str = "Hello! This is a test from A2Apex.",
        blocking: bool = True,
    ) -> TestResult:
        """
        Test: Send a message using message/send

        Validates:
        - HTTP 200 response
        - Valid JSON-RPC 2.0 response
        - Response contains Task or Message
        """
        test_name = "message_send"

        message = self._build_message(message_text)
        params = {
            "message": message,
            "configuration": {
                "blocking": blocking,
                "acceptedOutputModes": ["text/plain", "application/json"],
            },
        }
        request = self._jsonrpc_request("message/send", params)

        endpoint = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        response, error, duration = await self._request("POST", endpoint, request)

        if error:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"Request failed: {type(error).__name__}",
                duration_ms=duration,
                request=request,
                error=str(error),
            )

        if response.status_code != 200:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"HTTP {response.status_code}",
                duration_ms=duration,
                request=request,
            )

        try:
            json_response = response.json()
        except json.JSONDecodeError as e:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Invalid JSON response",
                duration_ms=duration,
                request=request,
                error=str(e),
            )

        # Validate JSON-RPC format
        if json_response.get("jsonrpc") != "2.0":
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Not valid JSON-RPC 2.0",
                duration_ms=duration,
                request=request,
                response=json_response,
            )

        # Check for error
        if "error" in json_response:
            err = json_response["error"]
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"JSON-RPC error: {err.get('message', 'Unknown')}",
                duration_ms=duration,
                request=request,
                response=json_response,
                error=f"Code {err.get('code')}: {err.get('message')}",
            )

        if "result" not in json_response:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Missing 'result' field",
                duration_ms=duration,
                request=request,
                response=json_response,
            )

        result = json_response["result"]
        is_task = "id" in result and "status" in result
        is_message = "role" in result and "parts" in result

        details = {
            "response_type": "task" if is_task else ("message" if is_message else "unknown"),
            "endpoint": endpoint,
        }

        if is_task:
            details["task_id"] = result.get("id")
            details["task_state"] = result.get("status", {}).get("state")
            details["context_id"] = result.get("contextId")

            state = result.get("status", {}).get("state")
            valid_states = [s.value for s in TaskState]

            if state not in valid_states:
                return TestResult(
                    name=test_name,
                    status=TestStatus.FAILED,
                    message=f"Invalid task state: {state}",
                    duration_ms=duration,
                    request=request,
                    response=json_response,
                    details=details,
                )

            return TestResult(
                name=test_name,
                status=TestStatus.PASSED,
                message=f"Task created (state: {state})",
                duration_ms=duration,
                request=request,
                response=json_response,
                details=details,
            )

        if is_message:
            details["message_role"] = result.get("role")
            details["parts_count"] = len(result.get("parts", []))

            return TestResult(
                name=test_name,
                status=TestStatus.PASSED,
                message="Direct message response received",
                duration_ms=duration,
                request=request,
                response=json_response,
                details=details,
            )

        return TestResult(
            name=test_name,
            status=TestStatus.WARNING,
            message="Unexpected response structure",
            duration_ms=duration,
            request=request,
            response=json_response,
            details=details,
        )

    async def test_task_get(self, task_id: str) -> TestResult:
        """Test: Get task status using tasks/get."""
        test_name = "task_get"

        request = self._jsonrpc_request("tasks/get", {"id": task_id})
        endpoint = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        response, error, duration = await self._request("POST", endpoint, request)

        if error:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"Request failed: {type(error).__name__}",
                duration_ms=duration,
                request=request,
                error=str(error),
            )

        if response.status_code != 200:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"HTTP {response.status_code}",
                duration_ms=duration,
                request=request,
            )

        try:
            json_response = response.json()
        except json.JSONDecodeError as e:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Invalid JSON response",
                duration_ms=duration,
                request=request,
                error=str(e),
            )

        if "error" in json_response:
            err = json_response["error"]
            code = err.get("code")

            if code == -32001:  # TaskNotFound
                return TestResult(
                    name=test_name,
                    status=TestStatus.WARNING,
                    message="Task not found (may have expired)",
                    duration_ms=duration,
                    request=request,
                    response=json_response,
                    details={"error_code": code},
                )

            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"JSON-RPC error: {err.get('message')}",
                duration_ms=duration,
                request=request,
                response=json_response,
                error=f"Code {code}",
            )

        if "result" not in json_response:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Missing 'result'",
                duration_ms=duration,
                request=request,
                response=json_response,
            )

        result = json_response["result"]
        state = result.get("status", {}).get("state")

        return TestResult(
            name=test_name,
            status=TestStatus.PASSED,
            message=f"Task retrieved (state: {state})",
            duration_ms=duration,
            request=request,
            response=json_response,
            details={
                "task_id": result.get("id"),
                "state": state,
                "has_artifacts": len(result.get("artifacts", [])) > 0,
            },
        )

    async def test_task_cancel(self, task_id: str) -> TestResult:
        """Test: Cancel a task using tasks/cancel."""
        test_name = "task_cancel"

        request = self._jsonrpc_request("tasks/cancel", {"id": task_id})
        endpoint = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        response, error, duration = await self._request("POST", endpoint, request)

        if error:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"Request failed: {type(error).__name__}",
                duration_ms=duration,
                request=request,
                error=str(error),
            )

        if response.status_code != 200:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"HTTP {response.status_code}",
                duration_ms=duration,
                request=request,
            )

        try:
            json_response = response.json()
        except json.JSONDecodeError as e:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Invalid JSON response",
                duration_ms=duration,
                request=request,
                error=str(e),
            )

        if "error" in json_response:
            err = json_response["error"]
            code = err.get("code")

            if code == -32002:  # TaskNotCancelable
                return TestResult(
                    name=test_name,
                    status=TestStatus.PASSED,
                    message="Task not cancelable (already terminal)",
                    duration_ms=duration,
                    request=request,
                    response=json_response,
                    details={"error_code": code},
                )

            if code == -32001:  # TaskNotFound
                return TestResult(
                    name=test_name,
                    status=TestStatus.WARNING,
                    message="Task not found",
                    duration_ms=duration,
                    request=request,
                    response=json_response,
                    details={"error_code": code},
                )

            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"JSON-RPC error: {err.get('message')}",
                duration_ms=duration,
                request=request,
                response=json_response,
            )

        result = json_response.get("result", {})
        state = result.get("status", {}).get("state")

        return TestResult(
            name=test_name,
            status=TestStatus.PASSED,
            message=f"Cancel processed (state: {state})",
            duration_ms=duration,
            request=request,
            response=json_response,
            details={"final_state": state},
        )

    async def test_streaming(
        self,
        message_text: str = "Please count from 1 to 5 slowly.",
    ) -> TestResult:
        """
        Test: Streaming via message/stream (SSE)

        Validates:
        - Server responds with SSE
        - Events have correct format
        """
        test_name = "streaming"

        # Check capability
        if self.agent_card:
            caps = self.agent_card.get("capabilities", {})
            if not caps.get("streaming"):
                return TestResult(
                    name=test_name,
                    status=TestStatus.SKIPPED,
                    message="Streaming not supported",
                    duration_ms=0,
                    details={"streaming_supported": False},
                )

        message = self._build_message(message_text)
        params = {
            "message": message,
            "configuration": {"acceptedOutputModes": ["text/plain"]},
        }
        request = self._jsonrpc_request("message/stream", params)
        endpoint = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url

        events: list[dict] = []
        start = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                headers = self._headers({"Accept": "text/event-stream"})

                async with client.stream("POST", endpoint, json=request, headers=headers) as resp:
                    if resp.status_code != 200:
                        duration = (time.perf_counter() - start) * 1000
                        return TestResult(
                            name=test_name,
                            status=TestStatus.FAILED,
                            message=f"HTTP {resp.status_code}",
                            duration_ms=duration,
                            request=request,
                        )

                    content_type = resp.headers.get("content-type", "")
                    is_sse = "text/event-stream" in content_type

                    buffer = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk

                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)

                            for line in event_text.split("\n"):
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    try:
                                        event_data = json.loads(data_str)
                                        events.append(event_data)
                                    except json.JSONDecodeError:
                                        pass

                            # Check for terminal
                            if events:
                                last = events[-1]
                                if isinstance(last, dict):
                                    result = last.get("result", {})
                                    if "statusUpdate" in result:
                                        if result["statusUpdate"].get("final"):
                                            break
                                    if "task" in result:
                                        state = result["task"].get("status", {}).get("state")
                                        if is_terminal_state(state):
                                            break

                        if len(events) > 50:
                            break

                    duration = (time.perf_counter() - start) * 1000

                    if not events:
                        return TestResult(
                            name=test_name,
                            status=TestStatus.FAILED,
                            message="No SSE events received",
                            duration_ms=duration,
                            request=request,
                            details={"content_type": content_type, "is_sse": is_sse},
                        )

                    return TestResult(
                        name=test_name,
                        status=TestStatus.PASSED,
                        message=f"Streaming works ({len(events)} events)",
                        duration_ms=duration,
                        request=request,
                        details={
                            "events_count": len(events),
                            "content_type": content_type,
                            "is_sse": is_sse,
                        },
                    )

        except httpx.ReadTimeout:
            duration = (time.perf_counter() - start) * 1000
            if events:
                return TestResult(
                    name=test_name,
                    status=TestStatus.PASSED,
                    message=f"Stream timed out with {len(events)} events",
                    duration_ms=duration,
                    request=request,
                    details={"events_count": len(events)},
                )
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Stream timed out with no events",
                duration_ms=duration,
                request=request,
            )
        except Exception as e:
            duration = (time.perf_counter() - start) * 1000
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"Streaming failed: {type(e).__name__}",
                duration_ms=duration,
                request=request,
                error=str(e),
            )

    async def test_invalid_method(self) -> TestResult:
        """Test: Agent handles invalid method gracefully."""
        test_name = "invalid_method"

        request = self._jsonrpc_request("nonexistent/method", {})
        endpoint = self.agent_card.get("url", self.base_url) if self.agent_card else self.base_url
        response, error, duration = await self._request("POST", endpoint, request)

        if error:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message=f"Request failed: {type(error).__name__}",
                duration_ms=duration,
                request=request,
                error=str(error),
            )

        try:
            json_response = response.json()
        except json.JSONDecodeError:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Response not valid JSON",
                duration_ms=duration,
                request=request,
            )

        if "error" not in json_response:
            return TestResult(
                name=test_name,
                status=TestStatus.FAILED,
                message="Agent did not return error for invalid method",
                duration_ms=duration,
                request=request,
                response=json_response,
            )

        err = json_response["error"]
        code = err.get("code")

        if code == -32601:  # MethodNotFound
            return TestResult(
                name=test_name,
                status=TestStatus.PASSED,
                message="Correctly returns MethodNotFoundError (-32601)",
                duration_ms=duration,
                request=request,
                response=json_response,
                details={"error_code": code},
            )

        return TestResult(
            name=test_name,
            status=TestStatus.WARNING,
            message=f"Returns error but wrong code (expected -32601, got {code})",
            duration_ms=duration,
            request=request,
            response=json_response,
            details={"error_code": code, "expected_code": -32601},
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # FULL TEST SUITE
    # ═══════════════════════════════════════════════════════════════════════════

    async def run_all_tests(self) -> TestReport:
        """Run the complete live test suite."""
        report = TestReport(agent_url=self.base_url)
        start = time.perf_counter()

        # Test 1: Agent Card
        result = await self.test_agent_card_fetch()
        report.add_result(result)

        if result.status == TestStatus.FAILED:
            report.total_duration_ms = (time.perf_counter() - start) * 1000
            return report

        report.agent_card = self.agent_card

        # Test 2: Message Send
        send_result = await self.test_message_send()
        report.add_result(send_result)

        task_id = None
        if send_result.details:
            task_id = send_result.details.get("task_id")

        # Test 3: Task Get
        if task_id:
            result = await self.test_task_get(task_id)
            report.add_result(result)
        else:
            report.add_result(
                TestResult(
                    name="task_get",
                    status=TestStatus.SKIPPED,
                    message="No task ID from message/send",
                )
            )

        # Test 4: Streaming
        result = await self.test_streaming()
        report.add_result(result)

        # Test 5: Invalid Method
        result = await self.test_invalid_method()
        report.add_result(result)

        # Test 6: Task Cancel
        if task_id:
            result = await self.test_task_cancel(task_id)
            report.add_result(result)
        else:
            report.add_result(
                TestResult(
                    name="task_cancel",
                    status=TestStatus.SKIPPED,
                    message="No task ID available",
                )
            )

        report.total_duration_ms = (time.perf_counter() - start) * 1000
        return report


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════


async def test_agent(
    url: str,
    auth_header: str | None = None,
    timeout: float = 30.0,
) -> TestReport:
    """
    Run the complete live test suite against an agent.

    Args:
        url: Base URL of the A2A agent
        auth_header: Optional Authorization header
        timeout: Request timeout in seconds

    Returns:
        TestReport with all results
    """
    tester = LiveTester(url, auth_header, timeout)
    return await tester.run_all_tests()


async def test_agent_card_fetch(url: str, timeout: float = 30.0) -> TestResult:
    """Quick test: just fetch the Agent Card."""
    tester = LiveTester(url, timeout=timeout)
    return await tester.test_agent_card_fetch()


async def test_message_send(
    url: str,
    message: str = "Hello!",
    auth_header: str | None = None,
    timeout: float = 30.0,
) -> TestResult:
    """Quick test: send a message."""
    tester = LiveTester(url, auth_header, timeout)
    await tester.test_agent_card_fetch()
    return await tester.test_message_send(message)
