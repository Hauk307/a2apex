"""Tests for the Agent Card validator."""

import pytest

from a2apex import validate_agent_card, Severity, AgentCardValidator


# ═══════════════════════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def valid_card():
    """A valid, complete Agent Card."""
    return {
        "name": "Test Agent",
        "description": "A test agent for validation",
        "url": "https://agent.example.com/a2a",
        "version": "1.0.0",
        "protocolVersion": "0.3",
        "capabilities": {
            "streaming": True,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [
            {
                "id": "chat",
                "name": "Chat",
                "description": "General conversation",
                "tags": ["conversation", "chat"],
                "examples": ["Hello!", "What can you do?"],
            }
        ],
        "provider": {
            "organization": "Test Corp",
            "url": "https://testcorp.com",
        },
        "documentationUrl": "https://docs.example.com",
    }


@pytest.fixture
def minimal_card():
    """Minimal valid Agent Card (required fields only)."""
    return {
        "name": "Minimal Agent",
        "url": "https://agent.example.com/a2a",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "skill1", "name": "Skill One"}],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# VALID CARDS
# ═══════════════════════════════════════════════════════════════════════════════


def test_valid_card_passes(valid_card):
    """A complete, valid card should pass with no errors."""
    report = validate_agent_card(valid_card)
    assert report.is_valid
    assert report.error_count == 0
    assert report.score > 80


def test_minimal_card_has_warnings(minimal_card):
    """Minimal card should be valid but have warnings."""
    report = validate_agent_card(minimal_card)
    assert report.is_valid
    assert report.error_count == 0
    assert report.warning_count > 0  # Missing recommended fields


# ═══════════════════════════════════════════════════════════════════════════════
# MISSING REQUIRED FIELDS
# ═══════════════════════════════════════════════════════════════════════════════


