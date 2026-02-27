"""
A2Apex Protocol Compliance Checker

Run comprehensive A2A protocol compliance tests against agents.
"""

import asyncio
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import httpx

from .agent_card_validator import AgentCardValidator, fetch_and_validate_agent_card, ValidationSeverity
from .task_tester import TaskTester, TaskState


class CheckCategory(Enum):
    """Categories of compliance checks."""
    DISCOVERY = "discovery"       # Agent Card accessibility and format
    MESSAGING = "messaging"       # Message sending and receiving
    TASK_LIFECYCLE = "lifecycle"  # Task state management
    ERROR_HANDLING = "errors"     # Error response format
    SECURITY = "security"         # Authentication and headers
    STREAMING = "streaming"       # SSE streaming support
    PUSH = "push"                 # Push notification support


class CheckStatus(Enum):
    """Status of a compliance check."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class ComplianceCheck:
    """Result of a single compliance check."""
    id: str
    name: str
    category: CheckCategory
    status: CheckStatus
    message: str
    details: Optional[dict] = None
    required: bool = True  # Is this a required check?
    spec_section: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "status": self.status.value,
            "message": self.message,
            "details": self.details,
            "required": self.required,
            "spec_section": self.spec_section
        }


@dataclass
class ComplianceReport:
    """Complete compliance report for an agent."""
    agent_url: str
    is_compliant: bool
    compliance_score: float  # 0-100
    checks: list[ComplianceCheck] = field(default_factory=list)
    agent_card: Optional[dict] = None
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    duration_ms: float = 0
    
    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.PASSED)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.FAILED)
    
    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.WARNING)
    
    @property
    def skipped_count(self) -> int:
        return sum(1 for c in self.checks if c.status == CheckStatus.SKIPPED)
    
    def checks_by_category(self) -> dict[str, list[ComplianceCheck]]:
        """Group checks by category."""
        result = {}
        for check in self.checks:
            cat = check.category.value
            if cat not in result:
                result[cat] = []
            result[cat].append(check)
        return result
    
    def to_dict(self) -> dict:
        return {
            "agent_url": self.agent_url,
            "is_compliant": self.is_compliant,
            "compliance_score": round(self.compliance_score, 1),
            "summary": {
                "total_checks": len(self.checks),
                "passed": self.passed_count,
                "failed": self.failed_count,
                "warnings": self.warning_count,
                "skipped": self.skipped_count
            },
            "checks_by_category": {
                cat: [c.to_dict() for c in checks]
                for cat, checks in self.checks_by_category().items()
            },
            "agent_card": self.agent_card,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms
        }


class ProtocolChecker:
    """
    Comprehensive A2A protocol compliance checker.
    
    Runs a suite of tests to verify an agent's compliance with the A2A specification.
    """
    
    def __init__(
        self,
        agent_url: str,
        auth_header: Optional[str] = None,
        timeout: float = 30.0,
        skip_optional: bool = False
    ):
        """
        Initialize the protocol checker.
        
        Args:
            agent_url: Base URL of the agent (without /.well-known/agent-card.json)
            auth_header: Optional Authorization header for authenticated requests
            timeout: Request timeout in seconds
            skip_optional: Whether to skip optional checks
        """
        self.agent_url = agent_url.rstrip("/")
        self.auth_header = auth_header
        self.timeout = timeout
        self.skip_optional = skip_optional
        self.checks: list[ComplianceCheck] = []
        self.agent_card: Optional[dict] = None
    
    def _add_check(
        self,
        id: str,
        name: str,
        category: CheckCategory,
        status: CheckStatus,
        message: str,
        details: Optional[dict] = None,
        required: bool = True,
        spec_section: Optional[str] = None
    ):
        self.checks.append(ComplianceCheck(
            id=id,
            name=name,
            category=category,
            status=status,
            message=message,
            details=details,
            required=required,
            spec_section=spec_section
        ))
    
    async def _check_agent_card_accessibility(self) -> bool:
        """Check if Agent Card is accessible at the well-known URL."""
        card_url = f"{self.agent_url}/.well-known/agent-card.json"
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(card_url)
                
                # Check HTTP status
                if response.status_code == 200:
                    self._add_check(
                        id="discovery.accessibility",
                        name="Agent Card Accessible",
                        category=CheckCategory.DISCOVERY,
                        status=CheckStatus.PASSED,
                        message=f"Agent Card accessible at {card_url}",
                        spec_section="Section 5.3"
                    )
                    
                    # Check Content-Type
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        self._add_check(
                            id="discovery.content_type",
                            name="Correct Content-Type",
                            category=CheckCategory.DISCOVERY,
                            status=CheckStatus.PASSED,
                            message="Content-Type is application/json",
                            spec_section="Section 3.2.1"
                        )
                    else:
                        self._add_check(
                            id="discovery.content_type",
                            name="Correct Content-Type",
                            category=CheckCategory.DISCOVERY,
                            status=CheckStatus.WARNING,
                            message=f"Content-Type should be application/json, got: {content_type}",
                            spec_section="Section 3.2.1"
                        )
                    
                    # Try to parse JSON
                    try:
                        self.agent_card = response.json()
                        self._add_check(
                            id="discovery.valid_json",
                            name="Valid JSON",
                            category=CheckCategory.DISCOVERY,
                            status=CheckStatus.PASSED,
                            message="Agent Card is valid JSON"
                        )
                        return True
                    except Exception as e:
                        self._add_check(
                            id="discovery.valid_json",
                            name="Valid JSON",
                            category=CheckCategory.DISCOVERY,
                            status=CheckStatus.FAILED,
                            message=f"Agent Card is not valid JSON: {str(e)}"
                        )
                        return False
                else:
                    self._add_check(
                        id="discovery.accessibility",
                        name="Agent Card Accessible",
                        category=CheckCategory.DISCOVERY,
                        status=CheckStatus.FAILED,
                        message=f"Agent Card not accessible: HTTP {response.status_code}",
                        spec_section="Section 5.3"
                    )
                    return False
                    
        except httpx.ConnectError as e:
            self._add_check(
                id="discovery.accessibility",
                name="Agent Card Accessible",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.FAILED,
                message=f"Cannot connect to agent: {str(e)}"
            )
            return False
        except httpx.TimeoutException:
            self._add_check(
                id="discovery.accessibility",
                name="Agent Card Accessible",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.FAILED,
                message="Request timed out"
            )
            return False
    
    async def _check_agent_card_structure(self) -> bool:
        """Validate Agent Card structure against the schema."""
        if not self.agent_card:
            return False
        
        validator = AgentCardValidator()
        report = validator.validate(self.agent_card)
        
        if report.is_valid:
            self._add_check(
                id="discovery.schema_valid",
                name="Agent Card Schema Valid",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.PASSED,
                message="Agent Card conforms to A2A schema",
                details={"warnings": len(report.warnings)},
                spec_section="Section 5.5"
            )
        else:
            self._add_check(
                id="discovery.schema_valid",
                name="Agent Card Schema Valid",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.FAILED,
                message=f"Agent Card has {len(report.errors)} schema errors",
                details={"errors": [e.message for e in report.errors[:5]]},
                spec_section="Section 5.5"
            )
            return False
        
        # Check for required fields specifically
        required_fields = ["name", "description", "url", "version", "capabilities", "skills"]
        missing = [f for f in required_fields if f not in self.agent_card]
        
        if not missing:
            self._add_check(
                id="discovery.required_fields",
                name="Required Fields Present",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.PASSED,
                message="All required fields are present"
            )
        else:
            self._add_check(
                id="discovery.required_fields",
                name="Required Fields Present",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.FAILED,
                message=f"Missing required fields: {', '.join(missing)}"
            )
        
        # Check protocol version
        if "protocolVersion" in self.agent_card:
            version = self.agent_card["protocolVersion"]
            self._add_check(
                id="discovery.protocol_version",
                name="Protocol Version Declared",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.PASSED,
                message=f"Protocol version: {version}",
                spec_section="Section 5.5"
            )
        else:
            self._add_check(
                id="discovery.protocol_version",
                name="Protocol Version Declared",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.WARNING,
                message="protocolVersion not specified (recommended)",
                spec_section="Section 5.5"
            )
        
        # Check skills
        skills = self.agent_card.get("skills", [])
        if len(skills) > 0:
            self._add_check(
                id="discovery.has_skills",
                name="Skills Defined",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.PASSED,
                message=f"Agent declares {len(skills)} skill(s)",
                details={"skills": [s.get("name", s.get("id")) for s in skills[:5]]}
            )
        else:
            self._add_check(
                id="discovery.has_skills",
                name="Skills Defined",
                category=CheckCategory.DISCOVERY,
                status=CheckStatus.WARNING,
                message="No skills defined (agents should have at least one skill)"
            )
        
        return True
    
    async def _check_message_send(self) -> bool:
        """Test basic message sending capability."""
        if not self.agent_card:
            self._add_check(
                id="messaging.send",
                name="Message Send",
                category=CheckCategory.MESSAGING,
                status=CheckStatus.SKIPPED,
                message="Skipped: Agent Card not available"
            )
            return False
        
        # Get the endpoint URL from agent card
        endpoint_url = self.agent_card.get("url", self.agent_url)
        
        tester = TaskTester(endpoint_url, self.auth_header, self.timeout)
        
        try:
            report = await tester.test_basic_task("Hello, this is an A2A protocol compliance test.")
            
            if report.response_received:
                self._add_check(
                    id="messaging.send",
                    name="Message Send",
                    category=CheckCategory.MESSAGING,
                    status=CheckStatus.PASSED,
                    message="Agent responds to message/send",
                    details={"duration_ms": report.duration_ms},
                    spec_section="Section 3.1.1"
                )
            else:
                self._add_check(
                    id="messaging.send",
                    name="Message Send",
                    category=CheckCategory.MESSAGING,
                    status=CheckStatus.FAILED,
                    message=f"No response received: {report.error}",
                    spec_section="Section 3.1.1"
                )
                return False
            
            # Check JSON-RPC format
            if report.raw_response and report.raw_response.get("jsonrpc") == "2.0":
                self._add_check(
                    id="messaging.jsonrpc_format",
                    name="JSON-RPC 2.0 Format",
                    category=CheckCategory.MESSAGING,
                    status=CheckStatus.PASSED,
                    message="Response uses JSON-RPC 2.0 format",
                    spec_section="Section 3.2.1"
                )
            else:
                self._add_check(
                    id="messaging.jsonrpc_format",
                    name="JSON-RPC 2.0 Format",
                    category=CheckCategory.MESSAGING,
                    status=CheckStatus.FAILED,
                    message="Response not in JSON-RPC 2.0 format",
                    spec_section="Section 3.2.1"
                )
            
            # Check response validity
            if report.response_valid:
                self._add_check(
                    id="messaging.response_valid",
                    name="Valid Response Structure",
                    category=CheckCategory.MESSAGING,
                    status=CheckStatus.PASSED,
                    message="Response contains valid Task or Message object"
                )
            else:
                self._add_check(
                    id="messaging.response_valid",
                    name="Valid Response Structure",
                    category=CheckCategory.MESSAGING,
                    status=CheckStatus.FAILED,
                    message="Response does not contain valid Task or Message"
                )
            
            return report.response_valid
            
        except Exception as e:
            self._add_check(
                id="messaging.send",
                name="Message Send",
                category=CheckCategory.MESSAGING,
                status=CheckStatus.FAILED,
                message=f"Error sending message: {str(e)}"
            )
            return False
    
    async def _check_task_lifecycle(self) -> bool:
        """Test task lifecycle handling."""
        if not self.agent_card:
            self._add_check(
                id="lifecycle.test",
                name="Task Lifecycle",
                category=CheckCategory.TASK_LIFECYCLE,
                status=CheckStatus.SKIPPED,
                message="Skipped: Agent Card not available"
            )
            return False
        
        endpoint_url = self.agent_card.get("url", self.agent_url)
        tester = TaskTester(endpoint_url, self.auth_header, self.timeout)
        
        try:
            report = await tester.test_task_lifecycle(
                "What is 2 + 2? Please respond with the answer.",
                poll_interval=0.5,
                max_polls=20
            )
            
            if report.task_id:
                self._add_check(
                    id="lifecycle.task_created",
                    name="Task Creation",
                    category=CheckCategory.TASK_LIFECYCLE,
                    status=CheckStatus.PASSED,
                    message=f"Task created with ID: {report.task_id}",
                    spec_section="Section 3.1.1"
                )
            else:
                # Agent might return direct message
                self._add_check(
                    id="lifecycle.task_created",
                    name="Task Creation",
                    category=CheckCategory.TASK_LIFECYCLE,
                    status=CheckStatus.PASSED,
                    message="Agent returned direct message (stateless interaction)",
                    required=False
                )
                return True
            
            # Check final state
            if report.final_state:
                valid_states = [s.value for s in TaskState]
                if report.final_state in valid_states:
                    self._add_check(
                        id="lifecycle.valid_state",
                        name="Valid Task State",
                        category=CheckCategory.TASK_LIFECYCLE,
                        status=CheckStatus.PASSED,
                        message=f"Task ended in valid state: {report.final_state}",
                        spec_section="Section 6.3"
                    )
                else:
                    self._add_check(
                        id="lifecycle.valid_state",
                        name="Valid Task State",
                        category=CheckCategory.TASK_LIFECYCLE,
                        status=CheckStatus.FAILED,
                        message=f"Invalid task state: {report.final_state}",
                        spec_section="Section 6.3"
                    )
                
                # Check if reached terminal state
                terminal_states = ["completed", "failed", "canceled", "rejected"]
                if report.final_state in terminal_states:
                    self._add_check(
                        id="lifecycle.terminal_state",
                        name="Reaches Terminal State",
                        category=CheckCategory.TASK_LIFECYCLE,
                        status=CheckStatus.PASSED,
                        message=f"Task reached terminal state: {report.final_state}"
                    )
                else:
                    self._add_check(
                        id="lifecycle.terminal_state",
                        name="Reaches Terminal State",
                        category=CheckCategory.TASK_LIFECYCLE,
                        status=CheckStatus.WARNING,
                        message=f"Task did not reach terminal state within timeout: {report.final_state}"
                    )
            
            return True
            
        except Exception as e:
            self._add_check(
                id="lifecycle.test",
                name="Task Lifecycle",
                category=CheckCategory.TASK_LIFECYCLE,
                status=CheckStatus.FAILED,
                message=f"Error testing lifecycle: {str(e)}"
            )
            return False
    
    async def _check_error_handling(self) -> bool:
        """Test error response format."""
        if not self.agent_card:
            self._add_check(
                id="errors.test",
                name="Error Handling",
                category=CheckCategory.ERROR_HANDLING,
                status=CheckStatus.SKIPPED,
                message="Skipped: Agent Card not available"
            )
            return False
        
        endpoint_url = self.agent_card.get("url", self.agent_url)
        
        try:
            # Send a request for a non-existent task
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                headers = {
                    "Content-Type": "application/json",
                    "A2A-Version": "0.3"
                }
                if self.auth_header:
                    headers["Authorization"] = self.auth_header
                
                request = {
                    "jsonrpc": "2.0",
                    "method": "tasks/get",
                    "params": {"id": "non-existent-task-id-12345"},
                    "id": "error-test-1"
                }
                
                response = await client.post(endpoint_url, json=request, headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if "error" in data:
                        error = data["error"]
                        
                        # Check error structure
                        has_code = "code" in error
                        has_message = "message" in error
                        
                        if has_code and has_message:
                            self._add_check(
                                id="errors.structure",
                                name="Error Response Structure",
                                category=CheckCategory.ERROR_HANDLING,
                                status=CheckStatus.PASSED,
                                message="Error response has required fields (code, message)",
                                details={"error_code": error.get("code")},
                                spec_section="Section 3.3.2"
                            )
                        else:
                            missing = []
                            if not has_code:
                                missing.append("code")
                            if not has_message:
                                missing.append("message")
                            self._add_check(
                                id="errors.structure",
                                name="Error Response Structure",
                                category=CheckCategory.ERROR_HANDLING,
                                status=CheckStatus.WARNING,
                                message=f"Error response missing: {', '.join(missing)}",
                                spec_section="Section 3.3.2"
                            )
                        
                        # Check for TaskNotFoundError
                        error_message = error.get("message", "").lower()
                        if "not found" in error_message or error.get("code") == -32001:
                            self._add_check(
                                id="errors.task_not_found",
                                name="TaskNotFoundError Handling",
                                category=CheckCategory.ERROR_HANDLING,
                                status=CheckStatus.PASSED,
                                message="Agent properly returns TaskNotFoundError",
                                spec_section="Section 3.3.2"
                            )
                        
                        return True
                    else:
                        # No error returned - might have actually found/created something
                        self._add_check(
                            id="errors.structure",
                            name="Error Response Structure",
                            category=CheckCategory.ERROR_HANDLING,
                            status=CheckStatus.WARNING,
                            message="No error returned for non-existent task (may be implementation-specific)"
                        )
                        return True
                else:
                    # HTTP-level error
                    self._add_check(
                        id="errors.http_error",
                        name="HTTP Error Handling",
                        category=CheckCategory.ERROR_HANDLING,
                        status=CheckStatus.PASSED,
                        message=f"Agent returns HTTP {response.status_code} for errors"
                    )
                    return True
                    
        except Exception as e:
            self._add_check(
                id="errors.test",
                name="Error Handling",
                category=CheckCategory.ERROR_HANDLING,
                status=CheckStatus.WARNING,
                message=f"Could not test error handling: {str(e)}"
            )
            return False
    
    async def _check_streaming_support(self) -> bool:
        """Check if streaming is properly declared and basic functionality."""
        if not self.agent_card:
            self._add_check(
                id="streaming.check",
                name="Streaming Support",
                category=CheckCategory.STREAMING,
                status=CheckStatus.SKIPPED,
                message="Skipped: Agent Card not available"
            )
            return False
        
        capabilities = self.agent_card.get("capabilities", {})
        supports_streaming = capabilities.get("streaming", False)
        
        if supports_streaming:
            self._add_check(
                id="streaming.declared",
                name="Streaming Declared",
                category=CheckCategory.STREAMING,
                status=CheckStatus.PASSED,
                message="Agent declares streaming support",
                required=False,
                spec_section="Section 5.5.2"
            )
            # TODO: Actually test streaming endpoint
        else:
            self._add_check(
                id="streaming.declared",
                name="Streaming Declared",
                category=CheckCategory.STREAMING,
                status=CheckStatus.SKIPPED,
                message="Agent does not declare streaming support",
                required=False
            )
        
        return True
    
    async def _check_push_notification_support(self) -> bool:
        """Check if push notifications are properly declared."""
        if not self.agent_card:
            self._add_check(
                id="push.check",
                name="Push Notification Support",
                category=CheckCategory.PUSH,
                status=CheckStatus.SKIPPED,
                message="Skipped: Agent Card not available"
            )
            return False
        
        capabilities = self.agent_card.get("capabilities", {})
        supports_push = capabilities.get("pushNotifications", False)
        
        if supports_push:
            self._add_check(
                id="push.declared",
                name="Push Notifications Declared",
                category=CheckCategory.PUSH,
                status=CheckStatus.PASSED,
                message="Agent declares push notification support",
                required=False,
                spec_section="Section 5.5.2"
            )
        else:
            self._add_check(
                id="push.declared",
                name="Push Notifications Declared",
                category=CheckCategory.PUSH,
                status=CheckStatus.SKIPPED,
                message="Agent does not declare push notification support",
                required=False
            )
        
        return True
    
    async def _check_security(self) -> bool:
        """Check security-related declarations."""
        if not self.agent_card:
            self._add_check(
                id="security.check",
                name="Security Check",
                category=CheckCategory.SECURITY,
                status=CheckStatus.SKIPPED,
                message="Skipped: Agent Card not available"
            )
            return False
        
        # Check URL uses HTTPS
        url = self.agent_card.get("url", "")
        if url.startswith("https://"):
            self._add_check(
                id="security.https",
                name="HTTPS Endpoint",
                category=CheckCategory.SECURITY,
                status=CheckStatus.PASSED,
                message="Agent endpoint uses HTTPS",
                spec_section="Section 4.1"
            )
        elif "localhost" in url or "127.0.0.1" in url:
            self._add_check(
                id="security.https",
                name="HTTPS Endpoint",
                category=CheckCategory.SECURITY,
                status=CheckStatus.WARNING,
                message="Agent uses HTTP (acceptable for localhost development)",
                spec_section="Section 4.1"
            )
        else:
            self._add_check(
                id="security.https",
                name="HTTPS Endpoint",
                category=CheckCategory.SECURITY,
                status=CheckStatus.FAILED,
                message="Agent endpoint should use HTTPS in production",
                spec_section="Section 4.1"
            )
        
        # Check if security schemes are declared
        security_schemes = self.agent_card.get("securitySchemes", {})
        security_requirements = self.agent_card.get("security", [])
        
        if security_schemes:
            self._add_check(
                id="security.schemes_declared",
                name="Security Schemes Declared",
                category=CheckCategory.SECURITY,
                status=CheckStatus.PASSED,
                message=f"Agent declares {len(security_schemes)} security scheme(s)",
                details={"schemes": list(security_schemes.keys())},
                required=False,
                spec_section="Section 5.5.3"
            )
        else:
            self._add_check(
                id="security.schemes_declared",
                name="Security Schemes Declared",
                category=CheckCategory.SECURITY,
                status=CheckStatus.WARNING,
                message="No security schemes declared (agent may be publicly accessible)",
                required=False,
                spec_section="Section 5.5.3"
            )
        
        return True
    
    async def run_all_checks(self) -> ComplianceReport:
        """
        Run all compliance checks against the agent.
        
        Returns:
            ComplianceReport with all check results
        """
        start_time = datetime.now()
        self.checks = []  # Reset checks
        
        # Run checks in order
        card_accessible = await self._check_agent_card_accessibility()
        
        if card_accessible:
            await self._check_agent_card_structure()
            await self._check_security()
            await self._check_message_send()
            await self._check_task_lifecycle()
            await self._check_error_handling()
            await self._check_streaming_support()
            await self._check_push_notification_support()
        
        # Calculate compliance score
        required_checks = [c for c in self.checks if c.required]
        passed_required = sum(1 for c in required_checks if c.status == CheckStatus.PASSED)
        total_required = len(required_checks) if required_checks else 1
        
        compliance_score = (passed_required / total_required) * 100 if total_required > 0 else 0
        
        # Determine overall compliance (all required checks must pass)
        failed_required = any(c for c in self.checks if c.required and c.status == CheckStatus.FAILED)
        is_compliant = not failed_required and card_accessible
        
        duration_ms = (datetime.now() - start_time).total_seconds() * 1000
        
        return ComplianceReport(
            agent_url=self.agent_url,
            is_compliant=is_compliant,
            compliance_score=compliance_score,
            checks=self.checks,
            agent_card=self.agent_card,
            duration_ms=duration_ms
        )


async def run_compliance_check(
    agent_url: str,
    auth_header: Optional[str] = None,
    timeout: float = 30.0
) -> ComplianceReport:
    """
    Convenience function to run a full compliance check.
    
    Args:
        agent_url: The A2A agent base URL
        auth_header: Optional Authorization header
        timeout: Request timeout in seconds
        
    Returns:
        ComplianceReport with all results
    """
    checker = ProtocolChecker(agent_url, auth_header, timeout)
    return await checker.run_all_checks()
