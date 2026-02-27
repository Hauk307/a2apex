"""
A2A Agent Card Validator

Standalone validation for A2A Agent Cards against the protocol specification.
No server connection needed — just pass in a dict and get a validation report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATION TYPES
# ═══════════════════════════════════════════════════════════════════════════════


class Severity(str, Enum):
    """Validation result severity levels."""

    ERROR = "error"  # Must fix — breaks compliance
    WARNING = "warning"  # Should fix — may cause issues
    INFO = "info"  # Suggestion for best practices


@dataclass
class ValidationIssue:
    """A single validation issue found."""

    field: str
    message: str
    severity: Severity
    suggestion: str | None = None
    spec_reference: str | None = None

    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "message": self.message,
            "severity": self.severity.value,
            "suggestion": self.suggestion,
            "spec_reference": self.spec_reference,
        }


@dataclass
class ValidationReport:
    """Complete validation report for an Agent Card."""

    is_valid: bool
    score: float  # 0-100 compliance score
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    info: list[ValidationIssue] = field(default_factory=list)
    agent_card: dict | None = None

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    @property
    def info_count(self) -> int:
        return len(self.info)

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "score": round(self.score, 1),
            "summary": {
                "errors": self.error_count,
                "warnings": self.warning_count,
                "info": self.info_count,
            },
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "info": [i.to_dict() for i in self.info],
        }

    def __str__(self) -> str:
        status = "✓ Valid" if self.is_valid else "✗ Invalid"
        return (
            f"{status} (Score: {self.score:.0f}/100) — "
            f"{self.error_count} errors, {self.warning_count} warnings"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

REQUIRED_FIELDS = ["name", "url", "version", "capabilities", "skills"]
RECOMMENDED_FIELDS = [
    "description",
    "defaultInputModes",
    "defaultOutputModes",
    "protocolVersion",
    "provider",
]
SKILL_REQUIRED_FIELDS = ["id", "name"]
VALID_TRANSPORTS = ["JSONRPC", "GRPC", "HTTP+JSON"]
VALID_SECURITY_TYPES = ["apiKey", "http", "oauth2", "openIdConnect", "mutualTLS"]
VALID_APIKEY_IN = ["header", "query", "cookie"]
VALID_OAUTH_FLOWS = ["authorizationCode", "implicit", "password", "clientCredentials"]

SEMVER_PATTERN = re.compile(
    r"^(\d+)\.(\d+)(\.(\d+))?(-[a-zA-Z0-9.-]+)?(\+[a-zA-Z0-9.-]+)?$"
)

COMMON_MIME_TYPES = {
    "text/plain",
    "text/html",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/xml",
    "application/pdf",
    "application/octet-stream",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "audio/mpeg",
    "audio/wav",
    "video/mp4",
    "video/webm",
}


# ═══════════════════════════════════════════════════════════════════════════════
# VALIDATOR CLASS
# ═══════════════════════════════════════════════════════════════════════════════


class AgentCardValidator:
    """
    Validates A2A Agent Cards against the complete protocol specification.

    Usage:
        validator = AgentCardValidator()
        report = validator.validate(agent_card_dict)
        print(f"Score: {report.score}/100")
        for error in report.errors:
            print(f"  ✗ {error.field}: {error.message}")
    """

    def __init__(self) -> None:
        self._issues: list[ValidationIssue] = []
        self._total_checks = 0
        self._passed_checks = 0

    def _add_issue(
        self,
        field: str,
        message: str,
        severity: Severity,
        suggestion: str | None = None,
        spec_reference: str | None = None,
    ) -> None:
        """Record a validation issue."""
        self._issues.append(
            ValidationIssue(
                field=field,
                message=message,
                severity=severity,
                suggestion=suggestion,
                spec_reference=spec_reference,
            )
        )
        self._total_checks += 1
        if severity == Severity.INFO:
            self._passed_checks += 1
        elif severity == Severity.WARNING:
            self._passed_checks += 0.5

    def _pass(self) -> None:
        """Record a passing check."""
        self._total_checks += 1
        self._passed_checks += 1

    def _validate_url(
        self,
        url: str,
        field_name: str,
        require_https: bool = False,
    ) -> bool:
        """Validate URL format."""
        url_pattern = re.compile(
            r"^https?://"
            r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,63}\.?|"
            r"localhost|"
            r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|"
            r"\[?[A-F0-9]*:[A-F0-9:]+\]?)"
            r"(?::\d+)?"
            r"(?:/?|[/?]\S*)?$",
            re.IGNORECASE,
        )

        if not isinstance(url, str) or not url.strip():
            self._add_issue(field_name, "URL must be a non-empty string", Severity.ERROR)
            return False

        if not url_pattern.match(url):
            self._add_issue(
                field_name,
                f"Invalid URL format: {url}",
                Severity.ERROR,
                suggestion="URL should be a valid HTTP/HTTPS URL",
            )
            return False

        # Check HTTPS
        is_localhost = "localhost" in url.lower() or "127.0.0.1" in url or "::1" in url
        if not url.startswith("https://") and not is_localhost:
            severity = Severity.ERROR if require_https else Severity.WARNING
            self._add_issue(
                field_name,
                "URL should use HTTPS for production",
                severity,
                suggestion="Change http:// to https://",
                spec_reference="Section 9: Authentication & Security",
            )
            return severity != Severity.ERROR

        self._pass()
        return True

    def _validate_semver(self, version: str, field_name: str) -> bool:
        """Validate semantic versioning format."""
        if not isinstance(version, str):
            self._add_issue(
                field_name,
                f"Version must be a string, got {type(version).__name__}",
                Severity.ERROR,
            )
            return False

        if not SEMVER_PATTERN.match(version) and not re.match(r"^\d+\.\d+$", version):
            self._add_issue(
                field_name,
                f"Invalid version format: {version}",
                Severity.ERROR,
                suggestion="Use semver: MAJOR.MINOR.PATCH (e.g., '1.0.0')",
            )
            return False

        self._pass()
        return True

    def _validate_mime_type(
        self,
        mime: str,
        field_name: str,
        index: int | None = None,
    ) -> bool:
        """Validate MIME type format."""
        display = f"{field_name}[{index}]" if index is not None else field_name

        if not isinstance(mime, str):
            self._add_issue(
                display,
                f"MIME type must be a string, got {type(mime).__name__}",
                Severity.ERROR,
            )
            return False

        if not re.match(r"^[\w\-\+\.]+/[\w\-\+\.]+", mime):
            self._add_issue(
                display,
                f"Invalid MIME type format: '{mime}'",
                Severity.ERROR,
                suggestion="Use format: type/subtype (e.g., text/plain)",
            )
            return False

        base_mime = mime.split(";")[0].strip()
        if base_mime not in COMMON_MIME_TYPES:
            self._add_issue(
                display,
                f"Non-standard MIME type: '{mime}'",
                Severity.INFO,
                suggestion="Ensure clients can handle this MIME type",
            )
        else:
            self._pass()

        return True

    def _validate_capabilities(self, capabilities: Any, card: dict) -> bool:
        """Validate AgentCapabilities object."""
        if not isinstance(capabilities, dict):
            self._add_issue(
                "capabilities",
                f"Must be an object, got {type(capabilities).__name__}",
                Severity.ERROR,
                spec_reference="Section 6: AgentCapabilities",
            )
            return False

        valid = True

        # Boolean fields
        for cap in ["streaming", "pushNotifications", "stateTransitionHistory"]:
            if cap in capabilities:
                if not isinstance(capabilities[cap], bool):
                    self._add_issue(
                        f"capabilities.{cap}",
                        f"Must be boolean, got {type(capabilities[cap]).__name__}",
                        Severity.ERROR,
                    )
                    valid = False
                else:
                    self._pass()

        # Extensions array
        if "extensions" in capabilities:
            exts = capabilities["extensions"]
            if not isinstance(exts, list):
                self._add_issue(
                    "capabilities.extensions",
                    "Must be an array",
                    Severity.ERROR,
                )
                valid = False
            else:
                for i, ext in enumerate(exts):
                    if not isinstance(ext, dict):
                        self._add_issue(
                            f"capabilities.extensions[{i}]",
                            "Extension must be an object",
                            Severity.ERROR,
                        )
                        valid = False
                    elif "uri" not in ext:
                        self._add_issue(
                            f"capabilities.extensions[{i}].uri",
                            "Extension must have 'uri' field",
                            Severity.ERROR,
                        )
                        valid = False
                    else:
                        self._pass()

        # Info about push notifications
        if capabilities.get("pushNotifications") is True:
            self._add_issue(
                "capabilities.pushNotifications",
                "Push notifications enabled — ensure push config methods are implemented",
                Severity.INFO,
                spec_reference="Section 8: Push Notifications",
            )

        return valid

    def _validate_skill(self, skill: Any, index: int, card: dict) -> bool:
        """Validate a single AgentSkill."""
        prefix = f"skills[{index}]"

        if not isinstance(skill, dict):
            self._add_issue(
                prefix,
                f"Skill must be an object, got {type(skill).__name__}",
                Severity.ERROR,
            )
            return False

        valid = True

        # Required fields
        for req in SKILL_REQUIRED_FIELDS:
            if req not in skill:
                self._add_issue(f"{prefix}.{req}", f"Missing required field: {req}", Severity.ERROR)
                valid = False
            elif not isinstance(skill[req], str) or not skill[req].strip():
                self._add_issue(f"{prefix}.{req}", f"Must be non-empty string", Severity.ERROR)
                valid = False
            else:
                self._pass()

        # Recommended fields
        for rec in ["description", "tags"]:
            if rec not in skill:
                self._add_issue(
                    f"{prefix}.{rec}",
                    f"Missing recommended field: {rec}",
                    Severity.WARNING,
                    suggestion=f"Add '{rec}' for better discoverability",
                )

        # Tags array
        if "tags" in skill:
            tags = skill["tags"]
            if not isinstance(tags, list):
                self._add_issue(f"{prefix}.tags", "Tags must be an array", Severity.ERROR)
                valid = False
            else:
                for i, tag in enumerate(tags):
                    if not isinstance(tag, str):
                        self._add_issue(f"{prefix}.tags[{i}]", "Tag must be a string", Severity.ERROR)
                        valid = False

        # MIME types
        for mode in ["inputModes", "outputModes"]:
            if mode in skill:
                modes = skill[mode]
                if not isinstance(modes, list):
                    self._add_issue(f"{prefix}.{mode}", "Must be array of MIME types", Severity.ERROR)
                    valid = False
                else:
                    for i, mime in enumerate(modes):
                        if not self._validate_mime_type(mime, f"{prefix}.{mode}", i):
                            valid = False

        # Examples
        if "examples" in skill:
            examples = skill["examples"]
            if not isinstance(examples, list):
                self._add_issue(f"{prefix}.examples", "Must be an array", Severity.ERROR)
                valid = False
            else:
                for i, ex in enumerate(examples):
                    if not isinstance(ex, str):
                        self._add_issue(f"{prefix}.examples[{i}]", "Must be a string", Severity.ERROR)
                        valid = False
        else:
            self._add_issue(
                f"{prefix}.examples",
                "Consider adding example prompts",
                Severity.INFO,
                suggestion="Add examples like: ['How do I...', 'Can you help with...']",
            )

        return valid

    def _validate_skills(self, skills: list, card: dict) -> bool:
        """Validate skills array with duplicate ID checking."""
        valid = True
        skill_ids: list[str] = []

        for i, skill in enumerate(skills):
            if not self._validate_skill(skill, i, card):
                valid = False

            if isinstance(skill, dict) and "id" in skill:
                skill_ids.append(skill["id"])

        # Check duplicates
        seen: set[str] = set()
        duplicates: set[str] = set()
        for sid in skill_ids:
            if sid in seen:
                duplicates.add(sid)
            seen.add(sid)

        if duplicates:
            self._add_issue(
                "skills",
                f"Duplicate skill IDs: {', '.join(duplicates)}",
                Severity.ERROR,
                suggestion="Each skill must have a unique ID",
            )
            valid = False
        else:
            self._pass()

        return valid

    def _validate_security_scheme(self, scheme: Any, name: str) -> bool:
        """Validate a security scheme."""
        prefix = f"securitySchemes.{name}"

        if not isinstance(scheme, dict):
            self._add_issue(prefix, "Must be an object", Severity.ERROR)
            return False

        if "type" not in scheme:
            self._add_issue(
                f"{prefix}.type",
                "Missing required 'type' field",
                Severity.ERROR,
                suggestion=f"Valid types: {', '.join(VALID_SECURITY_TYPES)}",
            )
            return False

        scheme_type = scheme["type"]
        if scheme_type not in VALID_SECURITY_TYPES:
            self._add_issue(
                f"{prefix}.type",
                f"Invalid type: '{scheme_type}'",
                Severity.ERROR,
                suggestion=f"Valid types: {', '.join(VALID_SECURITY_TYPES)}",
            )
            return False

        valid = True

        if scheme_type == "apiKey":
            if "name" not in scheme:
                self._add_issue(f"{prefix}.name", "API key requires 'name' field", Severity.ERROR)
                valid = False
            if "in" not in scheme:
                self._add_issue(
                    f"{prefix}.in",
                    "API key requires 'in' field",
                    Severity.ERROR,
                    suggestion=f"Valid values: {', '.join(VALID_APIKEY_IN)}",
                )
                valid = False
            elif scheme["in"] not in VALID_APIKEY_IN:
                self._add_issue(
                    f"{prefix}.in",
                    f"Invalid 'in' value: '{scheme['in']}'",
                    Severity.ERROR,
                )
                valid = False

        elif scheme_type == "http":
            if "scheme" not in scheme:
                self._add_issue(
                    f"{prefix}.scheme",
                    "HTTP auth requires 'scheme' field",
                    Severity.ERROR,
                    suggestion="Common values: 'Bearer', 'Basic'",
                )
                valid = False

        elif scheme_type == "oauth2":
            if "flows" not in scheme:
                self._add_issue(f"{prefix}.flows", "OAuth2 requires 'flows' object", Severity.ERROR)
                valid = False
            elif not isinstance(scheme["flows"], dict):
                self._add_issue(f"{prefix}.flows", "Must be an object", Severity.ERROR)
                valid = False
            else:
                flows = scheme["flows"]
                for flow_name, flow_config in flows.items():
                    if flow_name not in VALID_OAUTH_FLOWS:
                        self._add_issue(
                            f"{prefix}.flows.{flow_name}",
                            f"Unknown flow: '{flow_name}'",
                            Severity.WARNING,
                        )
                        continue
                    if not isinstance(flow_config, dict):
                        self._add_issue(
                            f"{prefix}.flows.{flow_name}",
                            "Flow config must be an object",
                            Severity.ERROR,
                        )
                        valid = False
                        continue
                    # Check required URLs per flow
                    if flow_name in ["authorizationCode", "implicit"]:
                        if "authorizationUrl" not in flow_config:
                            self._add_issue(
                                f"{prefix}.flows.{flow_name}.authorizationUrl",
                                f"{flow_name} requires 'authorizationUrl'",
                                Severity.ERROR,
                            )
                            valid = False
                    if flow_name in ["authorizationCode", "password", "clientCredentials"]:
                        if "tokenUrl" not in flow_config:
                            self._add_issue(
                                f"{prefix}.flows.{flow_name}.tokenUrl",
                                f"{flow_name} requires 'tokenUrl'",
                                Severity.ERROR,
                            )
                            valid = False

        elif scheme_type == "openIdConnect":
            if "openIdConnectUrl" not in scheme:
                self._add_issue(
                    f"{prefix}.openIdConnectUrl",
                    "OpenID Connect requires 'openIdConnectUrl'",
                    Severity.ERROR,
                )
                valid = False

        if valid:
            self._pass()
        return valid

    def _validate_provider(self, provider: Any) -> bool:
        """Validate AgentProvider object."""
        if not isinstance(provider, dict):
            self._add_issue("provider", "Must be an object", Severity.ERROR)
            return False

        valid = True

        if "organization" not in provider:
            self._add_issue(
                "provider.organization",
                "Missing recommended 'organization' field",
                Severity.WARNING,
            )
        elif not isinstance(provider["organization"], str):
            self._add_issue("provider.organization", "Must be a string", Severity.ERROR)
            valid = False

        if "url" in provider:
            if not self._validate_url(provider["url"], "provider.url"):
                valid = False

        if valid:
            self._pass()
        return valid

    def validate(self, agent_card: Any) -> ValidationReport:
        """
        Validate an Agent Card against the A2A specification.

        Args:
            agent_card: Agent Card as a dictionary

        Returns:
            ValidationReport with comprehensive results
        """
        self._issues = []
        self._total_checks = 0
        self._passed_checks = 0

        # Root type check
        if not isinstance(agent_card, dict):
            self._add_issue(
                "root",
                f"Agent Card must be an object, got {type(agent_card).__name__}",
                Severity.ERROR,
            )
            return self._build_report(None)

        # ════════════════════════════════════════════════════════════════════════
        # REQUIRED FIELDS
        # ════════════════════════════════════════════════════════════════════════

        # name
        if "name" not in agent_card:
            self._add_issue("name", "Missing required field: name", Severity.ERROR)
        elif not isinstance(agent_card["name"], str) or not agent_card["name"].strip():
            self._add_issue("name", "Must be a non-empty string", Severity.ERROR)
        else:
            self._pass()

        # url
        if "url" not in agent_card:
            self._add_issue("url", "Missing required field: url", Severity.ERROR)
        else:
            self._validate_url(agent_card["url"], "url")

        # version
        if "version" not in agent_card:
            self._add_issue("version", "Missing required field: version", Severity.ERROR)
        else:
            self._validate_semver(agent_card["version"], "version")

        # capabilities
        if "capabilities" not in agent_card:
            self._add_issue(
                "capabilities",
                "Missing required field: capabilities",
                Severity.ERROR,
                spec_reference="Section 6: AgentCapabilities",
            )
        else:
            self._validate_capabilities(agent_card["capabilities"], agent_card)

        # skills
        if "skills" not in agent_card:
            self._add_issue("skills", "Missing required field: skills", Severity.ERROR)
        elif not isinstance(agent_card["skills"], list):
            self._add_issue("skills", "Must be an array", Severity.ERROR)
        elif len(agent_card["skills"]) == 0:
            self._add_issue("skills", "Must have at least one skill", Severity.ERROR)
        else:
            self._validate_skills(agent_card["skills"], agent_card)

        # ════════════════════════════════════════════════════════════════════════
        # RECOMMENDED FIELDS
        # ════════════════════════════════════════════════════════════════════════

        if "description" not in agent_card:
            self._add_issue(
                "description",
                "Missing recommended field: description",
                Severity.WARNING,
                suggestion="Add a description to help users understand your agent",
            )
        elif not isinstance(agent_card["description"], str):
            self._add_issue("description", "Must be a string", Severity.ERROR)
        else:
            self._pass()

        if "protocolVersion" in agent_card:
            pv = agent_card["protocolVersion"]
            if not re.match(r"^\d+\.\d+(\.\d+)?$", str(pv)):
                self._add_issue(
                    "protocolVersion",
                    f"Invalid format: {pv}",
                    Severity.ERROR,
                    suggestion="Use format: Major.Minor (e.g., '0.3')",
                )
            else:
                self._pass()
        else:
            self._add_issue(
                "protocolVersion",
                "Missing recommended field: protocolVersion",
                Severity.WARNING,
                suggestion="Add protocolVersion (current: '0.3')",
            )

        for mode_field in ["defaultInputModes", "defaultOutputModes"]:
            if mode_field in agent_card:
                modes = agent_card[mode_field]
                if not isinstance(modes, list):
                    self._add_issue(mode_field, "Must be array of MIME types", Severity.ERROR)
                elif len(modes) == 0:
                    self._add_issue(mode_field, "Should have at least one MIME type", Severity.WARNING)
                else:
                    for i, mime in enumerate(modes):
                        self._validate_mime_type(mime, mode_field, i)
            else:
                self._add_issue(
                    mode_field,
                    f"Missing recommended field: {mode_field}",
                    Severity.WARNING,
                    suggestion="Add MIME types (e.g., ['text/plain', 'application/json'])",
                )

        if "provider" in agent_card:
            self._validate_provider(agent_card["provider"])
        else:
            self._add_issue(
                "provider",
                "Missing recommended field: provider",
                Severity.WARNING,
                suggestion="Add provider info with organization name",
            )

        # ════════════════════════════════════════════════════════════════════════
        # OPTIONAL FIELDS
        # ════════════════════════════════════════════════════════════════════════

        if "preferredTransport" in agent_card:
            transport = agent_card["preferredTransport"]
            if transport not in VALID_TRANSPORTS:
                self._add_issue(
                    "preferredTransport",
                    f"Unknown transport: '{transport}'",
                    Severity.WARNING,
                    suggestion=f"Standard transports: {', '.join(VALID_TRANSPORTS)}",
                )
            else:
                self._pass()

        if "iconUrl" in agent_card:
            self._validate_url(agent_card["iconUrl"], "iconUrl")

        if "documentationUrl" in agent_card:
            self._validate_url(agent_card["documentationUrl"], "documentationUrl")
        else:
            self._add_issue(
                "documentationUrl",
                "Missing recommended field: documentationUrl",
                Severity.INFO,
                suggestion="Link to docs helps users integrate with your agent",
            )

        if "securitySchemes" in agent_card:
            schemes = agent_card["securitySchemes"]
            if isinstance(schemes, dict):
                for name, scheme in schemes.items():
                    self._validate_security_scheme(scheme, name)

        return self._build_report(agent_card)

    def _build_report(self, agent_card: dict | None) -> ValidationReport:
        """Build the final validation report."""
        errors = [i for i in self._issues if i.severity == Severity.ERROR]
        warnings = [i for i in self._issues if i.severity == Severity.WARNING]
        info = [i for i in self._issues if i.severity == Severity.INFO]

        # Calculate score
        if self._total_checks > 0:
            score = (self._passed_checks / self._total_checks) * 100
        else:
            score = 0.0

        return ValidationReport(
            is_valid=len(errors) == 0,
            score=score,
            errors=errors,
            warnings=warnings,
            info=info,
            agent_card=agent_card,
        )


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════


def validate_agent_card(card: dict) -> ValidationReport:
    """
    Validate an Agent Card against the A2A specification.

    Args:
        card: Agent Card as a dictionary

    Returns:
        ValidationReport with score, errors, warnings, and info

    Example:
        from a2apex import validate_agent_card

        report = validate_agent_card({"name": "My Agent", ...})
        print(f"Score: {report.score}/100")
        for error in report.errors:
            print(f"  ✗ {error.field}: {error.message}")
    """
    validator = AgentCardValidator()
    return validator.validate(card)
