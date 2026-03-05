"""
A2Apex Authentication Tester

Tests authentication schemes declared in Agent Cards.
Validates that security mechanisms work as specified.
"""

import uuid
import time
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import httpx


class AuthTestStatus(Enum):
    """Status of an auth test."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNING = "warning"


@dataclass
class AuthTestResult:
    """Result of a single auth test."""
    test_name: str
    status: AuthTestStatus
    message: str
    duration_ms: float = 0
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
class AuthTestReport:
    """Complete report of auth testing."""
    agent_url: str
    total_tests: int = 0
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0
    results: list[AuthTestResult] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
    
    def add_result(self, result: AuthTestResult):
        self.results.append(result)
        self.total_tests += 1
        
        if result.status == AuthTestStatus.PASSED:
            self.passed += 1
        elif result.status == AuthTestStatus.FAILED:
            self.failed += 1
        elif result.status == AuthTestStatus.WARNING:
            self.warnings += 1
        elif result.status == AuthTestStatus.SKIPPED:
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


class AuthTester:
    """
    Authentication tester for A2A agents.
    
    Tests various authentication schemes declared in Agent Cards:
    - API Key authentication
    - HTTP Bearer token authentication
    - OAuth2 flow declarations
    - Security scheme compliance
    """
    
    def __init__(
        self,
        base_url: str,
        agent_card: Optional[dict] = None,
        timeout: float = 5.0
    ):
        """
        Initialize the auth tester.
        
        Args:
            base_url: Base URL of the A2A agent
            agent_card: Agent Card JSON (if already fetched)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.agent_card = agent_card
        self.timeout = timeout
    
    def _get_headers(self, extra: Optional[dict] = None) -> dict:
        """Build base request headers without auth."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "A2A-Version": "0.3"
        }
        if extra:
            headers.update(extra)
        return headers
    
    def _build_simple_request(self) -> dict:
        """Build a minimal valid JSON-RPC request for testing."""
        return {
            "jsonrpc": "2.0",
            "method": "message/send",
            "params": {
                "message": {
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Auth test ping"}],
                    "messageId": str(uuid.uuid4())
                }
            },
            "id": str(uuid.uuid4())
        }
    
    async def _fetch_agent_card(self) -> Optional[dict]:
        """Fetch agent card if not already available."""
        if self.agent_card:
            return self.agent_card
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/.well-known/agent-card.json")
                if response.status_code == 200:
                    self.agent_card = response.json()
                    return self.agent_card
        except Exception:
            pass
        return None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # AUTH TESTS
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def test_security_schemes_declared(self) -> AuthTestResult:
        """
        Test: Check if security schemes are properly declared in Agent Card.
        """
        test_name = "security_schemes_declared"
        start = time.perf_counter()
        
        card = await self._fetch_agent_card()
        duration_ms = (time.perf_counter() - start) * 1000
        
        if not card:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="Cannot fetch Agent Card",
                duration_ms=duration_ms,
                suggestion="Ensure Agent Card is accessible at /.well-known/agent-card.json"
            )
        
        security_schemes = card.get("securitySchemes", {})
        security_requirements = card.get("security", [])
        
        if not security_schemes:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.WARNING,
                message="No security schemes declared - agent may be publicly accessible",
                duration_ms=duration_ms,
                details={"has_schemes": False, "has_requirements": len(security_requirements) > 0},
                suggestion="Consider adding securitySchemes to protect your agent"
            )
        
        # Validate each security scheme structure
        valid_schemes = []
        invalid_schemes = []
        
        for name, scheme in security_schemes.items():
            scheme_type = scheme.get("type")
            if scheme_type in ["apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"]:
                valid_schemes.append(name)
            else:
                invalid_schemes.append({"name": name, "type": scheme_type})
        
        if invalid_schemes:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.WARNING,
                message=f"Some security schemes have invalid types",
                duration_ms=duration_ms,
                details={
                    "valid_schemes": valid_schemes,
                    "invalid_schemes": invalid_schemes
                },
                suggestion="Valid types: apiKey, http, oauth2, openIdConnect, mutualTLS"
            )
        
        return AuthTestResult(
            test_name=test_name,
            status=AuthTestStatus.PASSED,
            message=f"Security schemes properly declared ({len(valid_schemes)} scheme(s))",
            duration_ms=duration_ms,
            details={
                "schemes": list(security_schemes.keys()),
                "security_requirements": security_requirements
            }
        )
    
    async def test_unauthenticated_request(self) -> AuthTestResult:
        """
        Test: Send an unauthenticated request to see if it's properly rejected.
        
        If the agent declares security requirements, unauthenticated requests
        should return a 401 or JSON-RPC error.
        """
        test_name = "unauthenticated_request"
        start = time.perf_counter()
        
        card = await self._fetch_agent_card()
        
        if not card:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="Cannot fetch Agent Card",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        # Check if agent requires authentication
        security_requirements = card.get("security", [])
        security_schemes = card.get("securitySchemes", {})
        
        requires_auth = len(security_requirements) > 0 or len(security_schemes) > 0
        
        endpoint_url = card.get("url", f"{self.base_url}/a2a")
        request = self._build_simple_request()
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=self._get_headers()
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                # Check response
                if response.status_code == 401:
                    if requires_auth:
                        return AuthTestResult(
                            test_name=test_name,
                            status=AuthTestStatus.PASSED,
                            message="Correctly returns 401 for unauthenticated request",
                            duration_ms=duration_ms,
                            details={"http_status": 401}
                        )
                    else:
                        return AuthTestResult(
                            test_name=test_name,
                            status=AuthTestStatus.WARNING,
                            message="Returns 401 but no security requirements declared",
                            duration_ms=duration_ms,
                            suggestion="Add security requirements to Agent Card if auth is required"
                        )
                
                if response.status_code == 403:
                    return AuthTestResult(
                        test_name=test_name,
                        status=AuthTestStatus.PASSED,
                        message="Returns 403 Forbidden for unauthenticated request",
                        duration_ms=duration_ms,
                        details={"http_status": 403}
                    )
                
                if response.status_code == 200:
                    try:
                        json_response = response.json()
                        
                        # Check for JSON-RPC error
                        if "error" in json_response:
                            error_code = json_response["error"].get("code")
                            # Auth-related error codes
                            if error_code in [-32000, -32003, -32010]:  # Custom auth error codes
                                return AuthTestResult(
                                    test_name=test_name,
                                    status=AuthTestStatus.PASSED,
                                    message=f"Returns JSON-RPC auth error (code: {error_code})",
                                    duration_ms=duration_ms,
                                    details={"error": json_response["error"]}
                                )
                        
                        # Request succeeded without auth
                        if requires_auth:
                            return AuthTestResult(
                                test_name=test_name,
                                status=AuthTestStatus.FAILED,
                                message="Request succeeded without auth despite security requirements",
                                duration_ms=duration_ms,
                                suggestion="Enforce authentication on protected endpoints"
                            )
                        else:
                            return AuthTestResult(
                                test_name=test_name,
                                status=AuthTestStatus.PASSED,
                                message="Agent accepts unauthenticated requests (no auth required)",
                                duration_ms=duration_ms,
                                details={"requires_auth": False}
                            )
                    except Exception:
                        pass
                
                # Other status codes
                return AuthTestResult(
                    test_name=test_name,
                    status=AuthTestStatus.WARNING,
                    message=f"Unexpected HTTP status: {response.status_code}",
                    duration_ms=duration_ms,
                    details={"http_status": response.status_code}
                )
                
        except Exception as e:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    async def test_apikey_scheme_structure(self) -> AuthTestResult:
        """
        Test: Validate API key scheme has required fields.
        """
        test_name = "apikey_scheme_structure"
        start = time.perf_counter()
        
        card = await self._fetch_agent_card()
        duration_ms = (time.perf_counter() - start) * 1000
        
        if not card:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="Cannot fetch Agent Card",
                duration_ms=duration_ms
            )
        
        security_schemes = card.get("securitySchemes", {})
        apikey_schemes = {
            name: scheme for name, scheme in security_schemes.items()
            if scheme.get("type") == "apiKey"
        }
        
        if not apikey_schemes:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="No API key schemes declared",
                duration_ms=duration_ms
            )
        
        issues = []
        valid_schemes = []
        
        for name, scheme in apikey_schemes.items():
            # API key requires 'name' and 'in' fields
            if "name" not in scheme:
                issues.append(f"{name}: missing 'name' field (header/query/cookie name)")
            if "in" not in scheme:
                issues.append(f"{name}: missing 'in' field (header/query/cookie)")
            elif scheme["in"] not in ["header", "query", "cookie"]:
                issues.append(f"{name}: invalid 'in' value: {scheme['in']}")
            
            if "name" in scheme and "in" in scheme and scheme["in"] in ["header", "query", "cookie"]:
                valid_schemes.append({
                    "name": name,
                    "key_name": scheme["name"],
                    "location": scheme["in"]
                })
        
        if issues:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.FAILED,
                message=f"API key scheme validation failed ({len(issues)} issue(s))",
                duration_ms=duration_ms,
                details={"issues": issues},
                suggestion="API key schemes require 'name' and 'in' (header/query/cookie)"
            )
        
        return AuthTestResult(
            test_name=test_name,
            status=AuthTestStatus.PASSED,
            message=f"API key schemes properly structured ({len(valid_schemes)})",
            duration_ms=duration_ms,
            details={"schemes": valid_schemes}
        )
    
    async def test_http_scheme_structure(self) -> AuthTestResult:
        """
        Test: Validate HTTP auth scheme has required fields.
        """
        test_name = "http_scheme_structure"
        start = time.perf_counter()
        
        card = await self._fetch_agent_card()
        duration_ms = (time.perf_counter() - start) * 1000
        
        if not card:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="Cannot fetch Agent Card",
                duration_ms=duration_ms
            )
        
        security_schemes = card.get("securitySchemes", {})
        http_schemes = {
            name: scheme for name, scheme in security_schemes.items()
            if scheme.get("type") == "http"
        }
        
        if not http_schemes:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="No HTTP auth schemes declared",
                duration_ms=duration_ms
            )
        
        issues = []
        valid_schemes = []
        
        for name, scheme in http_schemes.items():
            # HTTP auth requires 'scheme' field (e.g., "Bearer", "Basic")
            if "scheme" not in scheme:
                issues.append(f"{name}: missing 'scheme' field")
            else:
                scheme_type = scheme["scheme"].lower()
                valid_schemes.append({
                    "name": name,
                    "scheme": scheme["scheme"],
                    "bearerFormat": scheme.get("bearerFormat")
                })
        
        if issues:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.FAILED,
                message=f"HTTP scheme validation failed ({len(issues)} issue(s))",
                duration_ms=duration_ms,
                details={"issues": issues},
                suggestion="HTTP auth schemes require 'scheme' field (e.g., 'Bearer', 'Basic')"
            )
        
        return AuthTestResult(
            test_name=test_name,
            status=AuthTestStatus.PASSED,
            message=f"HTTP auth schemes properly structured ({len(valid_schemes)})",
            duration_ms=duration_ms,
            details={"schemes": valid_schemes}
        )
    
    async def test_oauth2_scheme_structure(self) -> AuthTestResult:
        """
        Test: Validate OAuth2 scheme has required fields.
        """
        test_name = "oauth2_scheme_structure"
        start = time.perf_counter()
        
        card = await self._fetch_agent_card()
        duration_ms = (time.perf_counter() - start) * 1000
        
        if not card:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="Cannot fetch Agent Card",
                duration_ms=duration_ms
            )
        
        security_schemes = card.get("securitySchemes", {})
        oauth2_schemes = {
            name: scheme for name, scheme in security_schemes.items()
            if scheme.get("type") == "oauth2"
        }
        
        if not oauth2_schemes:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="No OAuth2 schemes declared",
                duration_ms=duration_ms
            )
        
        issues = []
        valid_schemes = []
        
        valid_flows = ["authorizationCode", "implicit", "password", "clientCredentials"]
        
        for name, scheme in oauth2_schemes.items():
            # OAuth2 requires 'flows' object
            if "flows" not in scheme:
                issues.append(f"{name}: missing 'flows' field")
                continue
            
            flows = scheme["flows"]
            if not isinstance(flows, dict):
                issues.append(f"{name}: 'flows' must be an object")
                continue
            
            scheme_info = {"name": name, "flows": []}
            
            for flow_name, flow_config in flows.items():
                if flow_name not in valid_flows:
                    issues.append(f"{name}: unknown flow type '{flow_name}'")
                    continue
                
                flow_info = {"type": flow_name, "valid": True}
                
                # Check required URLs per flow type
                if flow_name in ["authorizationCode", "implicit"]:
                    if "authorizationUrl" not in flow_config:
                        issues.append(f"{name}.{flow_name}: missing 'authorizationUrl'")
                        flow_info["valid"] = False
                
                if flow_name in ["authorizationCode", "password", "clientCredentials"]:
                    if "tokenUrl" not in flow_config:
                        issues.append(f"{name}.{flow_name}: missing 'tokenUrl'")
                        flow_info["valid"] = False
                
                scheme_info["flows"].append(flow_info)
            
            if scheme_info["flows"]:
                valid_schemes.append(scheme_info)
        
        if issues:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.FAILED,
                message=f"OAuth2 scheme validation failed ({len(issues)} issue(s))",
                duration_ms=duration_ms,
                details={"issues": issues},
                suggestion="OAuth2 requires 'flows' with appropriate URLs (authorizationUrl, tokenUrl)"
            )
        
        return AuthTestResult(
            test_name=test_name,
            status=AuthTestStatus.PASSED,
            message=f"OAuth2 schemes properly structured ({len(valid_schemes)})",
            duration_ms=duration_ms,
            details={"schemes": valid_schemes}
        )
    
    async def test_security_requirements_reference(self) -> AuthTestResult:
        """
        Test: Verify security requirements reference valid scheme names.
        """
        test_name = "security_requirements_reference"
        start = time.perf_counter()
        
        card = await self._fetch_agent_card()
        duration_ms = (time.perf_counter() - start) * 1000
        
        if not card:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="Cannot fetch Agent Card",
                duration_ms=duration_ms
            )
        
        security_requirements = card.get("security", [])
        security_schemes = card.get("securitySchemes", {})
        
        if not security_requirements:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="No security requirements declared",
                duration_ms=duration_ms,
                details={"has_schemes": len(security_schemes) > 0}
            )
        
        defined_schemes = set(security_schemes.keys())
        undefined_refs = []
        valid_refs = []
        
        for i, requirement in enumerate(security_requirements):
            if not isinstance(requirement, dict):
                undefined_refs.append(f"requirement[{i}]: not an object")
                continue
            
            for scheme_name, scopes in requirement.items():
                if scheme_name not in defined_schemes:
                    undefined_refs.append(scheme_name)
                else:
                    valid_refs.append({"scheme": scheme_name, "scopes": scopes})
        
        if undefined_refs:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.FAILED,
                message=f"Security requirements reference undefined schemes",
                duration_ms=duration_ms,
                details={
                    "undefined": undefined_refs,
                    "defined_schemes": list(defined_schemes)
                },
                suggestion="All security requirements must reference schemes defined in securitySchemes"
            )
        
        return AuthTestResult(
            test_name=test_name,
            status=AuthTestStatus.PASSED,
            message=f"All security requirements reference valid schemes ({len(valid_refs)})",
            duration_ms=duration_ms,
            details={"requirements": valid_refs}
        )
    
    async def test_https_enforcement(self) -> AuthTestResult:
        """
        Test: Check if agent uses HTTPS in production.
        """
        test_name = "https_enforcement"
        start = time.perf_counter()
        
        card = await self._fetch_agent_card()
        duration_ms = (time.perf_counter() - start) * 1000
        
        if not card:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="Cannot fetch Agent Card",
                duration_ms=duration_ms
            )
        
        url = card.get("url", self.base_url)
        is_localhost = any(x in url.lower() for x in ["localhost", "127.0.0.1", "::1", "[::1]"])
        is_https = url.startswith("https://")
        
        if is_https:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.PASSED,
                message="Agent uses HTTPS",
                duration_ms=duration_ms,
                details={"url": url}
            )
        
        if is_localhost:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.PASSED,
                message="HTTP acceptable for localhost development",
                duration_ms=duration_ms,
                details={"url": url, "is_localhost": True}
            )
        
        return AuthTestResult(
            test_name=test_name,
            status=AuthTestStatus.FAILED,
            message="Agent should use HTTPS in production",
            duration_ms=duration_ms,
            details={"url": url},
            suggestion="Change http:// to https:// for secure communication"
        )
    
    async def test_apikey_auth_with_invalid_key(self) -> AuthTestResult:
        """
        Test: Send a request with an invalid API key to verify rejection.
        """
        test_name = "apikey_invalid_key"
        start = time.perf_counter()
        
        card = await self._fetch_agent_card()
        
        if not card:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="Cannot fetch Agent Card",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        # Find API key scheme
        security_schemes = card.get("securitySchemes", {})
        apikey_scheme = None
        for name, scheme in security_schemes.items():
            if scheme.get("type") == "apiKey":
                apikey_scheme = scheme
                break
        
        if not apikey_scheme:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.SKIPPED,
                message="No API key scheme declared",
                duration_ms=(time.perf_counter() - start) * 1000
            )
        
        key_name = apikey_scheme.get("name", "X-API-Key")
        key_location = apikey_scheme.get("in", "header")
        
        endpoint_url = card.get("url", f"{self.base_url}/a2a")
        request = self._build_simple_request()
        
        # Add invalid API key
        headers = self._get_headers()
        params = {}
        
        invalid_key = "invalid-test-key-12345"
        
        if key_location == "header":
            headers[key_name] = invalid_key
        elif key_location == "query":
            params[key_name] = invalid_key
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    endpoint_url,
                    json=request,
                    headers=headers,
                    params=params if params else None
                )
                duration_ms = (time.perf_counter() - start) * 1000
                
                if response.status_code in [401, 403]:
                    return AuthTestResult(
                        test_name=test_name,
                        status=AuthTestStatus.PASSED,
                        message=f"Correctly rejects invalid API key (HTTP {response.status_code})",
                        duration_ms=duration_ms,
                        details={"http_status": response.status_code}
                    )
                
                if response.status_code == 200:
                    try:
                        json_response = response.json()
                        if "error" in json_response:
                            return AuthTestResult(
                                test_name=test_name,
                                status=AuthTestStatus.PASSED,
                                message="Returns JSON-RPC error for invalid API key",
                                duration_ms=duration_ms,
                                details={"error": json_response["error"]}
                            )
                        else:
                            return AuthTestResult(
                                test_name=test_name,
                                status=AuthTestStatus.WARNING,
                                message="Request succeeded with invalid API key",
                                duration_ms=duration_ms,
                                suggestion="Agent may not be validating API keys"
                            )
                    except Exception:
                        pass
                
                return AuthTestResult(
                    test_name=test_name,
                    status=AuthTestStatus.WARNING,
                    message=f"Unexpected response: HTTP {response.status_code}",
                    duration_ms=duration_ms
                )
                
        except Exception as e:
            return AuthTestResult(
                test_name=test_name,
                status=AuthTestStatus.FAILED,
                message=f"Request failed: {type(e).__name__}",
                duration_ms=(time.perf_counter() - start) * 1000,
                error=str(e)
            )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FULL TEST SUITE
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def run_all_tests(self) -> AuthTestReport:
        """
        Run the complete auth test suite.
        
        Returns:
            AuthTestReport with all test results
        """
        report = AuthTestReport(agent_url=self.base_url)
        
        # Run all auth tests
        tests = [
            self.test_security_schemes_declared,
            self.test_https_enforcement,
            self.test_apikey_scheme_structure,
            self.test_http_scheme_structure,
            self.test_oauth2_scheme_structure,
            self.test_security_requirements_reference,
            self.test_unauthenticated_request,
            self.test_apikey_auth_with_invalid_key,
        ]
        
        for test_func in tests:
            try:
                result = await test_func()
                report.add_result(result)
            except Exception as e:
                report.add_result(AuthTestResult(
                    test_name=test_func.__name__.replace("test_", ""),
                    status=AuthTestStatus.FAILED,
                    message=f"Test crashed: {type(e).__name__}",
                    error=str(e)
                ))
        
        return report


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def run_auth_tests(
    agent_url: str,
    agent_card: Optional[dict] = None,
    timeout: float = 5.0
) -> AuthTestReport:
    """
    Run the complete auth test suite against an agent.
    
    Args:
        agent_url: Base URL of the A2A agent
        agent_card: Optional pre-fetched Agent Card
        timeout: Request timeout in seconds
        
    Returns:
        AuthTestReport with all test results
    """
    tester = AuthTester(agent_url, agent_card, timeout)
    return await tester.run_all_tests()
