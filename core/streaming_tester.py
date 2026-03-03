"""
A2Apex Streaming Tester

Tests Server-Sent Events (SSE) streaming endpoints.
Validates streaming behavior and event format compliance.
"""

import uuid
import time
import json
import asyncio
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import httpx


class StreamTestStatus(Enum):
    """Status of a streaming test."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class StreamTestResult:
    """Result of a single streaming test."""
    test_name: str
    status: StreamTestStatus
    message: str
    duration_ms: float = 0
    events_received: int = 0
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
            "events_received": self.events_received,
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
class StreamTestReport:
    """Complete report of streaming tests."""
    agent_url: str
    streaming_supported: bool = False
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0
    results: list[StreamTestResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def add_result(self, result: StreamTestResult):
        self.results.append(result)
        self.total_tests += 1
        
        if result.status == StreamTestStatus.PASSED:
            self.passed += 1
        elif result.status == StreamTestStatus.FAILED:
            self.failed += 1
        elif result.status == StreamTestStatus.WARNING:
            self.warnings += 1
        elif result.status == StreamTestStatus.SKIPPED:
            self.skipped += 1
    
    @property
    def score(self) -> float:
        if self.total_tests == 0:
            return 0
        return (self.passed / self.total_tests) * 100
    
    def to_dict(self) -> dict:
        return {
            "agent_url": self.agent_url,
            "timestamp": self.timestamp,
            "streaming_supported": self.streaming_supported,
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


# Valid task states for state transition validation
VALID_STATES = ["submitted", "working", "input-required", "auth-required", 
                "completed", "failed", "canceled", "rejected"]

TERMINAL_STATES = ["completed", "failed", "canceled", "rejected"]


class StreamingTester:
    """
    Streaming tester for A2A agents.
    
    Tests SSE streaming functionality:
    - Connection to message/stream
    - Event format validation
    - State transition validation
    - Artifact streaming
    - Timeout handling
    """
    
    def __init__(
        self,
        base_url: str,
        agent_card: Optional[dict] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the streaming tester.
        
        Args:
            base_url: Base URL of the A2A agent
            agent_card: Agent Card JSON (if already fetched)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.agent_card = agent_card
        self.timeout = timeout
        self._endpoint_url: Optional[str] = None
    
    async def _fetch_agent_card(self) -> Optional[dict]:
        """Fetch agent card if not already available."""
        if self.agent_card:
            return self.agent_card
        
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/.well-known/agent-card.json")
                if response.status_code == 200:
                    self.agent_card = response.json()
                    return self.agent_card
        except Exception:
            pass
        return None
    
    async def _get_endpoint_url(self) -> str:
        """Get the A2A endpoint URL."""
        if self._endpoint_url:
            return self._endpoint_url
        
        card = await self._fetch_agent_card()
        if card:
            self._endpoint_url = card.get("url", f"{self.base_url}/a2a")
        else:
            self._endpoint_url = f"{self.base_url}/a2a"
        
        return self._endpoint_url
    
    def _get_headers(self) -> dict:
        """Build request headers for SSE."""
        return {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "A2A-Version": "0.3"
        }
    
    def _build_stream_request(self, message_text: str) -> dict:
        """Build a message/stream JSON-RPC request."""
        return {
            "jsonrpc": "2.0",
            "method": "message/stream",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": message_text}],
                    "messageId": str(uuid.uuid4())
                }
            },
            "id": str(uuid.uuid4())
        }
    
    def _parse_sse_events(self, raw_data: str) -> list[dict]:
        """Parse SSE events from raw response data."""
        events = []
        current_event_type = None
        current_data = []
        
        for line in raw_data.split("\n"):
            line = line.strip()
            
            if line.startswith("event:"):
                current_event_type = line[6:].strip()
            elif line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str:
                    try:
                        data = json.loads(data_str)
                        events.append({
                            "event_type": current_event_type or "message",
                            "data": data
                        })
                    except json.JSONDecodeError:
                        # Non-JSON data
                        events.append({
                            "event_type": current_event_type or "message",
                            "raw": data_str
                        })
            elif line == "" and current_event_type:
                current_event_type = None
        
        return events
    
    def _extract_states_from_events(self, events: list[dict]) -> list[str]:
        """Extract task states from SSE events."""
        states = []
        
        for event in events:
            data = event.get("data", {})
            
            # Check for task state in result
            if "result" in data:
                result = data["result"]
                
                # From task object
                if "task" in result:
                    state = result["task"].get("status", {}).get("state")
                    if state and state not in states:
                        states.append(state)
                
                # From status update
                if "statusUpdate" in result:
                    state = result["statusUpdate"].get("status", {}).get("state")
                    if state and (not states or states[-1] != state):
                        states.append(state)
        
        return states
    
    # ═══════════════════════════════════════════════════════════════════════════
    # STREAMING TESTS
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def test_streaming_supported(self) -> StreamTestResult:
        """
        Test: Check if streaming is declared in capabilities.
        """
        test_name = "streaming_supported"
        start = time.perf_counter()
        
        card = await self._fetch_agent_card()
        duration_ms = (time.perf_counter() - start) * 1000
        
        if not card:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.SKIPPED,
                message="Cannot fetch Agent Card",
                duration_ms=duration_ms
            )
        
        capabilities = card.get("capabilities", {})
        streaming = capabilities.get("streaming", False)
        
        if streaming:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.PASSED,
                message="Streaming is declared as supported",
                duration_ms=duration_ms,
                details={"capabilities.streaming": True}
            )
        else:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.SKIPPED,
                message="Streaming not supported (capabilities.streaming=false)",
                duration_ms=duration_ms,
                details={"capabilities.streaming": False}
            )
    
    async def test_stream_connection(self) -> StreamTestResult:
        """
        Test: Connect to message/stream endpoint and receive events.
        """
        test_name = "stream_connection"
        start = time.perf_counter()
        
        # Check if streaming is supported
        card = await self._fetch_agent_card()
        if card and not card.get("capabilities", {}).get("streaming", False):
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.SKIPPED,
                message="Streaming not supported",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        endpoint_url = await self._get_endpoint_url()
        request = self._build_stream_request("Hello, testing streaming!")
        
        events_received = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                ) as response:
                    
                    if response.status_code != 200:
                        duration_ms = (time.perf_counter() - start) * 1000
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.FAILED,
                            message=f"HTTP {response.status_code}",
                            duration_ms=duration_ms,
                            error=f"Expected HTTP 200, got {response.status_code}"
                        )
                    
                    # Check content type
                    content_type = response.headers.get("content-type", "")
                    is_sse = "text/event-stream" in content_type
                    
                    # Read events with timeout
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        
                        # Parse events from buffer
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            
                            for line in event_text.split("\n"):
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    try:
                                        event_data = json.loads(data_str)
                                        events_received.append(event_data)
                                        
                                        # Check for terminal state
                                        result = event_data.get("result", {})
                                        
                                        # Check statusUpdate final flag
                                        if result.get("statusUpdate", {}).get("final"):
                                            break
                                        
                                        # Check task state
                                        task = result.get("task", {})
                                        state = task.get("status", {}).get("state")
                                        if state in TERMINAL_STATES:
                                            break
                                    except json.JSONDecodeError:
                                        pass
                        
                        # Limit events
                        if len(events_received) > 50:
                            break
                    
                    duration_ms = (time.perf_counter() - start) * 1000
                    
                    if not events_received:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.FAILED,
                            message="No SSE events received",
                            duration_ms=duration_ms,
                            details={"content_type": content_type, "is_sse": is_sse}
                        )
                    
                    return StreamTestResult(
                        test_name=test_name,
                        status=StreamTestStatus.PASSED,
                        message=f"Successfully connected and received {len(events_received)} event(s)",
                        duration_ms=duration_ms,
                        events_received=len(events_received),
                        details={
                            "content_type": content_type,
                            "is_sse": is_sse,
                            "first_event_keys": list(events_received[0].keys()) if events_received else []
                        }
                    )
                    
        except httpx.TimeoutException:
            duration_ms = (time.perf_counter() - start) * 1000
            if events_received:
                return StreamTestResult(
                    test_name=test_name,
                    status=StreamTestStatus.WARNING,
                    message=f"Stream timed out but received {len(events_received)} event(s)",
                    duration_ms=duration_ms,
                    events_received=len(events_received)
                )
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.FAILED,
                message="Stream timed out with no events",
                duration_ms=duration_ms
            )
        except Exception as e:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.FAILED,
                message=f"Streaming failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_sse_event_format(self) -> StreamTestResult:
        """
        Test: Verify SSE events have correct format.
        """
        test_name = "sse_event_format"
        start = time.perf_counter()
        
        # Check if streaming is supported
        card = await self._fetch_agent_card()
        if card and not card.get("capabilities", {}).get("streaming", False):
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.SKIPPED,
                message="Streaming not supported",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        endpoint_url = await self._get_endpoint_url()
        request = self._build_stream_request("Testing SSE format")
        
        events_raw = []
        events_valid = 0
        events_invalid = 0
        issues = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                ) as response:
                    
                    if response.status_code != 200:
                        duration_ms = (time.perf_counter() - start) * 1000
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.FAILED,
                            message=f"HTTP {response.status_code}",
                            duration_ms=duration_ms
                        )
                    
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            events_raw.append(event_text)
                            
                            has_data = False
                            data_is_json = False
                            
                            for line in event_text.split("\n"):
                                if line.startswith("data:"):
                                    has_data = True
                                    data_str = line[5:].strip()
                                    try:
                                        data = json.loads(data_str)
                                        data_is_json = True
                                        
                                        # Validate JSON-RPC wrapper
                                        if "jsonrpc" not in data:
                                            issues.append("Event missing 'jsonrpc' field")
                                        if "result" not in data and "error" not in data:
                                            issues.append("Event missing 'result' or 'error' field")
                                        
                                        # Check for terminal
                                        result = data.get("result", {})
                                        if result.get("statusUpdate", {}).get("final"):
                                            break
                                        task = result.get("task", {})
                                        if task.get("status", {}).get("state") in TERMINAL_STATES:
                                            break
                                    except json.JSONDecodeError:
                                        issues.append(f"Event data is not valid JSON")
                            
                            if has_data and data_is_json:
                                events_valid += 1
                            else:
                                events_invalid += 1
                        
                        if len(events_raw) > 50:
                            break
                    
                    duration_ms = (time.perf_counter() - start) * 1000
                    
                    if not events_raw:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.FAILED,
                            message="No events received",
                            duration_ms=duration_ms
                        )
                    
                    if events_invalid > 0 or issues:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.WARNING,
                            message=f"Some events have format issues ({events_invalid} invalid)",
                            duration_ms=duration_ms,
                            events_received=len(events_raw),
                            details={
                                "valid_events": events_valid,
                                "invalid_events": events_invalid,
                                "issues": issues[:5]  # First 5 issues
                            },
                            suggestion="SSE events should have 'data: <json>' format with JSON-RPC structure"
                        )
                    
                    return StreamTestResult(
                        test_name=test_name,
                        status=StreamTestStatus.PASSED,
                        message=f"All {events_valid} events have valid SSE format",
                        duration_ms=duration_ms,
                        events_received=events_valid
                    )
                    
        except Exception as e:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.FAILED,
                message=f"Test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_state_transition_order(self) -> StreamTestResult:
        """
        Test: Verify state transitions follow A2A state machine rules.
        """
        test_name = "state_transition_order"
        start = time.perf_counter()
        
        # Check if streaming is supported
        card = await self._fetch_agent_card()
        if card and not card.get("capabilities", {}).get("streaming", False):
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.SKIPPED,
                message="Streaming not supported",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        endpoint_url = await self._get_endpoint_url()
        request = self._build_stream_request("Testing state transitions")
        
        events = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                ) as response:
                    
                    if response.status_code != 200:
                        duration_ms = (time.perf_counter() - start) * 1000
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.FAILED,
                            message=f"HTTP {response.status_code}",
                            duration_ms=duration_ms
                        )
                    
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            
                            for line in event_text.split("\n"):
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    try:
                                        data = json.loads(data_str)
                                        events.append({"data": data})
                                        
                                        # Check for terminal
                                        result = data.get("result", {})
                                        if result.get("statusUpdate", {}).get("final"):
                                            break
                                        task = result.get("task", {})
                                        if task.get("status", {}).get("state") in TERMINAL_STATES:
                                            break
                                    except json.JSONDecodeError:
                                        pass
                        
                        if len(events) > 50:
                            break
                    
                    duration_ms = (time.perf_counter() - start) * 1000
                    
                    # Extract states
                    states = self._extract_states_from_events(events)
                    
                    if not states:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.WARNING,
                            message="No state transitions observed in events",
                            duration_ms=duration_ms,
                            events_received=len(events)
                        )
                    
                    # Validate state transitions
                    # Valid transitions based on A2A state machine
                    valid_from = {
                        "submitted": ["working", "completed", "failed", "rejected", "canceled"],
                        "working": ["input-required", "auth-required", "completed", "failed", "canceled"],
                        "input-required": ["working", "completed", "failed", "canceled"],
                        "auth-required": ["working", "completed", "failed", "canceled"],
                    }
                    
                    invalid_transitions = []
                    for i in range(len(states) - 1):
                        from_state = states[i]
                        to_state = states[i + 1]
                        
                        # Check if transition is valid
                        if from_state in valid_from:
                            if to_state not in valid_from[from_state]:
                                invalid_transitions.append(f"{from_state} → {to_state}")
                        elif from_state in TERMINAL_STATES:
                            invalid_transitions.append(f"{from_state} → {to_state} (from terminal)")
                    
                    if invalid_transitions:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.FAILED,
                            message=f"Invalid state transitions detected",
                            duration_ms=duration_ms,
                            events_received=len(events),
                            details={
                                "states_observed": states,
                                "invalid_transitions": invalid_transitions
                            },
                            suggestion="Review A2A state machine rules"
                        )
                    
                    # Check if ended in terminal state
                    final_state = states[-1] if states else None
                    reached_terminal = final_state in TERMINAL_STATES
                    
                    return StreamTestResult(
                        test_name=test_name,
                        status=StreamTestStatus.PASSED,
                        message=f"Valid state transitions: {' → '.join(states)}",
                        duration_ms=duration_ms,
                        events_received=len(events),
                        details={
                            "states": states,
                            "reached_terminal": reached_terminal,
                            "final_state": final_state
                        }
                    )
                    
        except Exception as e:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.FAILED,
                message=f"Test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_artifact_streaming(self) -> StreamTestResult:
        """
        Test: Verify artifact updates are streamed correctly.
        """
        test_name = "artifact_streaming"
        start = time.perf_counter()
        
        # Check if streaming is supported
        card = await self._fetch_agent_card()
        if card and not card.get("capabilities", {}).get("streaming", False):
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.SKIPPED,
                message="Streaming not supported",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        endpoint_url = await self._get_endpoint_url()
        request = self._build_stream_request("Testing artifact streaming - please provide some output")
        
        artifact_updates = []
        events_count = 0
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                ) as response:
                    
                    if response.status_code != 200:
                        duration_ms = (time.perf_counter() - start) * 1000
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.FAILED,
                            message=f"HTTP {response.status_code}",
                            duration_ms=duration_ms
                        )
                    
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            
                            for line in event_text.split("\n"):
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    try:
                                        data = json.loads(data_str)
                                        events_count += 1
                                        
                                        result = data.get("result", {})
                                        
                                        # Check for artifact update
                                        if "artifactUpdate" in result:
                                            artifact_updates.append(result["artifactUpdate"])
                                        
                                        # Check for task with artifacts
                                        task = result.get("task", {})
                                        if task.get("artifacts"):
                                            for art in task["artifacts"]:
                                                if art not in artifact_updates:
                                                    artifact_updates.append(art)
                                        
                                        # Check for terminal
                                        if result.get("statusUpdate", {}).get("final"):
                                            break
                                        if task.get("status", {}).get("state") in TERMINAL_STATES:
                                            break
                                    except json.JSONDecodeError:
                                        pass
                        
                        if events_count > 50:
                            break
                    
                    duration_ms = (time.perf_counter() - start) * 1000
                    
                    if not artifact_updates:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.WARNING,
                            message="No artifact updates observed (agent may not produce artifacts)",
                            duration_ms=duration_ms,
                            events_received=events_count
                        )
                    
                    # Validate artifact structure
                    valid_artifacts = 0
                    for artifact in artifact_updates:
                        # Artifacts should have basic structure
                        if isinstance(artifact, dict):
                            has_id = "artifactId" in artifact or "id" in artifact
                            has_parts = "parts" in artifact
                            if has_id or has_parts:
                                valid_artifacts += 1
                    
                    return StreamTestResult(
                        test_name=test_name,
                        status=StreamTestStatus.PASSED,
                        message=f"Received {len(artifact_updates)} artifact update(s)",
                        duration_ms=duration_ms,
                        events_received=events_count,
                        details={
                            "artifact_count": len(artifact_updates),
                            "valid_artifacts": valid_artifacts
                        }
                    )
                    
        except Exception as e:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.FAILED,
                message=f"Test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_final_event_sent(self) -> StreamTestResult:
        """
        Test: Verify stream sends a final event to properly close.
        """
        test_name = "final_event_sent"
        start = time.perf_counter()
        
        # Check if streaming is supported
        card = await self._fetch_agent_card()
        if card and not card.get("capabilities", {}).get("streaming", False):
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.SKIPPED,
                message="Streaming not supported",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        endpoint_url = await self._get_endpoint_url()
        request = self._build_stream_request("Quick test for final event")
        
        events = []
        found_final = False
        final_state = None
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                ) as response:
                    
                    if response.status_code != 200:
                        duration_ms = (time.perf_counter() - start) * 1000
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.FAILED,
                            message=f"HTTP {response.status_code}",
                            duration_ms=duration_ms
                        )
                    
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            
                            for line in event_text.split("\n"):
                                if line.startswith("data:"):
                                    data_str = line[5:].strip()
                                    try:
                                        data = json.loads(data_str)
                                        events.append(data)
                                        
                                        result = data.get("result", {})
                                        
                                        # Check for final flag
                                        status_update = result.get("statusUpdate", {})
                                        if status_update.get("final"):
                                            found_final = True
                                            final_state = status_update.get("status", {}).get("state")
                                            break
                                        
                                        # Check task terminal state
                                        task = result.get("task", {})
                                        state = task.get("status", {}).get("state")
                                        if state in TERMINAL_STATES:
                                            found_final = True
                                            final_state = state
                                            break
                                    except json.JSONDecodeError:
                                        pass
                        
                        if found_final or len(events) > 50:
                            break
                    
                    duration_ms = (time.perf_counter() - start) * 1000
                    
                    if found_final:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.PASSED,
                            message=f"Stream properly closed with final event (state: {final_state})",
                            duration_ms=duration_ms,
                            events_received=len(events),
                            details={"final_state": final_state}
                        )
                    else:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.WARNING,
                            message="No final event detected (stream may not close properly)",
                            duration_ms=duration_ms,
                            events_received=len(events),
                            suggestion="Send statusUpdate with final:true or task in terminal state"
                        )
                    
        except Exception as e:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.FAILED,
                message=f"Test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_content_type_header(self) -> StreamTestResult:
        """
        Test: Verify response has correct Content-Type for SSE.
        """
        test_name = "content_type_header"
        start = time.perf_counter()
        
        # Check if streaming is supported
        card = await self._fetch_agent_card()
        if card and not card.get("capabilities", {}).get("streaming", False):
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.SKIPPED,
                message="Streaming not supported",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        endpoint_url = await self._get_endpoint_url()
        request = self._build_stream_request("Content-Type test")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST",
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                ) as response:
                    duration_ms = (time.perf_counter() - start) * 1000
                    
                    content_type = response.headers.get("content-type", "")
                    
                    if "text/event-stream" in content_type:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.PASSED,
                            message="Correct Content-Type: text/event-stream",
                            duration_ms=duration_ms,
                            details={"content_type": content_type}
                        )
                    elif "application/json" in content_type:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.WARNING,
                            message="Response is JSON, not SSE stream",
                            duration_ms=duration_ms,
                            details={"content_type": content_type},
                            suggestion="Use Content-Type: text/event-stream for SSE"
                        )
                    else:
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.WARNING,
                            message=f"Unexpected Content-Type: {content_type}",
                            duration_ms=duration_ms,
                            details={"content_type": content_type},
                            suggestion="Use Content-Type: text/event-stream for SSE"
                        )
                    
        except Exception as e:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.FAILED,
                message=f"Test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_stream_timeout_handling(self) -> StreamTestResult:
        """
        Test: Verify graceful handling when stream times out.
        """
        test_name = "stream_timeout_handling"
        start = time.perf_counter()
        
        # Check if streaming is supported
        card = await self._fetch_agent_card()
        if card and not card.get("capabilities", {}).get("streaming", False):
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.SKIPPED,
                message="Streaming not supported",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        endpoint_url = await self._get_endpoint_url()
        request = self._build_stream_request("Timeout test - please respond quickly")
        
        events_received = 0
        
        try:
            # Use short timeout
            async with httpx.AsyncClient(timeout=3.0) as client:
                async with client.stream(
                    "POST",
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                ) as response:
                    
                    if response.status_code != 200:
                        duration_ms = (time.perf_counter() - start) * 1000
                        return StreamTestResult(
                            test_name=test_name,
                            status=StreamTestStatus.FAILED,
                            message=f"HTTP {response.status_code}",
                            duration_ms=duration_ms
                        )
                    
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            
                            for line in event_text.split("\n"):
                                if line.startswith("data:"):
                                    events_received += 1
                        
                        if events_received > 20:
                            break
                    
                    duration_ms = (time.perf_counter() - start) * 1000
                    
                    return StreamTestResult(
                        test_name=test_name,
                        status=StreamTestStatus.PASSED,
                        message=f"Stream completed within timeout ({events_received} events)",
                        duration_ms=duration_ms,
                        events_received=events_received
                    )
                    
        except httpx.TimeoutException:
            duration_ms = (time.perf_counter() - start) * 1000
            
            if events_received > 0:
                return StreamTestResult(
                    test_name=test_name,
                    status=StreamTestStatus.PASSED,
                    message=f"Received {events_received} events before timeout (graceful)",
                    duration_ms=duration_ms,
                    events_received=events_received
                )
            else:
                return StreamTestResult(
                    test_name=test_name,
                    status=StreamTestStatus.WARNING,
                    message="Timed out with no events (may indicate slow response)",
                    duration_ms=duration_ms,
                    suggestion="Consider sending initial event quickly"
                )
        except Exception as e:
            return StreamTestResult(
                test_name=test_name,
                status=StreamTestStatus.FAILED,
                message=f"Test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FULL TEST SUITE
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def run_all_tests(self) -> StreamTestReport:
        """
        Run the complete streaming test suite.
        
        Returns:
            StreamTestReport with all test results
        """
        report = StreamTestReport(agent_url=self.base_url)
        
        # First check if streaming is supported
        support_result = await self.test_streaming_supported()
        report.add_result(support_result)
        report.streaming_supported = support_result.status == StreamTestStatus.PASSED
        
        # Run remaining tests only if streaming might be supported
        if support_result.status != StreamTestStatus.SKIPPED or not self.agent_card:
            tests = [
                self.test_content_type_header,
                self.test_stream_connection,
                self.test_sse_event_format,
                self.test_state_transition_order,
                self.test_final_event_sent,
                self.test_artifact_streaming,
                self.test_stream_timeout_handling,
            ]
            
            for test_func in tests:
                try:
                    result = await test_func()
                    report.add_result(result)
                except Exception as e:
                    report.add_result(StreamTestResult(
                        test_name=test_func.__name__.replace("test_", ""),
                        status=StreamTestStatus.FAILED,
                        message=f"Test crashed: {type(e).__name__}",
                        error=str(e)
                    ))
        
        return report


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def run_streaming_tests(
    agent_url: str,
    agent_card: Optional[dict] = None,
    timeout: float = 30.0
) -> StreamTestReport:
    """
    Run the complete streaming test suite against an agent.
    
    Args:
        agent_url: Base URL of the A2A agent
        agent_card: Optional pre-fetched Agent Card
        timeout: Request timeout in seconds
        
    Returns:
        StreamTestReport with all test results
    """
    tester = StreamingTester(agent_url, agent_card, timeout)
    return await tester.run_all_tests()
