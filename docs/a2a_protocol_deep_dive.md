# A2A Protocol Deep Dive — The Definitive Reference for A2Apex

*Research compiled for building A2Apex: "Postman for AI Agents"*  
*Protocol Version: 0.3.0 (Release Candidate v1.0)*  
*Last Updated: 2026-02-26*

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Protocol Architecture](#protocol-architecture)
3. [Core Data Model](#core-data-model)
4. [Operations & Methods](#operations--methods)
5. [Protocol Bindings](#protocol-bindings)
6. [Agent Card Specification](#agent-card-specification)
7. [Task Lifecycle & State Machine](#task-lifecycle--state-machine)
8. [Streaming & Push Notifications](#streaming--push-notifications)
9. [Authentication & Security](#authentication--security)
10. [Error Handling](#error-handling)
11. [Test Scenarios for A2Apex](#test-scenarios-for-a2apex)
12. [Common Developer Mistakes](#common-developer-mistakes)
13. [Spec Gaps & Ambiguities](#spec-gaps--ambiguities)
14. [Comparison with Existing MVP](#comparison-with-existing-mvp)
15. [A2Apex Feature Roadmap](#a2apex-feature-roadmap)

---

## Executive Summary

The Agent2Agent (A2A) Protocol is an open standard enabling communication and interoperability between independent AI agent systems. It uses JSON-RPC 2.0 over HTTP(S) as the primary binding, with support for gRPC and HTTP+JSON/REST alternatives.

**Key characteristics:**
- **Async-first**: Designed for long-running tasks and human-in-the-loop scenarios
- **Opaque execution**: Agents collaborate without exposing internal state
- **Enterprise-ready**: Built on standard web security practices (OAuth 2.0, API keys, mTLS)
- **Modality-agnostic**: Supports text, files, structured data

**A2Apex Opportunity**: The spec is complex (180+ types in the Python SDK). Developers WILL make mistakes. A2Apex should be the authoritative testing/certification tool that helps them get it right.

---

## Protocol Architecture

### Three-Layer Model

```
┌─────────────────────────────────────────────────────┐
│  Layer 3: Protocol Bindings                         │
│  JSON-RPC 2.0 | gRPC | HTTP+JSON/REST | Custom      │
├─────────────────────────────────────────────────────┤
│  Layer 2: Abstract Operations                       │
│  SendMessage | GetTask | CancelTask | Subscribe     │
├─────────────────────────────────────────────────────┤
│  Layer 1: Canonical Data Model                      │
│  Task | Message | AgentCard | Part | Artifact       │
└─────────────────────────────────────────────────────┘
```

### Actors

| Actor | Description |
|-------|-------------|
| **A2A Client** | Application/agent that initiates requests |
| **A2A Server (Remote Agent)** | Agent exposing A2A-compliant endpoint |
| **User** | End user (human or automated service) |

---

## Core Data Model

### Message Object

The fundamental communication unit between client and agent.

```json
{
  "role": "user" | "agent",
  "messageId": "uuid-string",        // REQUIRED - unique identifier
  "parts": [Part],                   // REQUIRED - content array
  "contextId": "string",             // Optional - conversation grouping
  "taskId": "string",                // Optional - reference to existing task
  "referenceTaskIds": ["string"],    // Optional - related task references
  "extensions": ["uri"],             // Optional - extension URIs
  "metadata": {},                    // Optional - key-value map
  "kind": "message"                  // Discriminator (always "message")
}
```

**Testing Points:**
- [ ] `role` must be exactly "user" or "agent"
- [ ] `messageId` must be present and unique
- [ ] `parts` array must not be empty
- [ ] `contextId` and `taskId` must not conflict (if both provided, contextId must match task's context)

### Part Types (Discriminated Union)

Parts are the smallest content units. A Part must contain exactly ONE of:

#### TextPart
```json
{
  "kind": "text",
  "text": "string content",
  "metadata": {}
}
```

#### FilePart
```json
{
  "kind": "file",
  "file": {
    // FileWithUri
    "uri": "https://...",
    "name": "filename.pdf",
    "mimeType": "application/pdf"
  } | {
    // FileWithBytes
    "bytes": "base64-encoded-data",
    "name": "filename.pdf",
    "mimeType": "application/pdf"
  },
  "metadata": {}
}
```

#### DataPart
```json
{
  "kind": "data",
  "data": { "key": "value" },  // Structured JSON
  "metadata": {}
}
```

**Testing Points:**
- [ ] `kind` field must be present and valid
- [ ] Only one content field per Part type
- [ ] FilePart must have either `uri` OR `bytes`, not both
- [ ] Base64 encoding must be valid in FileWithBytes
- [ ] MIME types should be valid format

### Task Object

The fundamental unit of work with lifecycle state.

```json
{
  "id": "task-uuid",              // REQUIRED - server-generated
  "contextId": "context-uuid",    // REQUIRED - conversation grouping
  "status": {
    "state": "TaskState",         // REQUIRED - lifecycle state
    "message": Message,           // Optional - status details
    "timestamp": "ISO8601"        // Optional - when status changed
  },
  "artifacts": [Artifact],        // Optional - generated outputs
  "history": [Message],           // Optional - conversation history
  "metadata": {},
  "kind": "task"                  // Discriminator
}
```

### Artifact Object

Tangible outputs generated by tasks.

```json
{
  "artifactId": "uuid",           // REQUIRED - unique within task
  "name": "human-readable-name",  // Optional
  "description": "what this is",  // Optional
  "parts": [Part],                // REQUIRED - content
  "extensions": ["uri"],
  "metadata": {}
}
```

**Streaming Artifact Fields:**
- `append: boolean` — Append to previous artifact with same ID
- `lastChunk: boolean` — Final chunk indicator
- `index: number` — Ordering for reassembly

---

## Operations & Methods

### Core Operations Reference

| Operation | JSON-RPC Method | gRPC RPC | REST Endpoint | Description |
|-----------|-----------------|----------|---------------|-------------|
| Send Message | `message/send` | `SendMessage` | `POST /v1/message:send` | Primary interaction |
| Stream Message | `message/stream` | `SendStreamingMessage` | `POST /v1/message:stream` | Real-time streaming |
| Get Task | `tasks/get` | `GetTask` | `GET /v1/tasks/{id}` | Retrieve task state |
| List Tasks | `tasks/list` | `ListTasks` | `GET /v1/tasks` | List with pagination |
| Cancel Task | `tasks/cancel` | `CancelTask` | `POST /v1/tasks/{id}:cancel` | Request cancellation |
| Subscribe to Task | `tasks/resubscribe` | `SubscribeToTask` | `POST /v1/tasks/{id}:subscribe` | Resume streaming |
| Get Extended Card | `agent/getAuthenticatedExtendedCard` | `GetAuthenticatedExtendedCard` | `GET /v1/card` | Authenticated card |
| Create Push Config | `tasks/pushNotificationConfig/set` | `CreateTaskPushNotificationConfig` | `POST /v1/tasks/{id}/pushNotificationConfigs` | Register webhook |
| Get Push Config | `tasks/pushNotificationConfig/get` | `GetTaskPushNotificationConfig` | `GET /v1/tasks/{id}/pushNotificationConfigs/{configId}` | Get webhook config |
| List Push Configs | `tasks/pushNotificationConfig/list` | `ListTaskPushNotificationConfigs` | `GET /v1/tasks/{id}/pushNotificationConfigs` | List webhooks |
| Delete Push Config | `tasks/pushNotificationConfig/delete` | `DeleteTaskPushNotificationConfig` | `DELETE /v1/tasks/{id}/pushNotificationConfigs/{configId}` | Remove webhook |

### SendMessageRequest Structure

```json
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "method": "message/send",
  "params": {
    "message": Message,
    "configuration": {
      "acceptedOutputModes": ["text/plain", "application/json"],
      "historyLength": 10,
      "blocking": false,
      "pushNotificationConfig": PushNotificationConfig
    },
    "metadata": {}
  }
}
```

**Configuration Fields:**
- `acceptedOutputModes` — MIME types client accepts
- `historyLength` — Max messages in response (0 = none, unset = no limit)
- `blocking` — Wait for terminal/interrupted state before responding
- `pushNotificationConfig` — Webhook for async updates

### Response Types

Operations return either:
1. **Task** — For stateful, trackable work
2. **Message** — For immediate, stateless responses

```json
// Task response
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "result": {
    "task": Task
  }
}

// Message response  
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "result": {
    "message": Message
  }
}
```

---

## Protocol Bindings

### JSON-RPC 2.0 (Primary)

**Endpoint:** Single URL (from AgentCard.url)  
**Content-Type:** `application/json`  
**Streaming:** Server-Sent Events (SSE) with `text/event-stream`

```http
POST /a2a HTTP/1.1
Host: agent.example.com
Content-Type: application/json
Authorization: Bearer <token>
A2A-Version: 0.3

{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "message/send",
  "params": {...}
}
```

**SSE Format:**
```
event: message
data: {"jsonrpc":"2.0","id":1,"result":{"task":{...}}}

event: message
data: {"jsonrpc":"2.0","id":1,"result":{"statusUpdate":{...}}}
```

### gRPC

**Service Definition:** `a2a.AgentService`  
**Messages:** Protocol Buffers (a2a.proto is normative source)

### HTTP+JSON/REST

**URL Pattern:** `/v1/{resource}[/{id}][:{action}]`  
**Methods:** Standard HTTP verbs (GET, POST, DELETE)

---

## Agent Card Specification

The Agent Card is a JSON document at `/.well-known/agent-card.json`.

### Complete AgentCard Schema

```json
{
  // REQUIRED FIELDS
  "name": "Recipe Agent",
  "description": "Agent that helps users with recipes and cooking.",
  "url": "https://api.example.com/a2a/v1",
  "version": "1.0.0",
  "capabilities": AgentCapabilities,
  "defaultInputModes": ["text/plain", "application/json"],
  "defaultOutputModes": ["text/plain", "application/json"],
  "skills": [AgentSkill],
  
  // OPTIONAL FIELDS
  "protocolVersion": "0.3.0",
  "preferredTransport": "JSONRPC" | "GRPC" | "HTTP+JSON",
  "additionalInterfaces": [AgentInterface],
  "provider": {
    "organization": "Acme Corp",
    "url": "https://acme.com"
  },
  "iconUrl": "https://...",
  "documentationUrl": "https://...",
  "supportsAuthenticatedExtendedCard": true,
  "securitySchemes": { "schemeName": SecurityScheme },
  "security": [{ "schemeName": ["scope1"] }],
  "signatures": [AgentCardSignature]
}
```

### AgentCapabilities

```json
{
  "streaming": true,              // SSE support
  "pushNotifications": true,      // Webhook support
  "stateTransitionHistory": true, // History tracking
  "extensions": [AgentExtension]  // Protocol extensions
}
```

### AgentSkill

```json
{
  "id": "recipe-search",          // REQUIRED - unique identifier
  "name": "Recipe Search",        // REQUIRED - human readable
  "description": "Search for...", // REQUIRED - detailed description
  "tags": ["cooking", "recipes"], // REQUIRED - categorization
  "examples": ["Find a recipe for..."],  // Optional
  "inputModes": ["text/plain"],   // Optional - overrides defaults
  "outputModes": ["application/json"],
  "security": [{"oauth": ["recipe.read"]}]  // Optional - skill-specific auth
}
```

### Security Schemes (OpenAPI 3.0 Compatible)

#### API Key
```json
{
  "type": "apiKey",
  "name": "X-API-Key",
  "in": "header" | "query" | "cookie",
  "description": "API key authentication"
}
```

#### HTTP Auth (Bearer)
```json
{
  "type": "http",
  "scheme": "Bearer",
  "bearerFormat": "JWT",
  "description": "JWT authentication"
}
```

#### OAuth 2.0
```json
{
  "type": "oauth2",
  "flows": {
    "authorizationCode": {
      "authorizationUrl": "https://...",
      "tokenUrl": "https://...",
      "scopes": { "read": "Read access" }
    },
    "clientCredentials": {...},
    "implicit": {...},
    "password": {...}
  },
  "oauth2MetadataUrl": "https://..."
}
```

#### OpenID Connect
```json
{
  "type": "openIdConnect",
  "openIdConnectUrl": "https://.../.well-known/openid-configuration"
}
```

#### Mutual TLS
```json
{
  "type": "mutualTLS",
  "description": "Client certificate required"
}
```

---

## Task Lifecycle & State Machine

### Task States (TaskState enum)

| State | Type | Description |
|-------|------|-------------|
| `submitted` | Initial | Task received, not yet processing |
| `working` | In-progress | Agent actively processing |
| `input-required` | Interrupted | Agent needs more input |
| `auth-required` | Interrupted | Agent needs authentication |
| `completed` | Terminal | Successfully finished |
| `failed` | Terminal | Task failed with error |
| `canceled` | Terminal | Task was canceled |
| `rejected` | Terminal | Task was rejected (won't process) |

### State Transition Diagram

```
                    ┌──────────────┐
                    │  submitted   │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
          ┌────────►│   working    │◄─────────┐
          │         └──────┬───────┘          │
          │                │                  │
          │         ┌──────┴──────┐           │
          │         ▼             ▼           │
    ┌─────┴────┐  ┌─────┐   ┌─────────────┐   │
    │ input-   │  │auth-│   │  Terminal   │   │
    │ required │  │req'd│   │  States     │   │
    └─────┬────┘  └──┬──┘   │             │   │
          │         │       │ completed   │   │
          └─────────┼───────► failed      │   │
                    │       │ canceled    │   │
                    │       │ rejected    │   │
                    │       └─────────────┘   │
                    │                         │
                    └─────────────────────────┘
                    (after auth provided)
```

### Task Immutability Rules

1. **Terminal states are final** — Cannot transition out
2. **No task restart** — Follow-ups create NEW tasks in same context
3. **Messages to terminal tasks** — MUST return `UnsupportedOperationError`

### Context vs Task Semantics

| Concept | Generated By | Purpose |
|---------|--------------|---------|
| `contextId` | Server | Groups related tasks/messages (conversation) |
| `taskId` | Server | Identifies single unit of work |

**Rules:**
- Server MUST generate `contextId` if not provided
- Server MUST generate `taskId` for new tasks
- Client CANNOT provide `taskId` for new tasks
- If `taskId` provided, server MUST validate it exists
- If both provided, `contextId` must match task's context

---

## Streaming & Push Notifications

### Streaming (SSE)

**Capability Check:** `AgentCard.capabilities.streaming === true`

**Operations:**
1. `message/stream` — Send message + subscribe to updates
2. `tasks/resubscribe` — Reconnect to existing task stream

**Stream Response Wrapper:**
```json
{
  "task": Task,              // OneOf
  "message": Message,        // OneOf
  "statusUpdate": TaskStatusUpdateEvent,    // OneOf
  "artifactUpdate": TaskArtifactUpdateEvent // OneOf
}
```

**Stream Lifecycle:**
1. First event: `Task` or `Message`
2. Subsequent events: `TaskStatusUpdateEvent` and/or `TaskArtifactUpdateEvent`
3. Stream closes when task reaches terminal state

### TaskStatusUpdateEvent

```json
{
  "kind": "status-update",
  "taskId": "uuid",
  "contextId": "uuid",
  "status": TaskStatus,
  "final": boolean,  // True if stream will close
  "metadata": {}
}
```

### TaskArtifactUpdateEvent

```json
{
  "kind": "artifact-update",
  "taskId": "uuid",
  "contextId": "uuid",
  "artifact": Artifact,
  "append": boolean,     // Append to previous chunk
  "lastChunk": boolean,  // Final chunk of this artifact
  "metadata": {}
}
```

### Push Notifications (Webhooks)

**Capability Check:** `AgentCard.capabilities.pushNotifications === true`

**PushNotificationConfig:**
```json
{
  "id": "config-uuid",     // Client-provided
  "url": "https://client-webhook.com/callback",  // REQUIRED
  "token": "verification-token",  // Optional
  "authentication": {
    "schemes": ["Bearer"],
    "credentials": "optional-token"
  }
}
```

**Webhook Payload:** Same as stream response (`StreamResponse` wrapper)

**Security Requirements:**
- Server MUST validate webhook URLs (prevent SSRF)
- Server MUST authenticate to webhook per config
- Client MUST verify incoming notifications
- Use timestamps/nonces to prevent replay attacks

---

## Authentication & Security

### HTTP Headers

| Header | Purpose |
|--------|---------|
| `Authorization` | Bearer token, Basic auth |
| `X-API-Key` | API key (or custom header name) |
| `A2A-Version` | Protocol version (e.g., "0.3") |
| `A2A-Extensions` | Comma-separated extension URIs |

### Authentication Flow

1. Client reads `AgentCard.securitySchemes` and `AgentCard.security`
2. Client obtains credentials out-of-band (OAuth flow, API key registration)
3. Client includes credentials in HTTP headers
4. Server validates on every request
5. Return 401 Unauthorized or 403 Forbidden on failure

### In-Task Authentication (`auth-required` state)

When agent needs additional credentials mid-task:
1. Agent transitions task to `auth-required` state
2. Status message contains authentication requirements
3. Client obtains credentials out-of-band
4. Client sends new message with same `taskId` (credentials in headers)
5. Agent transitions back to `working`

### Enterprise Requirements

- **TLS 1.2+** mandatory in production
- **Certificate validation** required
- Implement **rate limiting** and **quotas**
- Support **distributed tracing** (OpenTelemetry, W3C Trace Context)
- **Audit logging** for compliance

---

## Error Handling

### JSON-RPC Error Codes

| Code | Name | Description |
|------|------|-------------|
| -32700 | `JSONParseError` | Invalid JSON |
| -32600 | `InvalidRequestError` | Not valid Request object |
| -32601 | `MethodNotFoundError` | Method doesn't exist |
| -32602 | `InvalidParamsError` | Invalid method parameters |
| -32603 | `InternalError` | Internal server error |

### A2A-Specific Error Codes

| Code | Name | Trigger |
|------|------|---------|
| -32001 | `TaskNotFoundError` | Task ID doesn't exist |
| -32002 | `TaskNotCancelableError` | Task in terminal state |
| -32003 | `PushNotificationNotSupportedError` | Capability not enabled |
| -32004 | `UnsupportedOperationError` | Operation not supported |
| -32005 | `ContentTypeNotSupportedError` | MIME type not supported |
| -32006 | `InvalidAgentResponseError` | Response doesn't conform to spec |
| -32007 | `AuthenticatedExtendedCardNotConfiguredError` | Extended card not configured |
| -32008 | `ExtensionSupportRequiredError` | Required extension not declared |
| -32009 | `VersionNotSupportedError` | Protocol version not supported |

### Error Response Format

```json
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "error": {
    "code": -32001,
    "message": "Task not found",
    "data": {
      "taskId": "unknown-task-id",
      "suggestion": "Verify the task ID and try again"
    }
  }
}
```

---

## Test Scenarios for A2Apex

### 1. Agent Card Validation

#### Required Field Tests
- [ ] `name` present and non-empty string
- [ ] `description` present and non-empty string
- [ ] `url` present and valid HTTPS URL (in production)
- [ ] `version` present and valid semver format
- [ ] `capabilities` object present
- [ ] `defaultInputModes` array with valid MIME types
- [ ] `defaultOutputModes` array with valid MIME types
- [ ] `skills` array with at least one skill

#### Skill Validation
- [ ] Each skill has `id`, `name`, `description`, `tags`
- [ ] Skill IDs are unique
- [ ] MIME types are valid format
- [ ] Examples array contains strings (if present)

#### Security Scheme Validation
- [ ] Schemes follow OpenAPI 3.0 format
- [ ] Referenced schemes in `security` exist in `securitySchemes`
- [ ] OAuth flows have required URLs
- [ ] API key schemes have valid `in` values

#### Capability Consistency
- [ ] If `streaming: true`, endpoint supports SSE
- [ ] If `pushNotifications: true`, push config methods work
- [ ] If `supportsAuthenticatedExtendedCard: true`, extended card endpoint exists

### 2. Endpoint Availability

- [ ] Agent Card accessible at `/.well-known/agent-card.json`
- [ ] Correct Content-Type header (`application/json`)
- [ ] Primary URL responds to requests
- [ ] All `additionalInterfaces` URLs are reachable

### 3. Task Lifecycle Tests

#### Happy Path
- [ ] Send message → Task created with `submitted` or `working` state
- [ ] Task progresses to `completed` with artifacts
- [ ] Get task returns correct state and artifacts
- [ ] History length respected

#### Multi-turn Conversations
- [ ] Context continuity with same `contextId`
- [ ] Task refinement with `referenceTaskIds`
- [ ] New tasks in same context work correctly
- [ ] Input-required → client response → working transition

#### Error Paths
- [ ] Invalid task ID → `TaskNotFoundError`
- [ ] Message to completed task → `UnsupportedOperationError`
- [ ] Cancel already-completed → `TaskNotCancelableError`
- [ ] Mismatched contextId/taskId → Validation error

### 4. Streaming Tests

- [ ] SSE connection established correctly
- [ ] First event is Task or Message
- [ ] Events ordered correctly
- [ ] Stream closes on terminal state
- [ ] Resubscription works for active tasks
- [ ] Resubscription fails for terminal tasks
- [ ] Artifact chunking (`append`, `lastChunk`) works

### 5. Push Notification Tests

- [ ] Config creation returns config with ID
- [ ] Webhook receives events
- [ ] Authentication to webhook works
- [ ] Token validation works
- [ ] List configs returns all configs
- [ ] Delete config stops notifications

### 6. Authentication Tests

- [ ] Unauthenticated request returns 401
- [ ] Invalid credentials return 401
- [ ] Insufficient scopes return 403
- [ ] Valid credentials allow access
- [ ] In-task auth flow works

### 7. Protocol Compliance

- [ ] JSON-RPC 2.0 format correct (jsonrpc, id, method, params)
- [ ] Request ID echoed in response
- [ ] Null result for void operations
- [ ] Error format includes code and message

### 8. Content Type Tests

- [ ] Unsupported input type → `ContentTypeNotSupportedError`
- [ ] Unsupported output type handled gracefully
- [ ] File parts with invalid base64 rejected
- [ ] Large files handled (or rejected with clear error)

---

## Common Developer Mistakes

### Agent Card Mistakes

1. **Missing required fields** — Especially `skills` array
2. **Invalid MIME types** — Using made-up types like "json" instead of "application/json"
3. **HTTP URLs in production** — Must be HTTPS
4. **Claiming capabilities not implemented** — Say `streaming: true` but don't support SSE
5. **Invalid security scheme format** — Not following OpenAPI 3.0 spec

### Task Handling Mistakes

1. **Not generating unique IDs** — Collisions cause chaos
2. **Accepting messages to terminal tasks** — Must reject with error
3. **Not preserving context** — Breaking conversation continuity
4. **Invalid state transitions** — Going from `completed` to `working`
5. **Missing timestamps** — Required for status objects

### Protocol Mistakes

1. **Wrong JSON-RPC format** — Missing `jsonrpc: "2.0"` or `id`
2. **Wrong method names** — Case-sensitive! `message/send` not `Message/Send`
3. **Streaming without SSE** — Must use proper `text/event-stream` format
4. **Not handling errors** — Silent failures instead of proper error responses
5. **Missing A2A-Version header** — Required for version negotiation

### Security Mistakes

1. **Secrets in Agent Card** — Never embed credentials
2. **Not validating webhook URLs** — SSRF vulnerability
3. **HTTP in production** — Must use TLS
4. **No authentication on extended card** — Sensitive info exposure
5. **Replay-vulnerable webhooks** — Not checking timestamps/nonces

---

## Spec Gaps & Ambiguities

### 1. Agent Card Discovery

**Gap:** No standard registry API defined.

**Ambiguity:** How do clients discover agents beyond well-known URI?

**A2Apex Opportunity:** Provide registry mock/testing for catalog-based discovery.

### 2. Rate Limiting

**Gap:** No standard rate limiting headers or behavior defined.

**A2Apex Opportunity:** Test how agents handle rate limiting, provide guidelines.

### 3. Artifact Size Limits

**Gap:** No maximum size specified for artifacts or file parts.

**A2Apex Opportunity:** Test with various sizes, document practical limits.

### 4. Context Expiration

**Gap:** "Agents MAY implement context expiration or cleanup policies and SHOULD document any such policies" — but no standard format.

**A2Apex Opportunity:** Test context expiration behavior, help document policies.

### 5. Pagination Limits

**Gap:** ListTasks says max 100 per page, but no guidance on cursor lifetime.

**A2Apex Opportunity:** Test pagination edge cases.

### 6. Webhook Retry Policy

**Gap:** No standard retry behavior for failed webhook deliveries.

**A2Apex Opportunity:** Test webhook reliability, provide retry recommendations.

### 7. Multi-Transport Consistency

**Gap:** If agent exposes JSONRPC + gRPC + REST, should all return identical results?

**A2Apex Opportunity:** Cross-transport consistency testing.

### 8. Version Negotiation

**Gap:** Client sends `A2A-Version` header, but what if server supports multiple versions?

**A2Apex Opportunity:** Test version compatibility, provide guidance.

---

## Comparison with Existing MVP

### What Our MVP Already Covers

Based on `a2apex/docs/a2a_spec_notes.md` and `README.md`:

| Feature | Status | Notes |
|---------|--------|-------|
| Agent Card JSON validation | ✅ Basic | Checks required fields |
| Agent Card fetch from URL | ✅ | Via `/.well-known/agent-card.json` |
| Task lifecycle states | ✅ Documented | Notes exist but unclear if tested |
| Protocol compliance checklist | ✅ Checklist | In spec notes, not implemented |
| Web UI | ✅ Placeholder | Basic structure exists |

### What's Missing from MVP

| Feature | Priority | Effort |
|---------|----------|--------|
| **Full schema validation** (all 180+ types) | HIGH | Medium |
| **Live endpoint testing** (actually call agent) | HIGH | Medium |
| **Streaming (SSE) testing** | HIGH | High |
| **Push notification testing** | MEDIUM | High |
| **Authentication testing** | MEDIUM | Medium |
| **Multi-transport testing** | LOW | High |
| **Error response validation** | HIGH | Low |
| **State machine validation** | HIGH | Medium |
| **Performance/load testing** | LOW | Medium |
| **Certification report generation** | MEDIUM | Medium |

### Competitor Analysis: a2a-inspector

The official `a2a-inspector` tool provides:
- Agent Card fetching and display
- Basic spec compliance checks
- Live chat interface
- Debug console (raw JSON-RPC)

**A2Apex Differentiation:**
1. **Comprehensive validation** — Not just "does it work" but "is it spec-compliant"
2. **Automated test suites** — Run full compliance tests
3. **Certification** — Generate compliance reports
4. **Developer guidance** — Explain what's wrong and how to fix it
5. **Test scenario library** — Pre-built tests for common patterns

---

## A2Apex Feature Roadmap

### Phase 1: Foundation (MVP Enhancement)

1. **Complete JSON Schema validation**
   - Generate from `a2a.proto` or Python SDK types
   - Validate all object types, not just AgentCard

2. **Agent Card deep validation**
   - Cross-reference capabilities with actual endpoint support
   - Security scheme format validation
   - Skill completeness checks

3. **Basic endpoint testing**
   - Send simple message/send
   - Verify response format
   - Check error handling

### Phase 2: Task Lifecycle Testing

1. **State machine validator**
   - Track state transitions
   - Flag invalid transitions
   - Test all state paths

2. **Multi-turn conversation testing**
   - Context preservation
   - Task refinement
   - Input-required flows

3. **Artifact validation**
   - Part type validation
   - Streaming artifact reassembly
   - Size/format checks

### Phase 3: Advanced Features

1. **Streaming (SSE) testing**
   - Connection establishment
   - Event ordering
   - Reconnection handling

2. **Push notification testing**
   - Webhook mock server
   - Authentication validation
   - Event delivery verification

3. **Authentication testing**
   - OAuth flow testing
   - API key validation
   - Scope verification

### Phase 4: Certification

1. **Compliance report generation**
   - PDF/HTML reports
   - Pass/fail scoring
   - Remediation guidance

2. **Certification badges**
   - "A2A Certified" levels
   - Automated re-certification

3. **Registry integration**
   - Publish verified agents
   - Query certified agents

---

## Appendix: JSON-RPC Method Reference

### message/send
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "message/send",
  "params": {
    "message": Message,
    "configuration": MessageSendConfiguration,
    "metadata": {}
  }
}
```

### message/stream
Same params as message/send, returns SSE stream.

### tasks/get
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tasks/get",
  "params": {
    "id": "task-uuid",
    "historyLength": 10,
    "metadata": {}
  }
}
```

### tasks/cancel
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tasks/cancel",
  "params": {
    "id": "task-uuid",
    "metadata": {}
  }
}
```

### tasks/resubscribe
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tasks/resubscribe",
  "params": {
    "id": "task-uuid",
    "metadata": {}
  }
}
```

### tasks/pushNotificationConfig/set
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tasks/pushNotificationConfig/set",
  "params": {
    "taskId": "task-uuid",
    "pushNotificationConfig": PushNotificationConfig
  }
}
```

### tasks/pushNotificationConfig/get
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tasks/pushNotificationConfig/get",
  "params": {
    "id": "task-uuid",
    "pushNotificationConfigId": "config-uuid",
    "metadata": {}
  }
}
```

### tasks/pushNotificationConfig/list
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tasks/pushNotificationConfig/list",
  "params": {
    "id": "task-uuid",
    "metadata": {}
  }
}
```

### tasks/pushNotificationConfig/delete
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tasks/pushNotificationConfig/delete",
  "params": {
    "id": "task-uuid",
    "pushNotificationConfigId": "config-uuid",
    "metadata": {}
  }
}
```

### agent/getAuthenticatedExtendedCard
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "agent/getAuthenticatedExtendedCard"
}
```

---

## Appendix: Python SDK Type Summary

From `a2a-python/src/a2a/types.py` (generated from proto):

**Core Types:** Task, Message, Artifact, Part, AgentCard, AgentSkill
**Part Types:** TextPart, FilePart, DataPart
**File Types:** FileWithUri, FileWithBytes
**Status Types:** TaskStatus, TaskState (enum)
**Event Types:** TaskStatusUpdateEvent, TaskArtifactUpdateEvent
**Config Types:** PushNotificationConfig, MessageSendConfiguration
**Security Types:** APIKeySecurityScheme, HTTPAuthSecurityScheme, OAuth2SecurityScheme, OpenIdConnectSecurityScheme, MutualTLSSecurityScheme
**Request Types:** SendMessageRequest, GetTaskRequest, CancelTaskRequest, etc.
**Error Types:** TaskNotFoundError, TaskNotCancelableError, etc.

**Total: ~180 distinct types**

---

*This document is the authoritative reference for building A2Apex. Keep it updated as the A2A spec evolves.*
