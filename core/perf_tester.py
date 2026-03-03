"""
A2Apex Performance Tester

Basic performance validation for A2A agents.
Tests latency, concurrent handling, and task isolation.
"""

import uuid
import time
import asyncio
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import httpx


class PerfTestStatus(Enum):
    """Status of a performance test."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class PerfTestResult:
    """Result of a single performance test."""
    test_name: str
    status: PerfTestStatus
    message: str
    duration_ms: float = 0
    latency_ms: Optional[float] = None
    threshold_ms: Optional[float] = None
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
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms else None,
            "threshold_ms": self.threshold_ms,
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
class PerfTestReport:
    """Complete report of performance tests."""
    agent_url: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0
    avg_latency_ms: float = 0
    results: list[PerfTestResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def add_result(self, result: PerfTestResult):
        self.results.append(result)
        self.total_tests += 1
        
        if result.status == PerfTestStatus.PASSED:
            self.passed += 1
        elif result.status == PerfTestStatus.FAILED:
            self.failed += 1
        elif result.status == PerfTestStatus.WARNING:
            self.warnings += 1
        elif result.status == PerfTestStatus.SKIPPED:
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
            "summary": {
                "total": self.total_tests,
                "passed": self.passed,
                "failed": self.failed,
                "warnings": self.warnings,
                "skipped": self.skipped,
                "score": round(self.score, 1),
                "avg_latency_ms": round(self.avg_latency_ms, 2)
            },
            "results": [r.to_dict() for r in self.results]
        }


class PerfTester:
    """
    Performance tester for A2A agents.
    
    Tests:
    - Agent Card fetch latency
    - Message send latency
    - Concurrent request handling
    - Task isolation
    """
    
    # Thresholds
    CARD_FETCH_WARN_MS = 2000
    CARD_FETCH_FAIL_MS = 5000
    MESSAGE_SEND_WARN_MS = 10000
    MESSAGE_SEND_FAIL_MS = 30000
    CONCURRENT_REQUESTS = 5
    
    def __init__(
        self,
        base_url: str,
        agent_card: Optional[dict] = None,
        timeout: float = 30.0
    ):
        """
        Initialize the performance tester.
        
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
        """Build base request headers."""
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "A2A-Version": "0.3"
        }
    
    def _build_message_request(self, text: str, request_id: Optional[str] = None) -> dict:
        """Build a message/send JSON-RPC request."""
        return {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": text}],
                    "messageId": str(uuid.uuid4())
                },
                "configuration": {
                    "blocking": True
                }
            },
            "id": request_id or str(uuid.uuid4())
        }
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PERFORMANCE TESTS
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def test_agent_card_latency(self) -> PerfTestResult:
        """
        Test: Measure Agent Card fetch latency.
        
        Thresholds:
        - Pass: <2s
        - Warning: 2-5s
        - Fail: >5s
        """
        test_name = "agent_card_latency"
        card_url = f"{self.base_url}/.well-known/agent-card.json"
        
        start = time.perf_counter()
        
        try:
            async with httpx.AsyncClient(timeout=self.CARD_FETCH_FAIL_MS / 1000 + 1) as client:
                response = await client.get(card_url)
                latency_ms = (time.perf_counter() - start) * 1000
                
                if response.status_code != 200:
                    return PerfTestResult(
                        test_name=test_name,
                        status=PerfTestStatus.FAILED,
                        message=f"HTTP {response.status_code}",
                        duration_ms=latency_ms,
                        latency_ms=latency_ms,
                        threshold_ms=self.CARD_FETCH_WARN_MS
                    )
                
                if latency_ms > self.CARD_FETCH_FAIL_MS:
                    return PerfTestResult(
                        test_name=test_name,
                        status=PerfTestStatus.FAILED,
                        message=f"Agent Card fetch too slow ({latency_ms:.0f}ms > {self.CARD_FETCH_FAIL_MS}ms)",
                        duration_ms=latency_ms,
                        latency_ms=latency_ms,
                        threshold_ms=self.CARD_FETCH_FAIL_MS,
                        suggestion="Cache Agent Card or optimize endpoint"
                    )
                elif latency_ms > self.CARD_FETCH_WARN_MS:
                    return PerfTestResult(
                        test_name=test_name,
                        status=PerfTestStatus.WARNING,
                        message=f"Agent Card fetch slow ({latency_ms:.0f}ms > {self.CARD_FETCH_WARN_MS}ms)",
                        duration_ms=latency_ms,
                        latency_ms=latency_ms,
                        threshold_ms=self.CARD_FETCH_WARN_MS,
                        suggestion="Consider caching Agent Card"
                    )
                else:
                    return PerfTestResult(
                        test_name=test_name,
                        status=PerfTestStatus.PASSED,
                        message=f"Agent Card fetch: {latency_ms:.0f}ms",
                        duration_ms=latency_ms,
                        latency_ms=latency_ms,
                        threshold_ms=self.CARD_FETCH_WARN_MS
                    )
                
        except httpx.TimeoutException:
            duration_ms = (time.perf_counter() - start) * 1000
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.FAILED,
                message="Agent Card fetch timed out",
                duration_ms=duration_ms,
                threshold_ms=self.CARD_FETCH_FAIL_MS,
                suggestion="Agent Card should respond within 5 seconds"
            )
        except Exception as e:
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_message_send_latency(self) -> PerfTestResult:
        """
        Test: Measure message/send latency for a simple task.
        
        Thresholds:
        - Pass: <10s
        - Warning: 10-30s
        - Fail: >30s
        """
        test_name = "message_send_latency"
        
        endpoint_url = await self._get_endpoint_url()
        request = self._build_message_request("Hello! Quick latency test.")
        
        start = time.perf_counter()
        
        try:
            async with httpx.AsyncClient(timeout=self.MESSAGE_SEND_FAIL_MS / 1000 + 5) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                latency_ms = (time.perf_counter() - start) * 1000
                
                if response.status_code != 200:
                    return PerfTestResult(
                        test_name=test_name,
                        status=PerfTestStatus.FAILED,
                        message=f"HTTP {response.status_code}",
                        duration_ms=latency_ms,
                        latency_ms=latency_ms
                    )
                
                json_response = response.json()
                
                # Check for error
                if "error" in json_response:
                    return PerfTestResult(
                        test_name=test_name,
                        status=PerfTestStatus.FAILED,
                        message=f"JSON-RPC error: {json_response['error'].get('message', 'Unknown')}",
                        duration_ms=latency_ms,
                        latency_ms=latency_ms
                    )
                
                # Evaluate latency
                if latency_ms > self.MESSAGE_SEND_FAIL_MS:
                    return PerfTestResult(
                        test_name=test_name,
                        status=PerfTestStatus.FAILED,
                        message=f"Message send too slow ({latency_ms:.0f}ms > {self.MESSAGE_SEND_FAIL_MS}ms)",
                        duration_ms=latency_ms,
                        latency_ms=latency_ms,
                        threshold_ms=self.MESSAGE_SEND_FAIL_MS,
                        suggestion="Optimize message processing or use non-blocking mode"
                    )
                elif latency_ms > self.MESSAGE_SEND_WARN_MS:
                    return PerfTestResult(
                        test_name=test_name,
                        status=PerfTestStatus.WARNING,
                        message=f"Message send slow ({latency_ms:.0f}ms > {self.MESSAGE_SEND_WARN_MS}ms)",
                        duration_ms=latency_ms,
                        latency_ms=latency_ms,
                        threshold_ms=self.MESSAGE_SEND_WARN_MS,
                        suggestion="Consider async processing for simple tasks"
                    )
                else:
                    return PerfTestResult(
                        test_name=test_name,
                        status=PerfTestStatus.PASSED,
                        message=f"Message send: {latency_ms:.0f}ms",
                        duration_ms=latency_ms,
                        latency_ms=latency_ms,
                        threshold_ms=self.MESSAGE_SEND_WARN_MS,
                        details={"task_id": json_response.get("result", {}).get("task", {}).get("id")}
                    )
                
        except httpx.TimeoutException:
            duration_ms = (time.perf_counter() - start) * 1000
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.FAILED,
                message="Message send timed out",
                duration_ms=duration_ms,
                threshold_ms=self.MESSAGE_SEND_FAIL_MS,
                suggestion="Simple tasks should complete within 30 seconds"
            )
        except Exception as e:
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_concurrent_requests(self) -> PerfTestResult:
        """
        Test: Send multiple concurrent requests and verify they all complete.
        """
        test_name = "concurrent_requests"
        
        endpoint_url = await self._get_endpoint_url()
        num_requests = self.CONCURRENT_REQUESTS
        
        async def send_request(index: int) -> dict:
            """Send a single request and return result."""
            request = self._build_message_request(
                f"Concurrent test #{index}",
                f"concurrent-{index}"
            )
            start = time.perf_counter()
            
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        endpoint_url,
                        json=request,
                        headers=self._get_headers()
                    )
                    latency_ms = (time.perf_counter() - start) * 1000
                    
                    return {
                        "index": index,
                        "success": response.status_code == 200,
                        "status_code": response.status_code,
                        "latency_ms": latency_ms,
                        "error": None
                    }
            except Exception as e:
                return {
                    "index": index,
                    "success": False,
                    "error": str(e),
                    "latency_ms": (time.perf_counter() - start) * 1000
                }
        
        start = time.perf_counter()
        
        try:
            # Send all requests concurrently
            tasks = [send_request(i) for i in range(num_requests)]
            results = await asyncio.gather(*tasks)
            
            duration_ms = (time.perf_counter() - start) * 1000
            
            # Analyze results
            successes = sum(1 for r in results if r["success"])
            failures = num_requests - successes
            latencies = [r["latency_ms"] for r in results if r.get("latency_ms")]
            avg_latency = sum(latencies) / len(latencies) if latencies else 0
            max_latency = max(latencies) if latencies else 0
            min_latency = min(latencies) if latencies else 0
            
            if failures == num_requests:
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.FAILED,
                    message=f"All {num_requests} concurrent requests failed",
                    duration_ms=duration_ms,
                    details={"results": results}
                )
            elif failures > 0:
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.WARNING,
                    message=f"{failures}/{num_requests} concurrent requests failed",
                    duration_ms=duration_ms,
                    latency_ms=avg_latency,
                    details={
                        "total": num_requests,
                        "successes": successes,
                        "failures": failures,
                        "avg_latency_ms": avg_latency,
                        "max_latency_ms": max_latency
                    },
                    suggestion="Agent may have concurrency limits"
                )
            else:
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.PASSED,
                    message=f"All {num_requests} concurrent requests succeeded (avg: {avg_latency:.0f}ms)",
                    duration_ms=duration_ms,
                    latency_ms=avg_latency,
                    details={
                        "total": num_requests,
                        "successes": successes,
                        "avg_latency_ms": round(avg_latency, 2),
                        "max_latency_ms": round(max_latency, 2),
                        "min_latency_ms": round(min_latency, 2)
                    }
                )
                
        except Exception as e:
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.FAILED,
                message=f"Concurrent test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_task_isolation(self) -> PerfTestResult:
        """
        Test: Verify tasks don't interfere with each other.
        
        Sends requests with different content and verifies each gets
        the correct response.
        """
        test_name = "task_isolation"
        
        endpoint_url = await self._get_endpoint_url()
        
        # Create distinct requests with identifiable content
        test_values = [
            ("isolation_alpha", "alpha"),
            ("isolation_beta", "beta"),
            ("isolation_gamma", "gamma"),
        ]
        
        async def send_and_verify(request_id: str, marker: str) -> dict:
            """Send a request and verify the response matches."""
            request = self._build_message_request(
                f"Echo: {marker}",
                request_id
            )
            
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        endpoint_url,
                        json=request,
                        headers=self._get_headers()
                    )
                    
                    if response.status_code != 200:
                        return {
                            "request_id": request_id,
                            "marker": marker,
                            "success": False,
                            "error": f"HTTP {response.status_code}"
                        }
                    
                    json_response = response.json()
                    
                    # Check that response ID matches request ID
                    response_id = json_response.get("id")
                    id_matches = response_id == request_id
                    
                    # Check that task content relates to the marker
                    # (This is a basic check - agent may echo the marker)
                    result = json_response.get("result", {})
                    task = result.get("task", {})
                    artifacts = task.get("artifacts", [])
                    history = task.get("history", [])
                    
                    # Check for marker in any text
                    found_marker = False
                    for artifact in artifacts:
                        for part in artifact.get("parts", []):
                            if part.get("kind") == "text":
                                if marker in part.get("text", ""):
                                    found_marker = True
                    
                    for msg in history:
                        if msg.get("role") == "agent":
                            for part in msg.get("parts", []):
                                if part.get("kind") == "text":
                                    if marker in part.get("text", ""):
                                        found_marker = True
                    
                    return {
                        "request_id": request_id,
                        "marker": marker,
                        "success": True,
                        "id_matches": id_matches,
                        "marker_found": found_marker
                    }
                    
            except Exception as e:
                return {
                    "request_id": request_id,
                    "marker": marker,
                    "success": False,
                    "error": str(e)
                }
        
        start = time.perf_counter()
        
        try:
            # Send all requests concurrently
            tasks = [send_and_verify(req_id, marker) for req_id, marker in test_values]
            results = await asyncio.gather(*tasks)
            
            duration_ms = (time.perf_counter() - start) * 1000
            
            # Check for isolation issues
            id_mismatches = [r for r in results if r.get("success") and not r.get("id_matches")]
            marker_issues = [r for r in results if r.get("success") and not r.get("marker_found")]
            failures = [r for r in results if not r.get("success")]
            
            if failures:
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.FAILED,
                    message=f"{len(failures)}/{len(test_values)} requests failed",
                    duration_ms=duration_ms,
                    details={"results": results}
                )
            
            if id_mismatches:
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.FAILED,
                    message="Response IDs don't match request IDs (isolation failure)",
                    duration_ms=duration_ms,
                    details={"mismatches": id_mismatches},
                    suggestion="Ensure response ID matches the request ID"
                )
            
            # Marker not found is a warning (agent may not echo)
            if marker_issues and len(marker_issues) == len(results):
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.WARNING,
                    message="Markers not found in responses (may be expected)",
                    duration_ms=duration_ms,
                    details={"results": results}
                )
            
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.PASSED,
                message=f"Task isolation verified ({len(test_values)} tasks)",
                duration_ms=duration_ms,
                details={
                    "tasks_tested": len(test_values),
                    "id_matches": len([r for r in results if r.get("id_matches")]),
                    "markers_found": len([r for r in results if r.get("marker_found")])
                }
            )
            
        except Exception as e:
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.FAILED,
                message=f"Isolation test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_repeated_requests(self) -> PerfTestResult:
        """
        Test: Send multiple sequential requests and verify consistent performance.
        """
        test_name = "repeated_requests"
        
        endpoint_url = await self._get_endpoint_url()
        num_requests = 5
        latencies = []
        
        start = time.perf_counter()
        
        try:
            for i in range(num_requests):
                request = self._build_message_request(f"Sequential test #{i}")
                req_start = time.perf_counter()
                
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        endpoint_url,
                        json=request,
                        headers=self._get_headers()
                    )
                    latency_ms = (time.perf_counter() - req_start) * 1000
                    
                    if response.status_code == 200:
                        latencies.append(latency_ms)
            
            duration_ms = (time.perf_counter() - start) * 1000
            
            if not latencies:
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.FAILED,
                    message="All sequential requests failed",
                    duration_ms=duration_ms
                )
            
            avg_latency = sum(latencies) / len(latencies)
            max_latency = max(latencies)
            min_latency = min(latencies)
            variance = sum((l - avg_latency) ** 2 for l in latencies) / len(latencies)
            std_dev = variance ** 0.5
            
            # High variance indicates inconsistent performance
            cv = (std_dev / avg_latency) if avg_latency > 0 else 0  # Coefficient of variation
            
            if cv > 0.5:  # >50% variation
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.WARNING,
                    message=f"High latency variance (CV: {cv:.2f})",
                    duration_ms=duration_ms,
                    latency_ms=avg_latency,
                    details={
                        "requests": num_requests,
                        "avg_latency_ms": round(avg_latency, 2),
                        "min_latency_ms": round(min_latency, 2),
                        "max_latency_ms": round(max_latency, 2),
                        "std_dev_ms": round(std_dev, 2),
                        "coefficient_of_variation": round(cv, 2)
                    },
                    suggestion="Performance is inconsistent - check for resource contention"
                )
            
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.PASSED,
                message=f"Consistent performance over {num_requests} requests (avg: {avg_latency:.0f}ms)",
                duration_ms=duration_ms,
                latency_ms=avg_latency,
                details={
                    "requests": num_requests,
                    "successful": len(latencies),
                    "avg_latency_ms": round(avg_latency, 2),
                    "min_latency_ms": round(min_latency, 2),
                    "max_latency_ms": round(max_latency, 2),
                    "std_dev_ms": round(std_dev, 2),
                    "coefficient_of_variation": round(cv, 2)
                }
            )
            
        except Exception as e:
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.FAILED,
                message=f"Sequential test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_cold_start_vs_warm(self) -> PerfTestResult:
        """
        Test: Compare first request (cold start) vs subsequent requests.
        """
        test_name = "cold_vs_warm_start"
        
        endpoint_url = await self._get_endpoint_url()
        
        start = time.perf_counter()
        
        try:
            # First request (potentially cold)
            request1 = self._build_message_request("Cold start test")
            req1_start = time.perf_counter()
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response1 = await client.post(
                    endpoint_url,
                    json=request1,
                    headers=self._get_headers()
                )
                cold_latency = (time.perf_counter() - req1_start) * 1000
            
            if response1.status_code != 200:
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.FAILED,
                    message="Cold start request failed",
                    duration_ms=(time.perf_counter() - start) * 1000
                )
            
            # Wait a moment, then send warm request
            await asyncio.sleep(0.1)
            
            request2 = self._build_message_request("Warm request test")
            req2_start = time.perf_counter()
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response2 = await client.post(
                    endpoint_url,
                    json=request2,
                    headers=self._get_headers()
                )
                warm_latency = (time.perf_counter() - req2_start) * 1000
            
            if response2.status_code != 200:
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.FAILED,
                    message="Warm request failed",
                    duration_ms=(time.perf_counter() - start) * 1000
                )
            
            duration_ms = (time.perf_counter() - start) * 1000
            
            # Calculate cold start penalty
            cold_start_penalty = cold_latency - warm_latency
            cold_start_ratio = cold_latency / warm_latency if warm_latency > 0 else 1
            
            details = {
                "cold_latency_ms": round(cold_latency, 2),
                "warm_latency_ms": round(warm_latency, 2),
                "cold_start_penalty_ms": round(cold_start_penalty, 2),
                "cold_start_ratio": round(cold_start_ratio, 2)
            }
            
            if cold_start_ratio > 3:
                return PerfTestResult(
                    test_name=test_name,
                    status=PerfTestStatus.WARNING,
                    message=f"Significant cold start penalty ({cold_start_ratio:.1f}x slower)",
                    duration_ms=duration_ms,
                    latency_ms=cold_latency,
                    details=details,
                    suggestion="Consider keep-alive or pre-warming strategies"
                )
            
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.PASSED,
                message=f"Cold: {cold_latency:.0f}ms, Warm: {warm_latency:.0f}ms ({cold_start_ratio:.1f}x)",
                duration_ms=duration_ms,
                latency_ms=(cold_latency + warm_latency) / 2,
                details=details
            )
            
        except Exception as e:
            return PerfTestResult(
                test_name=test_name,
                status=PerfTestStatus.FAILED,
                message=f"Cold/warm test failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FULL TEST SUITE
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def run_all_tests(self) -> PerfTestReport:
        """
        Run the complete performance test suite.
        
        Returns:
            PerfTestReport with all test results
        """
        report = PerfTestReport(agent_url=self.base_url)
        
        # Run all performance tests
        tests = [
            self.test_agent_card_latency,
            self.test_message_send_latency,
            self.test_cold_start_vs_warm,
            self.test_repeated_requests,
            self.test_concurrent_requests,
            self.test_task_isolation,
        ]
        
        latencies = []
        
        for test_func in tests:
            try:
                result = await test_func()
                report.add_result(result)
                
                if result.latency_ms:
                    latencies.append(result.latency_ms)
                    
            except Exception as e:
                report.add_result(PerfTestResult(
                    test_name=test_func.__name__.replace("test_", ""),
                    status=PerfTestStatus.FAILED,
                    message=f"Test crashed: {type(e).__name__}",
                    error=str(e)
                ))
        
        # Calculate average latency
        if latencies:
            report.avg_latency_ms = sum(latencies) / len(latencies)
        
        return report


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def run_perf_tests(
    agent_url: str,
    agent_card: Optional[dict] = None,
    timeout: float = 30.0
) -> PerfTestReport:
    """
    Run the complete performance test suite against an agent.
    
    Args:
        agent_url: Base URL of the A2A agent
        agent_card: Optional pre-fetched Agent Card
        timeout: Request timeout in seconds
        
    Returns:
        PerfTestReport with all test results
    """
    tester = PerfTester(agent_url, agent_card, timeout)
    return await tester.run_all_tests()
