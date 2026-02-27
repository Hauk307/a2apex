# A2A Protocol Specification Notes

## Overview
The Agent2Agent (A2A) Protocol is an open standard for communication between AI agents built by Google. It enables agents built on different frameworks to communicate and collaborate.

**Current Version:** 0.3.0 (Release Candidate v1.0)

## Core Concepts

### 1. A2A Client & Server
- **Client**: Application/agent that initiates requests
- **Server (Remote Agent)**: Exposes A2A-compliant HTTP endpoint

### 2. Agent Card
Self-describing JSON manifest served at `/.well-known/agent-card.json`

**Required Fields:**
- `protocolVersion` - A2A version (e.g., "0.3.0")
- `name` - Human-readable agent name
- `description` - What the agent does
- `url` - Primary endpoint URL
- `version` - Agent's own version
- `capabilities` - Optional features supported
- `defaultInputModes` - Supported input MIME types
- `defaultOutputModes` - Supported output MIME types
- `skills` - Array of agent capabilities

**Optional Fields:**
- `preferredTransport` - Default "JSONRPC", also "GRPC", "HTTP+JSON"
- `additionalInterfaces` - Other transport/URL combos
- `iconUrl` - Agent icon
- `provider` - Organization info
- `documentationUrl` - Docs link
- `securitySchemes` - Auth methods (OpenAPI 3.0 format)
- `security` - Security requirements
- `supportsAuthenticatedExtendedCard` - If true, extended card available after auth

### 3. AgentCapabilities Object
```json
{
  "streaming": true,           // SSE support
  "pushNotifications": true,   // Webhook support
  "stateTransitionHistory": true,
  "extensions": []
}
```

### 4. AgentSkill Object
```json
{
  "id": "unique-skill-id",
  "name": "Human readable name",
  "description": "What this skill does",
  "tags": ["category1", "category2"],
  "examples": ["Example prompt 1"],
  "inputModes": ["text/plain", "application/json"],
  "outputModes": ["text/plain", "application/json"],
  "security": [{"oauth": ["read"]}]
}
```

## Transport Protocols

### JSON-RPC 2.0 (Primary)
- Content-Type: `application/json`
- Method pattern: `{category}/{action}` (e.g., "message/send")

### gRPC
- Protocol Buffers v3
- TLS required

### HTTP+JSON/REST
- RESTful URLs: `/v1/{resource}[/{id}][:{action}]`
- Standard HTTP verbs

## Core Operations

| Operation | JSON-RPC Method | REST Endpoint | Description |
|-----------|----------------|---------------|-------------|
| Send Message | `message/send` | POST /v1/message:send | Send message to agent |
| Stream Message | `message/stream` | POST /v1/message:stream | Send with streaming |
| Get Task | `tasks/get` | GET /v1/tasks/{id} | Get task status |
| List Tasks | `tasks/list` | GET /v1/tasks | List all tasks |
| Cancel Task | `tasks/cancel` | POST /v1/tasks/{id}:cancel | Cancel a task |
| Subscribe to Task | `tasks/resubscribe` | POST /v1/tasks/{id}:subscribe | Resume streaming |
| Get Extended Card | `agent/getAuthenticatedExtendedCard` | GET /v1/card | Authenticated card |

## Task Lifecycle

### Task States (TaskState enum)
- `submitted` - Task received, not yet started
- `working` - Agent is processing
- `input-required` - Agent needs more info from client
- `auth-required` - Agent needs authentication
- `completed` - Successfully finished
- `failed` - Task failed
- `canceled` - Task was canceled
- `rejected` - Task was rejected

### State Transitions
```
submitted → working → completed
                   → failed
                   → input-required → working
                   → auth-required → working
         → canceled (from any non-terminal state)
         → rejected
```

## Message Structure

### Message Object
```json
{
  "role": "user" | "agent",
  "parts": [Part],
  "messageId": "unique-id",
  "contextId": "optional-context",
  "taskId": "optional-task-reference",
  "referenceTaskIds": ["related-task-ids"],
  "metadata": {}
}
```

