"""Tests for the Pydantic models."""

import pytest
from pydantic import ValidationError

from a2apex import (
    AgentCard,
    AgentCapabilities,
    AgentSkill,
    AgentProvider,
    Task,
    TaskState,
    TaskStatus,
    Message,
    MessageRole,
    TextPart,
    FilePart,
    DataPart,
    FileWithUri,
    FileWithBytes,
    Artifact,
    JsonRpcRequest,
    JsonRpcResponse,
    JsonRpcError,
    ApiKeySecurityScheme,
    HttpSecurityScheme,
    OAuth2SecurityScheme,
    create_text_message,
    create_jsonrpc_request,
    is_interrupted_state,
)
from a2apex.models import is_terminal_state


# ═══════════════════════════════════════════════════════════════════════════════
# PART TYPES
# ═══════════════════════════════════════════════════════════════════════════════


class TestTextPart:
    def test_basic(self):
        part = TextPart(text="Hello world")
        assert part.kind == "text"
        assert part.text == "Hello world"
        assert part.metadata is None

    def test_with_metadata(self):
        part = TextPart(text="Hello", metadata={"lang": "en"})
        assert part.metadata == {"lang": "en"}

    def test_serialization(self):
        part = TextPart(text="Hello")
        d = part.model_dump()
        assert d["kind"] == "text"
        assert d["text"] == "Hello"


class TestFilePart:
    def test_with_uri(self):
        part = FilePart(
            file=FileWithUri(uri="https://example.com/file.pdf", mimeType="application/pdf")
        )
        assert part.kind == "file"
        assert part.file.uri == "https://example.com/file.pdf"

    def test_with_bytes(self):
        part = FilePart(file=FileWithBytes(bytes="SGVsbG8gV29ybGQ=", name="hello.txt"))
        assert part.kind == "file"
        assert part.file.bytes == "SGVsbG8gV29ybGQ="


class TestDataPart:
    def test_basic(self):
        part = DataPart(data={"key": "value", "number": 42})
        assert part.kind == "data"
        assert part.data["key"] == "value"
        assert part.data["number"] == 42


# ═══════════════════════════════════════════════════════════════════════════════
# MESSAGE
# ═══════════════════════════════════════════════════════════════════════════════


class TestMessage:
    def test_basic(self):
        msg = Message(
            role=MessageRole.USER,
            messageId="msg-123",
            parts=[TextPart(text="Hello")],
        )
        assert msg.role == MessageRole.USER
        assert msg.message_id == "msg-123"
        assert len(msg.parts) == 1
        assert msg.kind == "message"

    def test_with_context(self):
        msg = Message(
            role=MessageRole.AGENT,
            messageId="msg-456",
            parts=[TextPart(text="Hi there!")],
            contextId="ctx-789",
            taskId="task-abc",
        )
        assert msg.context_id == "ctx-789"
        assert msg.task_id == "task-abc"

    def test_helper_function(self):
        msg = create_text_message("Hello!")
        assert msg.role == MessageRole.USER
        assert len(msg.parts) == 1
        assert msg.parts[0].text == "Hello!"
        assert msg.message_id is not None


# ═══════════════════════════════════════════════════════════════════════════════
# TASK
# ═══════════════════════════════════════════════════════════════════════════════


class TestTask:
    def test_basic(self):
        task = Task(
            id="task-123",
            contextId="ctx-456",
            status=TaskStatus(state=TaskState.WORKING),
        )
        assert task.id == "task-123"
        assert task.context_id == "ctx-456"
        assert task.status.state == TaskState.WORKING
        assert task.kind == "task"

    def test_with_artifacts(self):
        task = Task(
            id="task-123",
            contextId="ctx-456",
            status=TaskStatus(state=TaskState.COMPLETED),
            artifacts=[
                Artifact(
                    artifactId="art-1",
                    name="Result",
                    parts=[TextPart(text="The answer is 42")],
                )
            ],
        )
        assert len(task.artifacts) == 1
        assert task.artifacts[0].name == "Result"

    def test_with_history(self):
        task = Task(
            id="task-123",
            contextId="ctx-456",
            status=TaskStatus(state=TaskState.COMPLETED),
            history=[
                Message(
                    role=MessageRole.USER,
                    messageId="m1",
                    parts=[TextPart(text="Hello")],
                ),
                Message(
                    role=MessageRole.AGENT,
                    messageId="m2",
                    parts=[TextPart(text="Hi!")],
                ),
            ],
        )
        assert len(task.history) == 2


class TestTaskState:
    def test_all_states(self):
        """All expected states should exist."""
        states = [
            "submitted",
            "working",
            "input-required",
            "auth-required",
            "completed",
            "failed",
            "canceled",
            "rejected",
        ]
        for s in states:
            assert TaskState(s) is not None

    def test_terminal_states(self):
        assert is_terminal_state(TaskState.COMPLETED)
        assert is_terminal_state(TaskState.FAILED)
        assert is_terminal_state(TaskState.CANCELED)
        assert is_terminal_state(TaskState.REJECTED)
        assert not is_terminal_state(TaskState.WORKING)
        assert not is_terminal_state(TaskState.SUBMITTED)

    def test_interrupted_states(self):
        assert is_interrupted_state(TaskState.INPUT_REQUIRED)
        assert is_interrupted_state(TaskState.AUTH_REQUIRED)
        assert not is_interrupted_state(TaskState.WORKING)


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT CARD
# ═══════════════════════════════════════════════════════════════════════════════


