"""
A2Apex Task Tester

Send test tasks to A2A agents and validate their responses.
"""

import uuid
import json
import asyncio
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import httpx


class TaskState(Enum):
    """Valid A2A task states."""
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    AUTH_REQUIRED = "auth-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    REJECTED = "rejected"


# Terminal states where no more messages can be sent
TERMINAL_STATES = {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED, TaskState.REJECTED}

# States that can transition to other states
IN_PROGRESS_STATES = {TaskState.SUBMITTED, TaskState.WORKING, TaskState.INPUT_REQUIRED, TaskState.AUTH_REQUIRED}


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    passed: bool
    message: str
    details: Optional[dict] = None
    duration_ms: Optional[float] = None


@dataclass
class TaskTestReport:
    """Complete report of task testing."""
    success: bool
    agent_url: str
    message_sent: str
    response_received: bool = False
    response_valid: bool = False
    task_id: Optional[str] = None
    final_state: Optional[str] = None
    artifacts: list = field(default_factory=list)
    tests: list[TestResult] = field(default_factory=list)
    raw_response: Optional[dict] = None
    error: Optional[str] = None
    duration_ms: float = 0
    
    @property
    def passed_count(self) -> int:
        return sum(1 for t in self.tests if t.passed)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for t in self.tests if not t.passed)
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "agent_url": self.agent_url,
            "message_sent": self.message_sent,
            "response_received": self.response_received,
            "response_valid": self.response_valid,
            "task_id": self.task_id,
            "final_state": self.final_state,
            "artifacts": self.artifacts,
            "summary": {
                "total_tests": len(self.tests),
                "passed": self.passed_count,
                "failed": self.failed_count
            },
            "tests": [
                {
                    "name": t.name,
                    "passed": t.passed,
                    "message": t.message,
                    "details": t.details,
                    "duration_ms": t.duration_ms
                }
                for t in self.tests
            ],
            "error": self.error,
            "duration_ms": self.duration_ms
        }