### Part Types

#### TextPart
```json
{
  "kind": "text",
  "text": "The content",
  "metadata": {}
}
```

#### FilePart
```json
{
  "kind": "file",
  "file": {
    "name": "filename.pdf",
    "mimeType": "application/pdf",
    "uri": "https://...",  // OR
    "bytes": "base64..."
  },
  "metadata": {}
}
```

#### DataPart
```json
{
  "kind": "data",
  "data": { "key": "value" },
  "metadata": {}
}
```

## Task Object

```json
{
  "id": "task-unique-id",
  "contextId": "context-id",
  "status": {
    "state": "working",
    "message": Message,
    "timestamp": "2024-01-01T00:00:00Z"
  },
  "artifacts": [Artifact],
  "history": [Message],
  "metadata": {}
}
```

## Artifact Object

```json
{
  "artifactId": "unique-id",
  "name": "output-name",
  "description": "What this artifact is",
  "parts": [Part],
  "index": 0,
  "append": false,
  "lastChunk": true,
  "metadata": {}
}
```

## Streaming Events

### TaskStatusUpdateEvent
```json
{
  "taskId": "task-id",
  "contextId": "context-id",
  "status": TaskStatus,
  "final": false
}
```

### TaskArtifactUpdateEvent
```json
{
  "taskId": "task-id",
  "contextId": "context-id",
  "artifact": Artifact
}
```

## Push Notifications

### PushNotificationConfig
```json
{
  "id": "config-id",
  "url": "https://client-webhook.com/callback",
  "token": "bearer-token-for-verification",
  "authentication": {
    "schemes": ["bearer"]
  }
}
```

## Error Codes

| Error | Description |
|-------|-------------|
| TaskNotFoundError | Task ID doesn't exist |
| TaskNotCancelableError | Task already in terminal state |
| PushNotificationNotSupportedError | Agent doesn't support push |
| UnsupportedOperationError | Operation not supported |
| ContentTypeNotSupportedError | MIME type not supported |
| InvalidAgentResponseError | Response doesn't conform to spec |
| ExtensionSupportRequiredError | Required extension not declared |
| VersionNotSupportedError | A2A version not supported |

## Security

### Authentication Methods (OpenAPI 3.0)
- API Key (`apiKey` in header/query/cookie)
- HTTP Auth (Basic, Bearer)
- OAuth 2.0 (various flows)
- OpenID Connect
- Mutual TLS

### Headers
- `Authorization: Bearer <token>`
- `X-API-Key: <key>`
- `A2A-Version: 0.3` (protocol version)
- `A2A-Extensions: <comma-separated URIs>`

## Validation Checklist for A2Apex

### Agent Card Validation
- [ ] Valid JSON
- [ ] Required fields present (name, description, url, version, capabilities, skills, defaultInputModes, defaultOutputModes)
- [ ] protocolVersion is valid A2A version
- [ ] url is valid HTTPS URL (in production)
- [ ] At least one skill defined
- [ ] Skills have required fields (id, name, description, tags)
- [ ] MIME types are valid
- [ ] Security schemes follow OpenAPI 3.0 format
- [ ] preferredTransport matches url capability

### Endpoint Validation
- [ ] Agent Card accessible at /.well-known/agent-card.json
- [ ] Correct Content-Type: application/json
- [ ] Responds to message/send
- [ ] Returns valid Task or Message objects
- [ ] Handles errors with proper error codes

### Task Lifecycle Validation
- [ ] Tasks have valid IDs
- [ ] State transitions are valid
- [ ] Terminal states don't accept new messages
- [ ] History is properly maintained
- [ ] Timestamps are ISO 8601 format

### Protocol Compliance
- [ ] JSON-RPC 2.0 format correct
- [ ] Proper error response structure
- [ ] Streaming uses SSE correctly (if supported)
- [ ] Push notifications work (if supported)