class TestAgentCard:
    def test_minimal(self):
        card = AgentCard(
            name="Test Agent",
            url="https://agent.example.com",
            version="1.0.0",
            capabilities=AgentCapabilities(),
            skills=[
                AgentSkill(id="skill1", name="Skill One"),
            ],
        )
        assert card.name == "Test Agent"
        assert card.capabilities.streaming is False

    def test_full(self):
        card = AgentCard(
            name="Full Agent",
            description="A complete agent",
            url="https://agent.example.com/a2a",
            version="2.1.0",
            protocolVersion="0.3",
            capabilities=AgentCapabilities(streaming=True, pushNotifications=True),
            defaultInputModes=["text/plain"],
            defaultOutputModes=["text/plain", "application/json"],
            skills=[
                AgentSkill(
                    id="chat",
                    name="Chat",
                    description="General conversation",
                    tags=["conversation"],
                    examples=["Hello!"],
                )
            ],
            provider=AgentProvider(organization="Test Corp"),
            documentationUrl="https://docs.example.com",
        )
        assert card.capabilities.streaming is True
        assert len(card.default_input_modes) == 1

    def test_parse_from_dict(self):
        """Should parse from a raw dict."""
        data = {
            "name": "Parsed Agent",
            "url": "https://example.com",
            "version": "1.0.0",
            "capabilities": {"streaming": True},
            "skills": [{"id": "s1", "name": "S1", "description": "Desc", "tags": []}],
        }
        card = AgentCard.model_validate(data)
        assert card.name == "Parsed Agent"
        assert card.capabilities.streaming is True


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY SCHEMES
# ═══════════════════════════════════════════════════════════════════════════════


class TestSecuritySchemes:
    def test_apikey(self):
        scheme = ApiKeySecurityScheme(name="X-API-Key", **{"in": "header"})
        assert scheme.type == "apiKey"
        assert scheme.name == "X-API-Key"
        assert scheme.in_ == "header"

    def test_http_bearer(self):
        scheme = HttpSecurityScheme(scheme="Bearer", bearerFormat="JWT")
        assert scheme.type == "http"
        assert scheme.scheme == "Bearer"
        assert scheme.bearer_format == "JWT"

    def test_oauth2(self):
        from a2apex.models import OAuth2Flows, OAuth2Flow

        scheme = OAuth2SecurityScheme(
            flows=OAuth2Flows(
                clientCredentials=OAuth2Flow(
                    tokenUrl="https://auth.example.com/token",
                    scopes={"read": "Read access"},
                )
            )
        )
        assert scheme.type == "oauth2"
        assert scheme.flows.client_credentials.token_url == "https://auth.example.com/token"


# ═══════════════════════════════════════════════════════════════════════════════
# JSON-RPC
# ═══════════════════════════════════════════════════════════════════════════════


class TestJsonRpc:
    def test_request(self):
        req = JsonRpcRequest(
            id="req-123",
            method="message/send",
            params={"message": {"role": "user"}},
        )
        assert req.jsonrpc == "2.0"
        assert req.method == "message/send"

    def test_response_success(self):
        resp = JsonRpcResponse(
            id="req-123",
            result={"task": {"id": "task-1"}},
        )
        assert resp.jsonrpc == "2.0"
        assert resp.result is not None
        assert resp.error is None

    def test_response_error(self):
        resp = JsonRpcResponse(
            id="req-123",
            error=JsonRpcError(code=-32001, message="Task not found"),
        )
        assert resp.error.code == -32001
        assert resp.result is None

    def test_helper_function(self):
        req = create_jsonrpc_request("tasks/get", {"id": "task-123"})
        assert req.method == "tasks/get"
        assert req.params["id"] == "task-123"
        assert req.id is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SERIALIZATION
# ═══════════════════════════════════════════════════════════════════════════════


class TestSerialization:
    def test_message_roundtrip(self):
        msg = Message(
            role=MessageRole.USER,
            messageId="m1",
            parts=[TextPart(text="Hello")],
        )
        d = msg.model_dump(by_alias=True)
        assert d["messageId"] == "m1"
        assert d["parts"][0]["kind"] == "text"

        # Parse back
        msg2 = Message.model_validate(d)
        assert msg2.message_id == "m1"

    def test_task_roundtrip(self):
        task = Task(
            id="t1",
            contextId="c1",
            status=TaskStatus(state=TaskState.COMPLETED),
            artifacts=[
                Artifact(artifactId="a1", parts=[TextPart(text="Result")])
            ],
        )
        d = task.model_dump(by_alias=True)
        assert d["contextId"] == "c1"
        assert d["status"]["state"] == "completed"

        task2 = Task.model_validate(d)
        assert task2.id == "t1"
        assert task2.status.state == TaskState.COMPLETED

    def test_agent_card_roundtrip(self):
        card = AgentCard(
            name="Test",
            url="https://example.com",
            version="1.0.0",
            capabilities=AgentCapabilities(streaming=True),
            skills=[AgentSkill(id="s1", name="S1")],
            provider=AgentProvider(organization="Org"),
        )
        d = card.model_dump(by_alias=True)
        assert d["capabilities"]["streaming"] is True

        card2 = AgentCard.model_validate(d)
        assert card2.name == "Test"
        assert card2.capabilities.streaming is True


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRA FIELDS
# ═══════════════════════════════════════════════════════════════════════════════


class TestExtraFields:
    """Models should allow extra fields for forward compatibility."""

    def test_message_extra(self):
        data = {
            "role": "user",
            "messageId": "m1",
            "parts": [{"kind": "text", "text": "Hi"}],
            "futureField": "some value",  # Extra field
        }
        msg = Message.model_validate(data)
        assert msg.role == MessageRole.USER
        # Extra field should be preserved
        assert hasattr(msg, "futureField") or "futureField" in msg.model_extra

    def test_task_extra(self):
        data = {
            "id": "t1",
            "contextId": "c1",
            "status": {"state": "working"},
            "newFeature": {"enabled": True},  # Extra field
        }
        task = Task.model_validate(data)
        assert task.id == "t1"