def test_missing_name():
    """Missing name should be an error."""
    card = {
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any(e.field == "name" for e in report.errors)


def test_missing_url():
    """Missing url should be an error."""
    card = {
        "name": "Agent",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any(e.field == "url" for e in report.errors)


def test_missing_version():
    """Missing version should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any(e.field == "version" for e in report.errors)


def test_missing_capabilities():
    """Missing capabilities should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any(e.field == "capabilities" for e in report.errors)


def test_missing_skills():
    """Missing skills should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any(e.field == "skills" for e in report.errors)


def test_empty_skills():
    """Empty skills array should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [],
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any("skills" in e.field for e in report.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# INVALID VALUES
# ═══════════════════════════════════════════════════════════════════════════════


def test_invalid_url():
    """Invalid URL format should be an error."""
    card = {
        "name": "Agent",
        "url": "not-a-valid-url",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any(e.field == "url" for e in report.errors)


def test_invalid_version():
    """Invalid semver should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "not-semver",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any(e.field == "version" for e in report.errors)


def test_http_url_warning():
    """HTTP URL (non-localhost) should trigger warning."""
    card = {
        "name": "Agent",
        "url": "http://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    assert any(
        w.field == "url" and "HTTPS" in w.message for w in report.warnings + report.errors
    )


def test_localhost_http_ok():
    """HTTP localhost should be OK (no warning)."""
    card = {
        "name": "Agent",
        "url": "http://localhost:8080/a2a",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    # Should not have HTTPS warning for localhost
    https_issues = [
        i for i in report.errors + report.warnings if "HTTPS" in i.message
    ]
    assert len(https_issues) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# MIME TYPE VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


def test_valid_mime_types():
    """Standard MIME types should pass."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "defaultInputModes": ["text/plain", "application/json", "image/png"],
        "defaultOutputModes": ["text/plain"],
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    # No MIME-related errors
    mime_errors = [e for e in report.errors if "MIME" in e.message]
    assert len(mime_errors) == 0


def test_invalid_mime_type():
    """Invalid MIME type format should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "defaultInputModes": ["json"],  # Invalid - should be application/json
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    assert any("MIME" in e.message for e in report.errors)


def test_nonstandard_mime_info():
    """Non-standard MIME type should get INFO (not error)."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "defaultInputModes": ["application/x-custom-type"],
        "skills": [{"id": "s1", "name": "S1"}],
    }
    report = validate_agent_card(card)
    assert report.is_valid  # Should still be valid
    assert any("Non-standard MIME" in i.message for i in report.info)


# ═══════════════════════════════════════════════════════════════════════════════
# SKILL VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


def test_skill_missing_id():
    """Skill without id should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"name": "Skill One"}],  # Missing id
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any("skills[0].id" in e.field for e in report.errors)


def test_skill_missing_name():
    """Skill without name should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1"}],  # Missing name
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any("skills[0].name" in e.field for e in report.errors)


def test_duplicate_skill_ids():
    """Duplicate skill IDs should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [
            {"id": "chat", "name": "Chat"},
            {"id": "chat", "name": "Chat 2"},  # Duplicate!
        ],
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any("Duplicate" in e.message for e in report.errors)


def test_skill_missing_recommended():
    """Skill without description/tags should get warnings."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "Skill One"}],
    }
    report = validate_agent_card(card)
    assert report.is_valid  # Should still be valid
    assert any("description" in w.field for w in report.warnings)


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY SCHEME VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════


def test_valid_apikey_scheme():
    """Valid API key scheme should pass."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
        "securitySchemes": {
            "apiKey": {
                "type": "apiKey",
                "name": "X-API-Key",
                "in": "header",
            }
        },
    }
    report = validate_agent_card(card)
    scheme_errors = [e for e in report.errors if "securitySchemes" in e.field]
    assert len(scheme_errors) == 0


def test_invalid_security_type():
    """Invalid security scheme type should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
        "securitySchemes": {
            "invalid": {"type": "notAValidType"},
        },
    }
    report = validate_agent_card(card)
    assert not report.is_valid
    assert any("type" in e.field for e in report.errors)


def test_apikey_missing_in():
    """API key scheme without 'in' should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
        "securitySchemes": {
            "apiKey": {
                "type": "apiKey",
                "name": "X-API-Key",
                # Missing 'in'
            }
        },
    }
    report = validate_agent_card(card)
    assert any(".in" in e.field for e in report.errors)


def test_oauth2_missing_flows():
    """OAuth2 scheme without flows should be an error."""
    card = {
        "name": "Agent",
        "url": "https://agent.example.com",
        "version": "1.0.0",
        "capabilities": {},
        "skills": [{"id": "s1", "name": "S1"}],
        "securitySchemes": {
            "oauth": {"type": "oauth2"},  # Missing flows
        },
    }
    report = validate_agent_card(card)
    assert any("flows" in e.field for e in report.errors)


# ═══════════════════════════════════════════════════════════════════════════════
# REPORT METHODS
# ═══════════════════════════════════════════════════════════════════════════════


def test_report_to_dict(valid_card):
    """Report should serialize to dict."""
    report = validate_agent_card(valid_card)
    d = report.to_dict()
    assert "is_valid" in d
    assert "score" in d
    assert "summary" in d
    assert "errors" in d
    assert "warnings" in d


def test_report_str(valid_card):
    """Report should have string representation."""
    report = validate_agent_card(valid_card)
    s = str(report)
    assert "Valid" in s or "Invalid" in s
    assert "Score" in s


# ═══════════════════════════════════════════════════════════════════════════════
# EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════


def test_not_a_dict():
    """Non-dict input should be an error."""
    report = validate_agent_card("not a dict")
    assert not report.is_valid
    assert any("object" in e.message.lower() for e in report.errors)


def test_empty_dict():
    """Empty dict should have multiple errors."""
    report = validate_agent_card({})
    assert not report.is_valid
    assert report.error_count >= 5  # Missing all required fields


def test_validator_reuse():
    """Validator should be reusable."""
    validator = AgentCardValidator()

    r1 = validator.validate({"name": "Agent1"})
    r2 = validator.validate({"name": "Agent2"})

    # Results should be independent
    assert r1.agent_card.get("name") == "Agent1"
    assert r2.agent_card.get("name") == "Agent2"
