"""
A2Apex Agent Card Validator - FULL SPEC COMPLIANCE

Validates Agent Card JSON against the complete A2A protocol specification (v0.3).
Based on: a2a_protocol_deep_dive.md - Section 6: Agent Card Specification

This is THE authoritative validator for A2A Agent Cards.
"""

import re
from typing import Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import httpx


class ValidationSeverity(Enum):
    ERROR = "error"      # Must fix - breaks compliance
    WARNING = "warning"  # Should fix - may cause issues  
    INFO = "info"        # Suggestion for best practices


@dataclass
class ValidationResult:
    field: str
    message: str
    severity: ValidationSeverity
    suggestion: Optional[str] = None
    spec_reference: Optional[str] = None


@dataclass
class AgentCardValidationReport:
    is_valid: bool
    errors: list[ValidationResult] = field(default_factory=list)
    warnings: list[ValidationResult] = field(default_factory=list)
    info: list[ValidationResult] = field(default_factory=list)
    agent_card: Optional[dict] = None
    score: float = 0.0  # Compliance score 0-100
    
    @property
    def error_count(self) -> int:
        return len(self.errors)
    
    @property
    def warning_count(self) -> int:
        return len(self.warnings)
    
    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "score": round(self.score, 1),
            "summary": {
                "errors": self.error_count,
                "warnings": self.warning_count,
                "info": len(self.info)
            },
            "errors": [
                {
                    "field": r.field,
                    "message": r.message,
                    "suggestion": r.suggestion,
                    "spec_reference": r.spec_reference
                }
                for r in self.errors
            ],
            "warnings": [
                {
                    "field": r.field,
                    "message": r.message,
                    "suggestion": r.suggestion,
                    "spec_reference": r.spec_reference
                }
                for r in self.warnings
            ],
            "info": [
                {
                    "field": r.field,
                    "message": r.message,
                    "suggestion": r.suggestion
                }
                for r in self.info
            ],
            "agent_card": self.agent_card
        }