class TaskTester:
    """Test task execution against an A2A agent."""
    
    def __init__(
        self,
        agent_url: str,
        auth_header: Optional[str] = None,
        timeout: float = 60.0
    ):
        """
        Initialize the task tester.
        
        Args:
            agent_url: Base URL of the A2A agent
            auth_header: Optional Authorization header value
            timeout: Request timeout in seconds
        """
        self.agent_url = agent_url.rstrip("/")
        self.auth_header = auth_header
        self.timeout = timeout
        self.tests: list[TestResult] = []
    
    def _add_test(
        self,
        name: str,
        passed: bool,
        message: str,
        details: Optional[dict] = None,
        duration_ms: Optional[float] = None
    ):
        self.tests.append(TestResult(
            name=name,
            passed=passed,
            message=message,
            details=details,
            duration_ms=duration_ms
        ))
    
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
            "parts": [
                {
                    "kind": "text",
                    "text": text
                }
            ],
            "messageId": str(uuid.uuid4())
        }
        
        if context_id:
            message["contextId"] = context_id
        if task_id:
            message["taskId"] = task_id
            
        return message
    
    def _validate_task_response(self, response: dict) -> tuple[bool, str]:
        """Validate that a response contains a valid Task object."""
        if "result" not in response:
            if "error" in response:
                error = response["error"]
                return False, f"JSON-RPC error: {error.get('message', 'Unknown error')}"
            return False, "Response missing 'result' field"
        
        result = response["result"]
        
        # Check if it's a Task (has id and status) or a Message (has role and parts)
        if "id" in result and "status" in result:
            # It's a Task
            task = result
            
            # Validate task ID
            if not isinstance(task.get("id"), str):
                return False, "Task missing valid 'id' field"
            
            # Validate status
            status = task.get("status", {})
            if not isinstance(status, dict):
                return False, "Task status must be an object"
            
            state = status.get("state")
            valid_states = [s.value for s in TaskState]
            if state not in valid_states:
                return False, f"Invalid task state: {state}"
            
            return True, f"Valid Task response with state: {state}"
        
        elif "role" in result and "parts" in result:
            # It's a direct Message response
            if result.get("role") != "agent":
                return False, "Message response should have role 'agent'"
            
            parts = result.get("parts", [])
            if not isinstance(parts, list) or len(parts) == 0:
                return False, "Message must have at least one part"
            
            return True, "Valid direct Message response"
        
        return False, "Response is neither a valid Task nor Message"
    
    def _validate_task_object(self, task: dict) -> list[TestResult]:
        """Validate the structure of a Task object."""
        results = []
        
        # Check required fields
        required_fields = ["id", "status"]
        for field in required_fields:
            if field not in task:
                results.append(TestResult(
                    name=f"task.{field}",
                    passed=False,
                    message=f"Task missing required field: {field}"
                ))
        
        # Validate status object
        status = task.get("status", {})
        if isinstance(status, dict):
            if "state" not in status:
                results.append(TestResult(
                    name="task.status.state",
                    passed=False,
                    message="Task status missing 'state' field"
                ))
            
            # Validate timestamp if present
            if "timestamp" in status:
                timestamp = status["timestamp"]
                try:
                    # Try to parse ISO 8601 timestamp
                    if isinstance(timestamp, str):
                        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                        results.append(TestResult(
                            name="task.status.timestamp",
                            passed=True,
                            message="Valid ISO 8601 timestamp"
                        ))
                except ValueError:
                    results.append(TestResult(
                        name="task.status.timestamp",
                        passed=False,
                        message=f"Invalid timestamp format: {timestamp}"
                    ))
        
        # Validate artifacts if present
        if "artifacts" in task:
            artifacts = task["artifacts"]
            if not isinstance(artifacts, list):
                results.append(TestResult(
                    name="task.artifacts",
                    passed=False,
                    message="Artifacts must be an array"
                ))
            else:
                for i, artifact in enumerate(artifacts):
                    if not isinstance(artifact, dict):
                        results.append(TestResult(
                            name=f"task.artifacts[{i}]",
                            passed=False,
                            message="Artifact must be an object"
                        ))
                    elif "parts" not in artifact:
                        results.append(TestResult(
                            name=f"task.artifacts[{i}].parts",
                            passed=False,
                            message="Artifact must have 'parts' field"
                        ))
        
        # Validate history if present
        if "history" in task:
            history = task["history"]
            if not isinstance(history, list):
                results.append(TestResult(
                    name="task.history",
                    passed=False,
                    message="History must be an array"
                ))
            else:
                for i, msg in enumerate(history):
                    if not isinstance(msg, dict):
                        results.append(TestResult(
                            name=f"task.history[{i}]",
                            passed=False,
                            message="History entry must be an object"
                        ))
                    elif "role" not in msg or "parts" not in msg:
                        results.append(TestResult(
                            name=f"task.history[{i}]",
                            passed=False,
                            message="History message must have 'role' and 'parts'"
                        ))
        
        return results
    
    async def send_message(
        self,
        text: str,
        context_id: Optional[str] = None,
        task_id: Optional[str] = None,
        blocking: bool = True
    ) -> dict:
        """
        Send a message to the agent using message/send.
        
        Args:
            text: The message text to send
            context_id: Optional context ID for continuation
            task_id: Optional task ID for continuation
            blocking: Whether to wait for completion
            
        Returns:
            The JSON-RPC response
        """
        message = self._build_message(text, context_id, task_id)
        
        params = {
            "message": message,
            "configuration": {
                "blocking": blocking
            }
        }
        
        request = self._build_jsonrpc_request("message/send", params)
        
        headers = {
            "Content-Type": "application/json",
            "A2A-Version": "0.3"
        }
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.agent_url,
                json=request,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
    
    async def get_task(self, task_id: str) -> dict:
        """
        Get the current state of a task using tasks/get.
        
        Args:
            task_id: The task ID to retrieve
            
        Returns:
            The JSON-RPC response
        """
        request = self._build_jsonrpc_request("tasks/get", {"id": task_id})
        
        headers = {
            "Content-Type": "application/json",
            "A2A-Version": "0.3"
        }
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.agent_url,
                json=request,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
    
    async def cancel_task(self, task_id: str) -> dict:
        """
        Cancel a task using tasks/cancel.
        
        Args:
            task_id: The task ID to cancel
            
        Returns:
            The JSON-RPC response
        """
        request = self._build_jsonrpc_request("tasks/cancel", {"id": task_id})
        
        headers = {
            "Content-Type": "application/json",
            "A2A-Version": "0.3"
        }
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                self.agent_url,
                json=request,
                headers=headers
            )
            response.raise_for_status()
            return response.json()
    
    async def test_basic_task(self, message: str = "Hello, this is a test message.") -> TaskTestReport:
        """
        Run a basic task test against the agent.
        
        Args:
            message: The test message to send
            
        Returns:
            TaskTestReport with test results
        """
        self.tests = []  # Reset tests
        start_time = datetime.now()
        
        report = TaskTestReport(
            success=False,
            agent_url=self.agent_url,
            message_sent=message
        )
        
        try:
            # Test 1: Send message
            send_start = datetime.now()
            response = await self.send_message(message)
            send_duration = (datetime.now() - send_start).total_seconds() * 1000
            
            report.response_received = True
            report.raw_response = response
            
            self._add_test(
                name="send_message",
                passed=True,
                message="Successfully sent message to agent",
                duration_ms=send_duration
            )
            
            # Test 2: Validate JSON-RPC format
            if "jsonrpc" in response and response["jsonrpc"] == "2.0":
                self._add_test(
                    name="jsonrpc_format",
                    passed=True,
                    message="Response is valid JSON-RPC 2.0"
                )
            else:
                self._add_test(
                    name="jsonrpc_format",
                    passed=False,
                    message="Response is not valid JSON-RPC 2.0 format"
                )
            
            # Test 3: Validate response structure
            is_valid, validation_msg = self._validate_task_response(response)
            self._add_test(
                name="response_structure",
                passed=is_valid,
                message=validation_msg
            )
            
            report.response_valid = is_valid
            
            if is_valid and "result" in response:
                result = response["result"]
                
                # Check if it's a Task or Message
                if "id" in result and "status" in result:
                    # It's a Task
                    task = result
                    report.task_id = task.get("id")
                    report.final_state = task.get("status", {}).get("state")
                    report.artifacts = task.get("artifacts", [])
                    
                    # Test 4: Validate task structure
                    task_tests = self._validate_task_object(task)
                    self.tests.extend(task_tests)
                    
                    # Test 5: Check for valid state
                    state = task.get("status", {}).get("state")
                    valid_states = [s.value for s in TaskState]
                    self._add_test(
                        name="task_state_valid",
                        passed=state in valid_states,
                        message=f"Task state '{state}' is {'valid' if state in valid_states else 'invalid'}"
                    )
                    
                    # Test 6: Check if task reached a meaningful state
                    meaningful_states = ["completed", "working", "input-required"]
                    self._add_test(
                        name="task_processed",
                        passed=state in meaningful_states,
                        message=f"Task reached state: {state}"
                    )
                    
                else:
                    # It's a direct Message response
                    self._add_test(
                        name="direct_response",
                        passed=True,
                        message="Agent returned a direct message response"
                    )
            
            # Calculate overall success
            report.success = all(t.passed for t in self.tests)
            
        except httpx.TimeoutException:
            self._add_test(
                name="connection",
                passed=False,
                message="Request timed out"
            )
            report.error = "Request timed out"
            
        except httpx.ConnectError as e:
            self._add_test(
                name="connection",
                passed=False,
                message=f"Failed to connect: {str(e)}"
            )
            report.error = f"Connection failed: {str(e)}"
            
        except httpx.HTTPStatusError as e:
            self._add_test(
                name="http_status",
                passed=False,
                message=f"HTTP error: {e.response.status_code}"
            )
            report.error = f"HTTP {e.response.status_code}"
            
        except json.JSONDecodeError as e:
            self._add_test(
                name="json_parse",
                passed=False,
                message=f"Invalid JSON response: {str(e)}"
            )
            report.error = "Invalid JSON response"
            
        except Exception as e:
            self._add_test(
                name="unexpected_error",
                passed=False,
                message=f"Unexpected error: {str(e)}"
            )
            report.error = str(e)
        
        report.tests = self.tests
        report.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        return report
    
    async def test_task_lifecycle(
        self,
        initial_message: str = "What is 2 + 2?",
        poll_interval: float = 1.0,
        max_polls: int = 30
    ) -> TaskTestReport:
        """
        Test the complete task lifecycle including polling.
        
        Args:
            initial_message: The initial test message
            poll_interval: Seconds between status polls
            max_polls: Maximum number of polls before timeout
            
        Returns:
            TaskTestReport with lifecycle test results
        """
        self.tests = []
        start_time = datetime.now()
        
        report = TaskTestReport(
            success=False,
            agent_url=self.agent_url,
            message_sent=initial_message
        )
        
        try:
            # Step 1: Send initial message (non-blocking)
            response = await self.send_message(initial_message, blocking=False)
            report.response_received = True
            report.raw_response = response
            
            self._add_test(
                name="initial_send",
                passed=True,
                message="Initial message sent successfully"
            )
            
            # Check if we got a task
            if "result" not in response:
                if "error" in response:
                    error = response["error"]
                    self._add_test(
                        name="task_created",
                        passed=False,
                        message=f"Error creating task: {error.get('message', 'Unknown')}"
                    )
                    report.error = error.get("message")
                    report.tests = self.tests
                    return report
            
            result = response["result"]
            
            # Handle direct message response
            if "role" in result and "parts" in result:
                self._add_test(
                    name="response_type",
                    passed=True,
                    message="Agent returned direct message (no task lifecycle)"
                )
                report.response_valid = True
                report.success = True
                report.tests = self.tests
                report.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
                return report
            
            # We have a task
            task_id = result.get("id")
            if not task_id:
                self._add_test(
                    name="task_id",
                    passed=False,
                    message="Task response missing ID"
                )
                report.tests = self.tests
                return report
            
            report.task_id = task_id
            initial_state = result.get("status", {}).get("state")
            
            self._add_test(
                name="task_created",
                passed=True,
                message=f"Task created with ID: {task_id}, initial state: {initial_state}"
            )
            
            # Step 2: Poll for completion
            states_seen = [initial_state]
            current_task = result
            
            for poll in range(max_polls):
                state = current_task.get("status", {}).get("state")
                
                # Check for terminal state
                if state in [s.value for s in TERMINAL_STATES]:
                    break
                
                await asyncio.sleep(poll_interval)
                
                # Get updated task state
                poll_response = await self.get_task(task_id)
                
                if "result" in poll_response:
                    current_task = poll_response["result"]
                    new_state = current_task.get("status", {}).get("state")
                    
                    if new_state != states_seen[-1]:
                        states_seen.append(new_state)
            
            # Record final state
            final_state = current_task.get("status", {}).get("state")
            report.final_state = final_state
            report.artifacts = current_task.get("artifacts", [])
            
            # Test: State transitions
            self._add_test(
                name="state_transitions",
                passed=True,
                message=f"State transitions: {' → '.join(states_seen)}",
                details={"states": states_seen}
            )
            
            # Test: Reached terminal state
            is_terminal = final_state in [s.value for s in TERMINAL_STATES]
            self._add_test(
                name="reached_terminal",
                passed=is_terminal,
                message=f"Task {'reached' if is_terminal else 'did not reach'} terminal state: {final_state}"
            )
            
            # Test: Successful completion
            is_completed = final_state == "completed"
            self._add_test(
                name="task_completed",
                passed=is_completed,
                message=f"Task {'completed successfully' if is_completed else f'ended with state: {final_state}'}"
            )
            
            # Test: Has artifacts (if completed)
            if is_completed:
                has_artifacts = len(report.artifacts) > 0
                self._add_test(
                    name="has_artifacts",
                    passed=has_artifacts,
                    message=f"Task has {len(report.artifacts)} artifact(s)" if has_artifacts else "Task has no artifacts (may be expected)"
                )
            
            report.response_valid = True
            report.success = all(t.passed for t in self.tests if t.name not in ["has_artifacts"])
            
        except Exception as e:
            self._add_test(
                name="lifecycle_error",
                passed=False,
                message=f"Error during lifecycle test: {str(e)}"
            )
            report.error = str(e)
        
        report.tests = self.tests
        report.duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        return report


async def run_task_test(
    agent_url: str,
    message: str = "Hello, this is a test message.",
    auth_header: Optional[str] = None,
    full_lifecycle: bool = False
) -> TaskTestReport:
    """
    Convenience function to run a task test.
    
    Args:
        agent_url: The A2A agent URL
        message: The test message to send
        auth_header: Optional Authorization header
        full_lifecycle: Whether to run full lifecycle test
        
    Returns:
        TaskTestReport with results
    """
    tester = TaskTester(agent_url, auth_header)
    
    if full_lifecycle:
        return await tester.test_task_lifecycle(message)
    else:
        return await tester.test_basic_task(message)