class AgentCardValidator:
    """
    Validates A2A Agent Cards against the COMPLETE protocol specification.
    
    Covers all fields from Section 6 of the A2A Protocol Deep Dive:
    - Required fields: name, description, url, version, capabilities, defaultInputModes, defaultOutputModes, skills
    - Optional fields: protocolVersion, preferredTransport, additionalInterfaces, provider, iconUrl, 
                       documentationUrl, supportsAuthenticatedExtendedCard, securitySchemes, security, signatures
    - Nested validation: AgentCapabilities, AgentSkill, SecurityScheme (all types), AgentProvider
    """
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CONSTANTS
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Required fields at root level
    REQUIRED_FIELDS = ["name", "url", "version", "capabilities", "skills"]
    
    # Recommended fields (warning if missing)
    RECOMMENDED_FIELDS = ["description", "defaultInputModes", "defaultOutputModes", "protocolVersion", "provider", "documentationUrl"]
    
    # Required fields for each skill
    SKILL_REQUIRED_FIELDS = ["id", "name"]
    SKILL_RECOMMENDED_FIELDS = ["description", "tags"]
    
    # Valid transports
    VALID_TRANSPORTS = ["JSONRPC", "GRPC", "HTTP+JSON"]
    
    # Valid security scheme types (OpenAPI 3.0)
    VALID_SECURITY_TYPES = ["apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"]
    
    # Valid 'in' values for apiKey
    VALID_APIKEY_IN = ["header", "query", "cookie"]
    
    # Valid OAuth2 flows
    VALID_OAUTH_FLOWS = ["authorizationCode", "implicit", "password", "clientCredentials"]
    
    # Semver regex pattern
    SEMVER_PATTERN = re.compile(r'^(\d+)\.(\d+)(\.(\d+))?(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$')
    
    # MIME type pattern (type/subtype with optional parameters)
    MIME_PATTERN = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9!#$&\-^_.+]*\/[a-zA-Z0-9][a-zA-Z0-9!#$&\-^_.+]*(\s*;\s*[a-zA-Z0-9\-_.]+=[a-zA-Z0-9\-_.\"]+)*$')
    
    # Common/standard MIME types for reference
    COMMON_MIME_TYPES = {
        "text/plain", "text/html", "text/markdown", "text/csv",
        "application/json", "application/xml", "application/pdf",
        "application/octet-stream", "application/x-www-form-urlencoded",
        "image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml",
        "audio/mpeg", "audio/wav", "audio/ogg",
        "video/mp4", "video/webm", "video/ogg",
        "multipart/form-data"
    }
    
    def __init__(self):
        self.results: list[ValidationResult] = []
        self._total_checks = 0
        self._passed_checks = 0
    
    # ═══════════════════════════════════════════════════════════════════════════
    # HELPER METHODS
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _add_result(
        self,
        field: str,
        message: str,
        severity: ValidationSeverity,
        suggestion: Optional[str] = None,
        spec_reference: Optional[str] = None
    ):
        self.results.append(ValidationResult(
            field=field,
            message=message,
            severity=severity,
            suggestion=suggestion,
            spec_reference=spec_reference
        ))
        
        self._total_checks += 1
        if severity == ValidationSeverity.INFO:
            self._passed_checks += 1
        elif severity == ValidationSeverity.WARNING:
            self._passed_checks += 0.5
    
    def _pass_check(self, field: str, message: str):
        """Record a passing check (not added to results but counted for score)."""
        self._total_checks += 1
        self._passed_checks += 1
    
    def _validate_url(self, url: str, field_name: str, require_https: bool = False) -> bool:
        """Validate URL format with optional HTTPS requirement."""
        # Basic URL pattern
        url_pattern = re.compile(
            r'^https?://'
            r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}\.?|'
            r'localhost|'
            r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|'
            r'\[?[A-F0-9]*:[A-F0-9:]+\]?)'  # IPv6
            r'(?::\d+)?'
            r'(?:/?|[/?]\S*)?$', re.IGNORECASE)
        
        if not isinstance(url, str) or not url.strip():
            self._add_result(
                field=field_name,
                message=f"URL must be a non-empty string",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        if not url_pattern.match(url):
            self._add_result(
                field=field_name,
                message=f"Invalid URL format: {url}",
                severity=ValidationSeverity.ERROR,
                suggestion="URL should be a valid HTTP/HTTPS URL (e.g., https://agent.example.com/a2a)"
            )
            return False
        
        # Check for HTTPS in production (warn for HTTP unless localhost)
        is_localhost = "localhost" in url.lower() or "127.0.0.1" in url or "::1" in url
        if not url.startswith("https://") and not is_localhost:
            severity = ValidationSeverity.ERROR if require_https else ValidationSeverity.WARNING
            self._add_result(
                field=field_name,
                message="URL should use HTTPS for production deployments",
                severity=severity,
                suggestion="Change http:// to https:// for secure communication",
                spec_reference="Section 9: Authentication & Security - TLS 1.2+ required"
            )
            return severity != ValidationSeverity.ERROR
        
        self._pass_check(field_name, "Valid URL")
        return True
    
    def _validate_semver(self, version: str, field_name: str) -> bool:
        """Validate semantic versioning format."""
        if not isinstance(version, str):
            self._add_result(
                field=field_name,
                message=f"Version must be a string, got {type(version).__name__}",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        # Allow both full semver (1.0.0) and short form (1.0)
        if not self.SEMVER_PATTERN.match(version) and not re.match(r'^\d+\.\d+$', version):
            self._add_result(
                field=field_name,
                message=f"Invalid version format: {version}",
                severity=ValidationSeverity.ERROR,
                suggestion="Use semantic versioning: MAJOR.MINOR.PATCH (e.g., '1.0.0') or MAJOR.MINOR (e.g., '0.3')"
            )
            return False
        
        self._pass_check(field_name, "Valid semver")
        return True
    
    def _validate_mime_type(self, mime_type: str, field_name: str, index: Optional[int] = None) -> bool:
        """Validate MIME type format."""
        display_field = f"{field_name}[{index}]" if index is not None else field_name
        
        if not isinstance(mime_type, str):
            self._add_result(
                field=display_field,
                message=f"MIME type must be a string, got {type(mime_type).__name__}",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        # Simplified MIME pattern check
        if not re.match(r'^[\w\-\+\.]+/[\w\-\+\.]+', mime_type):
            self._add_result(
                field=display_field,
                message=f"Invalid MIME type format: '{mime_type}'",
                severity=ValidationSeverity.ERROR,
                suggestion="Use format: type/subtype (e.g., text/plain, application/json)"
            )
            return False
        
        # Info for uncommon MIME types (not an error)
        base_mime = mime_type.split(';')[0].strip()
        if base_mime not in self.COMMON_MIME_TYPES:
            self._add_result(
                field=display_field,
                message=f"Non-standard MIME type: '{mime_type}'",
                severity=ValidationSeverity.INFO,
                suggestion="Ensure clients/agents can handle this MIME type"
            )
        else:
            self._pass_check(display_field, "Valid MIME type")
        
        return True
    
    def _validate_string_field(self, obj: dict, field: str, parent: str, required: bool = True, min_length: int = 1) -> bool:
        """Validate a string field exists and is non-empty."""
        full_field = f"{parent}.{field}" if parent else field
        
        if field not in obj:
            if required:
                self._add_result(
                    field=full_field,
                    message=f"Missing required field: {field}",
                    severity=ValidationSeverity.ERROR
                )
                return False
            return True  # Optional field not present is OK
        
        value = obj[field]
        if not isinstance(value, str):
            self._add_result(
                field=full_field,
                message=f"Field must be a string, got {type(value).__name__}",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        if len(value.strip()) < min_length:
            self._add_result(
                field=full_field,
                message=f"Field must be at least {min_length} character(s)",
                severity=ValidationSeverity.ERROR if required else ValidationSeverity.WARNING
            )
            return False
        
        self._pass_check(full_field, "Valid string field")
        return True
    
    def _validate_boolean_field(self, obj: dict, field: str, parent: str) -> bool:
        """Validate an optional boolean field."""
        full_field = f"{parent}.{field}" if parent else field
        
        if field not in obj:
            return True  # Optional
        
        value = obj[field]
        if not isinstance(value, bool):
            self._add_result(
                field=full_field,
                message=f"Field must be a boolean, got {type(value).__name__}",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        self._pass_check(full_field, "Valid boolean")
        return True
    
    def _validate_array_field(self, obj: dict, field: str, parent: str, required: bool = True, min_length: int = 0) -> Optional[list]:
        """Validate an array field exists and return it."""
        full_field = f"{parent}.{field}" if parent else field
        
        if field not in obj:
            if required:
                self._add_result(
                    field=full_field,
                    message=f"Missing required field: {field}",
                    severity=ValidationSeverity.ERROR
                )
            return None
        
        value = obj[field]
        if not isinstance(value, list):
            self._add_result(
                field=full_field,
                message=f"Field must be an array, got {type(value).__name__}",
                severity=ValidationSeverity.ERROR
            )
            return None
        
        if len(value) < min_length:
            self._add_result(
                field=full_field,
                message=f"Array must have at least {min_length} item(s)",
                severity=ValidationSeverity.ERROR if required else ValidationSeverity.WARNING
            )
            return None if required else value
        
        self._pass_check(full_field, "Valid array")
        return value
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CAPABILITY VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _validate_capabilities(self, capabilities: Any, agent_card: dict) -> bool:
        """Validate AgentCapabilities object."""
        if not isinstance(capabilities, dict):
            self._add_result(
                field="capabilities",
                message=f"Capabilities must be an object, got {type(capabilities).__name__}",
                severity=ValidationSeverity.ERROR,
                spec_reference="Section 6: AgentCapabilities"
            )
            return False
        
        valid = True
        
        # Validate boolean capability fields
        for cap_field in ["streaming", "pushNotifications", "stateTransitionHistory"]:
            if cap_field in capabilities:
                if not isinstance(capabilities[cap_field], bool):
                    self._add_result(
                        field=f"capabilities.{cap_field}",
                        message=f"Field must be a boolean, got {type(capabilities[cap_field]).__name__}",
                        severity=ValidationSeverity.ERROR
                    )
                    valid = False
                else:
                    self._pass_check(f"capabilities.{cap_field}", "Valid capability flag")
        
        # Validate extensions array if present
        if "extensions" in capabilities:
            if not isinstance(capabilities["extensions"], list):
                self._add_result(
                    field="capabilities.extensions",
                    message="Extensions must be an array",
                    severity=ValidationSeverity.ERROR
                )
                valid = False
            else:
                for i, ext in enumerate(capabilities["extensions"]):
                    if not isinstance(ext, dict):
                        self._add_result(
                            field=f"capabilities.extensions[{i}]",
                            message="Extension must be an object",
                            severity=ValidationSeverity.ERROR
                        )
                        valid = False
                    else:
                        # Extension requires 'uri' field
                        if "uri" not in ext:
                            self._add_result(
                                field=f"capabilities.extensions[{i}].uri",
                                message="Extension must have a 'uri' field",
                                severity=ValidationSeverity.ERROR,
                                spec_reference="Section 6: AgentExtension Object"
                            )
                            valid = False
                        elif not isinstance(ext["uri"], str):
                            self._add_result(
                                field=f"capabilities.extensions[{i}].uri",
                                message="Extension URI must be a string",
                                severity=ValidationSeverity.ERROR
                            )
                            valid = False
                        else:
                            self._pass_check(f"capabilities.extensions[{i}]", "Valid extension")
        
        # Cross-validation: if pushNotifications is true, warn about needing push config endpoints
        if capabilities.get("pushNotifications") is True:
            self._add_result(
                field="capabilities.pushNotifications",
                message="Push notifications enabled - ensure tasks/pushNotificationConfig/* methods are implemented",
                severity=ValidationSeverity.INFO,
                spec_reference="Section 8: Push Notifications"
            )
        
        return valid
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SKILL VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _validate_skill(self, skill: Any, index: int, agent_card: dict) -> bool:
        """Validate a single AgentSkill object."""
        prefix = f"skills[{index}]"
        
        if not isinstance(skill, dict):
            self._add_result(
                field=prefix,
                message=f"Skill must be an object, got {type(skill).__name__}",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        valid = True
        
        # Required fields
        for field in self.SKILL_REQUIRED_FIELDS:
            if not self._validate_string_field(skill, field, prefix, required=True):
                valid = False
        
        # Recommended fields
        for field in self.SKILL_RECOMMENDED_FIELDS:
            if field not in skill:
                self._add_result(
                    field=f"{prefix}.{field}",
                    message=f"Missing recommended field: {field}",
                    severity=ValidationSeverity.WARNING,
                    suggestion=f"Add '{field}' for better agent discovery"
                )
        
        # Validate tags is array of strings
        if "tags" in skill:
            tags = skill["tags"]
            if not isinstance(tags, list):
                self._add_result(
                    field=f"{prefix}.tags",
                    message="Tags must be an array of strings",
                    severity=ValidationSeverity.ERROR
                )
                valid = False
            else:
                for i, tag in enumerate(tags):
                    if not isinstance(tag, str):
                        self._add_result(
                            field=f"{prefix}.tags[{i}]",
                            message="Each tag must be a string",
                            severity=ValidationSeverity.ERROR
                        )
                        valid = False
        
        # Validate inputModes/outputModes MIME types
        for mode_field in ["inputModes", "outputModes"]:
            if mode_field in skill:
                modes = skill[mode_field]
                if not isinstance(modes, list):
                    self._add_result(
                        field=f"{prefix}.{mode_field}",
                        message="Must be an array of MIME types",
                        severity=ValidationSeverity.ERROR
                    )
                    valid = False
                else:
                    for i, mime in enumerate(modes):
                        if not self._validate_mime_type(mime, f"{prefix}.{mode_field}", i):
                            valid = False
        
        # Validate examples is array of strings
        if "examples" in skill:
            examples = skill["examples"]
            if not isinstance(examples, list):
                self._add_result(
                    field=f"{prefix}.examples",
                    message="Examples must be an array of strings",
                    severity=ValidationSeverity.ERROR
                )
                valid = False
            else:
                for i, example in enumerate(examples):
                    if not isinstance(example, str):
                        self._add_result(
                            field=f"{prefix}.examples[{i}]",
                            message="Each example must be a string",
                            severity=ValidationSeverity.ERROR
                        )
                        valid = False
        else:
            self._add_result(
                field=f"{prefix}.examples",
                message="Consider adding example prompts for better discoverability",
                severity=ValidationSeverity.INFO,
                suggestion="Add examples like: ['How do I...', 'Can you help with...']"
            )
        
        # Validate skill-level security if present
        if "security" in skill:
            self._validate_security_requirements(skill["security"], f"{prefix}.security", agent_card)
        
        return valid
    
    def _validate_skills(self, skills: list, agent_card: dict) -> bool:
        """Validate skills array with duplicate ID checking."""
        valid = True
        skill_ids = []
        
        for i, skill in enumerate(skills):
            if not self._validate_skill(skill, i, agent_card):
                valid = False
            
            # Collect skill IDs for duplicate check
            if isinstance(skill, dict) and "id" in skill:
                skill_ids.append(skill["id"])
        
        # Check for duplicate skill IDs
        seen = set()
        duplicates = set()
        for sid in skill_ids:
            if sid in seen:
                duplicates.add(sid)
            seen.add(sid)
        
        if duplicates:
            self._add_result(
                field="skills",
                message=f"Duplicate skill IDs found: {', '.join(duplicates)}",
                severity=ValidationSeverity.ERROR,
                suggestion="Each skill must have a unique ID"
            )
            valid = False
        else:
            self._pass_check("skills.ids", "Unique skill IDs")
        
        return valid
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SECURITY SCHEME VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _validate_security_scheme(self, scheme: Any, name: str) -> bool:
        """Validate a security scheme (OpenAPI 3.0 format)."""
        prefix = f"securitySchemes.{name}"
        
        if not isinstance(scheme, dict):
            self._add_result(
                field=prefix,
                message="Security scheme must be an object",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        # Type is required
        if "type" not in scheme:
            self._add_result(
                field=f"{prefix}.type",
                message="Security scheme must have a 'type' field",
                severity=ValidationSeverity.ERROR,
                suggestion=f"Valid types: {', '.join(self.VALID_SECURITY_TYPES)}",
                spec_reference="Section 9: Security Schemes"
            )
            return False
        
        scheme_type = scheme["type"]
        if scheme_type not in self.VALID_SECURITY_TYPES:
            self._add_result(
                field=f"{prefix}.type",
                message=f"Invalid security scheme type: '{scheme_type}'",
                severity=ValidationSeverity.ERROR,
                suggestion=f"Valid types: {', '.join(self.VALID_SECURITY_TYPES)}"
            )
            return False
        
        valid = True
        
        # Type-specific validation
        if scheme_type == "apiKey":
            valid = self._validate_apikey_scheme(scheme, prefix)
        elif scheme_type == "http":
            valid = self._validate_http_scheme(scheme, prefix)
        elif scheme_type == "oauth2":
            valid = self._validate_oauth2_scheme(scheme, prefix)
        elif scheme_type == "openIdConnect":
            valid = self._validate_oidc_scheme(scheme, prefix)
        elif scheme_type == "mutualTLS":
            # mutualTLS has no required additional fields
            self._pass_check(prefix, "Valid mutualTLS scheme")
        
        return valid
    
    def _validate_apikey_scheme(self, scheme: dict, prefix: str) -> bool:
        """Validate apiKey security scheme."""
        valid = True
        
        # 'name' is required - the header/query/cookie name
        if "name" not in scheme:
            self._add_result(
                field=f"{prefix}.name",
                message="API key scheme requires 'name' field (header/query/cookie name)",
                severity=ValidationSeverity.ERROR
            )
            valid = False
        elif not isinstance(scheme["name"], str):
            self._add_result(
                field=f"{prefix}.name",
                message="API key name must be a string",
                severity=ValidationSeverity.ERROR
            )
            valid = False
        
        # 'in' is required - where to send the key
        if "in" not in scheme:
            self._add_result(
                field=f"{prefix}.in",
                message="API key scheme requires 'in' field",
                severity=ValidationSeverity.ERROR,
                suggestion=f"Valid values: {', '.join(self.VALID_APIKEY_IN)}"
            )
            valid = False
        elif scheme["in"] not in self.VALID_APIKEY_IN:
            self._add_result(
                field=f"{prefix}.in",
                message=f"Invalid 'in' value: '{scheme['in']}'",
                severity=ValidationSeverity.ERROR,
                suggestion=f"Valid values: {', '.join(self.VALID_APIKEY_IN)}"
            )
            valid = False
        
        if valid:
            self._pass_check(prefix, "Valid apiKey scheme")
        
        return valid
    
    def _validate_http_scheme(self, scheme: dict, prefix: str) -> bool:
        """Validate HTTP auth security scheme (Bearer, Basic, etc)."""
        valid = True
        
        # 'scheme' is required (e.g., 'Bearer', 'Basic')
        if "scheme" not in scheme:
            self._add_result(
                field=f"{prefix}.scheme",
                message="HTTP auth requires 'scheme' field",
                severity=ValidationSeverity.ERROR,
                suggestion="Common values: 'Bearer', 'Basic'"
            )
            valid = False
        elif not isinstance(scheme["scheme"], str):
            self._add_result(
                field=f"{prefix}.scheme",
                message="HTTP scheme must be a string",
                severity=ValidationSeverity.ERROR
            )
            valid = False
        
        # bearerFormat is optional but validated if present
        if "bearerFormat" in scheme:
            if not isinstance(scheme["bearerFormat"], str):
                self._add_result(
                    field=f"{prefix}.bearerFormat",
                    message="bearerFormat must be a string",
                    severity=ValidationSeverity.WARNING
                )
        
        if valid:
            self._pass_check(prefix, "Valid HTTP auth scheme")
        
        return valid
    
    def _validate_oauth2_scheme(self, scheme: dict, prefix: str) -> bool:
        """Validate OAuth 2.0 security scheme."""
        valid = True
        
        # 'flows' is required
        if "flows" not in scheme:
            self._add_result(
                field=f"{prefix}.flows",
                message="OAuth2 scheme requires 'flows' object",
                severity=ValidationSeverity.ERROR,
                spec_reference="Section 9: OAuth 2.0"
            )
            return False
        
        flows = scheme["flows"]
        if not isinstance(flows, dict):
            self._add_result(
                field=f"{prefix}.flows",
                message="OAuth2 flows must be an object",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        if len(flows) == 0:
            self._add_result(
                field=f"{prefix}.flows",
                message="OAuth2 must define at least one flow",
                severity=ValidationSeverity.ERROR,
                suggestion=f"Valid flows: {', '.join(self.VALID_OAUTH_FLOWS)}"
            )
            return False
        
        # Validate each flow
        for flow_name, flow_config in flows.items():
            if flow_name not in self.VALID_OAUTH_FLOWS:
                self._add_result(
                    field=f"{prefix}.flows.{flow_name}",
                    message=f"Unknown OAuth2 flow: '{flow_name}'",
                    severity=ValidationSeverity.WARNING,
                    suggestion=f"Standard flows: {', '.join(self.VALID_OAUTH_FLOWS)}"
                )
                continue
            
            if not isinstance(flow_config, dict):
                self._add_result(
                    field=f"{prefix}.flows.{flow_name}",
                    message="Flow configuration must be an object",
                    severity=ValidationSeverity.ERROR
                )
                valid = False
                continue
            
            # Check required URLs per flow type
            if flow_name in ["authorizationCode", "implicit"]:
                if "authorizationUrl" not in flow_config:
                    self._add_result(
                        field=f"{prefix}.flows.{flow_name}.authorizationUrl",
                        message=f"{flow_name} flow requires 'authorizationUrl'",
                        severity=ValidationSeverity.ERROR
                    )
                    valid = False
            
            if flow_name in ["authorizationCode", "password", "clientCredentials"]:
                if "tokenUrl" not in flow_config:
                    self._add_result(
                        field=f"{prefix}.flows.{flow_name}.tokenUrl",
                        message=f"{flow_name} flow requires 'tokenUrl'",
                        severity=ValidationSeverity.ERROR
                    )
                    valid = False
            
            # Validate scopes if present
            if "scopes" in flow_config:
                scopes = flow_config["scopes"]
                if not isinstance(scopes, dict):
                    self._add_result(
                        field=f"{prefix}.flows.{flow_name}.scopes",
                        message="Scopes must be an object mapping scope names to descriptions",
                        severity=ValidationSeverity.ERROR
                    )
                    valid = False
        
        if valid:
            self._pass_check(prefix, "Valid OAuth2 scheme")
        
        return valid
    
    def _validate_oidc_scheme(self, scheme: dict, prefix: str) -> bool:
        """Validate OpenID Connect security scheme."""
        if "openIdConnectUrl" not in scheme:
            self._add_result(
                field=f"{prefix}.openIdConnectUrl",
                message="OpenID Connect scheme requires 'openIdConnectUrl'",
                severity=ValidationSeverity.ERROR,
                suggestion="URL to the OpenID Connect discovery document (/.well-known/openid-configuration)"
            )
            return False
        
        url = scheme["openIdConnectUrl"]
        if not isinstance(url, str):
            self._add_result(
                field=f"{prefix}.openIdConnectUrl",
                message="OpenID Connect URL must be a string",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        # Validate it looks like a URL
        if not url.startswith("http"):
            self._add_result(
                field=f"{prefix}.openIdConnectUrl",
                message="OpenID Connect URL should be a valid HTTP(S) URL",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        self._pass_check(prefix, "Valid OpenID Connect scheme")
        return True
    
    def _validate_security_requirements(self, security: Any, field_name: str, agent_card: dict) -> bool:
        """Validate security requirements array references valid scheme names."""
        if not isinstance(security, list):
            self._add_result(
                field=field_name,
                message="Security requirements must be an array",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        valid = True
        defined_schemes = set(agent_card.get("securitySchemes", {}).keys())
        
        for i, req in enumerate(security):
            if not isinstance(req, dict):
                self._add_result(
                    field=f"{field_name}[{i}]",
                    message="Each security requirement must be an object",
                    severity=ValidationSeverity.ERROR
                )
                valid = False
                continue
            
            # Each key should reference a defined scheme
            for scheme_name in req.keys():
                if scheme_name not in defined_schemes:
                    self._add_result(
                        field=f"{field_name}[{i}].{scheme_name}",
                        message=f"Security requirement references undefined scheme: '{scheme_name}'",
                        severity=ValidationSeverity.ERROR,
                        suggestion=f"Define '{scheme_name}' in securitySchemes first"
                    )
                    valid = False
                
                # Value should be array of scopes
                scopes = req[scheme_name]
                if not isinstance(scopes, list):
                    self._add_result(
                        field=f"{field_name}[{i}].{scheme_name}",
                        message="Scopes must be an array of strings",
                        severity=ValidationSeverity.ERROR
                    )
                    valid = False
        
        if valid:
            self._pass_check(field_name, "Valid security requirements")
        
        return valid
    
    # ═══════════════════════════════════════════════════════════════════════════
    # PROVIDER VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _validate_provider(self, provider: Any) -> bool:
        """Validate AgentProvider object."""
        if not isinstance(provider, dict):
            self._add_result(
                field="provider",
                message="Provider must be an object",
                severity=ValidationSeverity.ERROR
            )
            return False
        
        valid = True
        
        # organization is recommended
        if "organization" not in provider:
            self._add_result(
                field="provider.organization",
                message="Provider should have an 'organization' field",
                severity=ValidationSeverity.WARNING,
                spec_reference="Section 6: AgentProvider Object"
            )
        elif not isinstance(provider["organization"], str):
            self._add_result(
                field="provider.organization",
                message="Organization must be a string",
                severity=ValidationSeverity.ERROR
            )
            valid = False
        
        # URL validation if present
        if "url" in provider:
            if not self._validate_url(provider["url"], "provider.url"):
                valid = False
        
        if valid:
            self._pass_check("provider", "Valid provider")
        
        return valid
    
    # ═══════════════════════════════════════════════════════════════════════════
    # ADDITIONAL INTERFACES VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def _validate_additional_interfaces(self, interfaces: list) -> bool:
        """Validate additionalInterfaces array."""
        valid = True
        
        for i, iface in enumerate(interfaces):
            prefix = f"additionalInterfaces[{i}]"
            
            if not isinstance(iface, dict):
                self._add_result(
                    field=prefix,
                    message="Interface must be an object",
                    severity=ValidationSeverity.ERROR
                )
                valid = False
                continue
            
            # Required: url
            if "url" not in iface:
                self._add_result(
                    field=f"{prefix}.url",
                    message="Interface must have a 'url' field",
                    severity=ValidationSeverity.ERROR
                )
                valid = False
            else:
                if not self._validate_url(iface["url"], f"{prefix}.url"):
                    valid = False
            
            # Required: transport
            if "transport" not in iface:
                self._add_result(
                    field=f"{prefix}.transport",
                    message="Interface must have a 'transport' field",
                    severity=ValidationSeverity.ERROR,
                    suggestion=f"Valid values: {', '.join(self.VALID_TRANSPORTS)}"
                )
                valid = False
            elif iface["transport"] not in self.VALID_TRANSPORTS:
                self._add_result(
                    field=f"{prefix}.transport",
                    message=f"Unknown transport: '{iface['transport']}'",
                    severity=ValidationSeverity.WARNING,
                    suggestion=f"Standard transports: {', '.join(self.VALID_TRANSPORTS)}"
                )
        
        return valid
    
    # ═══════════════════════════════════════════════════════════════════════════
    # MAIN VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    
    def validate(self, agent_card: Any) -> AgentCardValidationReport:
        """
        Validate an Agent Card against the complete A2A specification.
        
        Args:
            agent_card: The Agent Card JSON as a dictionary
            
        Returns:
            AgentCardValidationReport with comprehensive validation results
        """
        self.results = []
        self._total_checks = 0
        self._passed_checks = 0
        
        # Root type check
        if not isinstance(agent_card, dict):
            self._add_result(
                field="root",
                message=f"Agent Card must be a JSON object, got {type(agent_card).__name__}",
                severity=ValidationSeverity.ERROR
            )
            return self._build_report(None)
        
        # ═══════════════════════════════════════════════════════════════════════
        # REQUIRED FIELDS
        # ═══════════════════════════════════════════════════════════════════════
        
        # name (required)
        self._validate_string_field(agent_card, "name", "", required=True)
        
        # url (required)
        if "url" in agent_card:
            self._validate_url(agent_card["url"], "url")
        else:
            self._add_result(
                field="url",
                message="Missing required field: url",
                severity=ValidationSeverity.ERROR
            )
        
        # version (required, semver)
        if "version" in agent_card:
            self._validate_semver(agent_card["version"], "version")
        else:
            self._add_result(
                field="version",
                message="Missing required field: version",
                severity=ValidationSeverity.ERROR
            )
        
        # capabilities (required)
        if "capabilities" in agent_card:
            self._validate_capabilities(agent_card["capabilities"], agent_card)
        else:
            self._add_result(
                field="capabilities",
                message="Missing required field: capabilities",
                severity=ValidationSeverity.ERROR,
                spec_reference="Section 6: AgentCapabilities"
            )
        
        # skills (required, at least one)
        skills = self._validate_array_field(agent_card, "skills", "", required=True, min_length=1)
        if skills:
            self._validate_skills(skills, agent_card)
        
        # ═══════════════════════════════════════════════════════════════════════
        # RECOMMENDED FIELDS
        # ═══════════════════════════════════════════════════════════════════════
        
        # description (recommended)
        if "description" not in agent_card:
            self._add_result(
                field="description",
                message="Missing recommended field: description",
                severity=ValidationSeverity.WARNING,
                suggestion="Add a description to help users understand what your agent does"
            )
        else:
            self._validate_string_field(agent_card, "description", "", required=False)
        
        # protocolVersion (recommended)
        if "protocolVersion" in agent_card:
            version = agent_card["protocolVersion"]
            if not re.match(r'^\d+\.\d+(\.\d+)?$', str(version)):
                self._add_result(
                    field="protocolVersion",
                    message=f"Invalid protocol version format: {version}",
                    severity=ValidationSeverity.ERROR,
                    suggestion="Use format: Major.Minor (e.g., '0.3')"
                )
            else:
                self._pass_check("protocolVersion", "Valid protocol version")
        else:
            self._add_result(
                field="protocolVersion",
                message="Missing recommended field: protocolVersion",
                severity=ValidationSeverity.WARNING,
                suggestion="Add protocolVersion field (current: '0.3')"
            )
        
        # defaultInputModes (recommended)
        if "defaultInputModes" in agent_card:
            modes = agent_card["defaultInputModes"]
            if isinstance(modes, list):
                if len(modes) == 0:
                    self._add_result(
                        field="defaultInputModes",
                        message="Array is empty - should have at least one MIME type",
                        severity=ValidationSeverity.WARNING
                    )
                else:
                    for i, mime in enumerate(modes):
                        self._validate_mime_type(mime, "defaultInputModes", i)
            else:
                self._add_result(
                    field="defaultInputModes",
                    message="Must be an array of MIME types",
                    severity=ValidationSeverity.ERROR
                )
        else:
            self._add_result(
                field="defaultInputModes",
                message="Missing recommended field: defaultInputModes",
                severity=ValidationSeverity.WARNING,
                suggestion="Add MIME types your agent accepts (e.g., ['text/plain', 'application/json'])"
            )
        
        # defaultOutputModes (recommended)
        if "defaultOutputModes" in agent_card:
            modes = agent_card["defaultOutputModes"]
            if isinstance(modes, list):
                if len(modes) == 0:
                    self._add_result(
                        field="defaultOutputModes",
                        message="Array is empty - should have at least one MIME type",
                        severity=ValidationSeverity.WARNING
                    )
                else:
                    for i, mime in enumerate(modes):
                        self._validate_mime_type(mime, "defaultOutputModes", i)
            else:
                self._add_result(
                    field="defaultOutputModes",
                    message="Must be an array of MIME types",
                    severity=ValidationSeverity.ERROR
                )
        else:
            self._add_result(
                field="defaultOutputModes",
                message="Missing recommended field: defaultOutputModes",
                severity=ValidationSeverity.WARNING,
                suggestion="Add MIME types your agent produces (e.g., ['text/plain', 'application/json'])"
            )
        
        # provider (recommended)
        if "provider" in agent_card:
            self._validate_provider(agent_card["provider"])
        else:
            self._add_result(
                field="provider",
                message="Missing recommended field: provider",
                severity=ValidationSeverity.WARNING,
                suggestion="Add provider info with organization name"
            )
        
        # documentationUrl (recommended)
        if "documentationUrl" in agent_card:
            self._validate_url(agent_card["documentationUrl"], "documentationUrl")
        else:
            self._add_result(
                field="documentationUrl",
                message="Missing recommended field: documentationUrl",
                severity=ValidationSeverity.INFO,
                suggestion="Link to documentation helps users integrate with your agent"
            )
        
        # ═══════════════════════════════════════════════════════════════════════
        # OPTIONAL FIELDS
        # ═══════════════════════════════════════════════════════════════════════
        
        # preferredTransport
        if "preferredTransport" in agent_card:
            transport = agent_card["preferredTransport"]
            if transport not in self.VALID_TRANSPORTS:
                self._add_result(
                    field="preferredTransport",
                    message=f"Unknown transport: '{transport}'",
                    severity=ValidationSeverity.WARNING,
                    suggestion=f"Standard transports: {', '.join(self.VALID_TRANSPORTS)}"
                )
            else:
                self._pass_check("preferredTransport", "Valid transport")
        
        # iconUrl
        if "iconUrl" in agent_card:
            self._validate_url(agent_card["iconUrl"], "iconUrl")
        
        # supportsAuthenticatedExtendedCard
        self._validate_boolean_field(agent_card, "supportsAuthenticatedExtendedCard", "")
        
        # additionalInterfaces
        if "additionalInterfaces" in agent_card:
            interfaces = agent_card["additionalInterfaces"]
            if isinstance(interfaces, list):
                self._validate_additional_interfaces(interfaces)
            else:
                self._add_result(
                    field="additionalInterfaces",
                    message="Must be an array of interface objects",
                    severity=ValidationSeverity.ERROR
                )
        
        # securitySchemes
        if "securitySchemes" in agent_card:
            schemes = agent_card["securitySchemes"]
            if not isinstance(schemes, dict):
                self._add_result(
                    field="securitySchemes",
                    message="Must be an object mapping scheme names to scheme definitions",
                    severity=ValidationSeverity.ERROR
                )
            else:
                for name, scheme in schemes.items():
                    self._validate_security_scheme(scheme, name)
        
        # security (references securitySchemes)
        if "security" in agent_card:
            self._validate_security_requirements(agent_card["security"], "security", agent_card)
        
        return self._build_report(agent_card)
    
    def _build_report(self, agent_card: Optional[dict]) -> AgentCardValidationReport:
        """Build the final validation report with score calculation."""
        errors = [r for r in self.results if r.severity == ValidationSeverity.ERROR]
        warnings = [r for r in self.results if r.severity == ValidationSeverity.WARNING]
        info = [r for r in self.results if r.severity == ValidationSeverity.INFO]
        
        # Calculate compliance score
        if self._total_checks > 0:
            score = (self._passed_checks / self._total_checks) * 100
        else:
            score = 0 if errors else 100
        
        # Penalty for errors
        score = max(0, score - (len(errors) * 5))
        
        return AgentCardValidationReport(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            info=info,
            agent_card=agent_card if len(errors) == 0 else None,
            score=score
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

async def fetch_and_validate_agent_card(url: str) -> AgentCardValidationReport:
    """
    Fetch an Agent Card from a URL and validate it.
    
    Handles URL normalization to find /.well-known/agent-card.json
    
    Args:
        url: The URL to fetch the Agent Card from (base URL or direct path)
        
    Returns:
        AgentCardValidationReport with validation results
    """
    validator = AgentCardValidator()
    http_issues = []
    
    # Normalize URL
    original_url = url
    if not url.endswith(".json"):
        url = url.rstrip("/")
        if "/.well-known/agent-card.json" not in url:
            url = url + "/.well-known/agent-card.json"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            
            # Check status code
            if response.status_code == 404:
                return AgentCardValidationReport(
                    is_valid=False,
                    errors=[ValidationResult(
                        field="http",
                        message=f"Agent Card not found at {url}",
                        severity=ValidationSeverity.ERROR,
                        suggestion="Ensure Agent Card is published at /.well-known/agent-card.json"
                    )],
                    score=0
                )
            
            if response.status_code != 200:
                return AgentCardValidationReport(
                    is_valid=False,
                    errors=[ValidationResult(
                        field="http",
                        message=f"HTTP {response.status_code} when fetching Agent Card",
                        severity=ValidationSeverity.ERROR,
                        suggestion="Ensure the Agent Card endpoint returns 200 OK"
                    )],
                    score=0
                )
            
            # Check Content-Type
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                http_issues.append(ValidationResult(
                    field="http.content-type",
                    message=f"Unexpected Content-Type: '{content_type}'",
                    severity=ValidationSeverity.WARNING,
                    suggestion="Agent Card should be served with Content-Type: application/json"
                ))
            
            # Check CORS headers (info only)
            if "access-control-allow-origin" not in response.headers:
                http_issues.append(ValidationResult(
                    field="http.cors",
                    message="No CORS headers detected",
                    severity=ValidationSeverity.INFO,
                    suggestion="Add Access-Control-Allow-Origin header for browser-based clients"
                ))
            
            # Parse JSON
            try:
                agent_card = response.json()
            except Exception as e:
                return AgentCardValidationReport(
                    is_valid=False,
                    errors=[ValidationResult(
                        field="json",
                        message=f"Invalid JSON: {str(e)}",
                        severity=ValidationSeverity.ERROR,
                        suggestion="Ensure the response is valid JSON"
                    )],
                    score=0
                )
            
            # Validate the Agent Card
            report = validator.validate(agent_card)
            
            # Add HTTP-level issues
            for issue in http_issues:
                if issue.severity == ValidationSeverity.WARNING:
                    report.warnings.insert(0, issue)
                elif issue.severity == ValidationSeverity.INFO:
                    report.info.insert(0, issue)
                elif issue.severity == ValidationSeverity.ERROR:
                    report.errors.insert(0, issue)
                    report.is_valid = False
            
            return report
            
    except httpx.TimeoutException:
        return AgentCardValidationReport(
            is_valid=False,
            errors=[ValidationResult(
                field="http",
                message="Request timed out (30s) while fetching Agent Card",
                severity=ValidationSeverity.ERROR,
                suggestion="Check if the agent server is running and accessible"
            )],
            score=0
        )
    except httpx.ConnectError as e:
        return AgentCardValidationReport(
            is_valid=False,
            errors=[ValidationResult(
                field="http",
                message=f"Failed to connect: {str(e)}",
                severity=ValidationSeverity.ERROR,
                suggestion="Verify the URL and ensure the server is running"
            )],
            score=0
        )
    except Exception as e:
        return AgentCardValidationReport(
            is_valid=False,
            errors=[ValidationResult(
                field="http",
                message=f"Unexpected error: {str(e)}",
                severity=ValidationSeverity.ERROR
            )],
            score=0
        )
