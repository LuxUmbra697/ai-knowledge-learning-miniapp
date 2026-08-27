## ADDED Requirements

### Requirement: Quiz generation accepts an optional knowledge base document reference
The system SHALL accept an optional `doc_id` field on the quiz generation request. When `doc_id` is omitted, the system SHALL behave identically to the existing quiz generation flow (model knowledge + optional web search), with no change to request/response schema or behavior.

#### Scenario: Request without doc_id behaves unchanged
- **WHEN** a client submits a quiz generation request without a `doc_id`
- **THEN** the system generates the quiz using the existing web-search-augmented flow exactly as before this change

#### Scenario: Request with doc_id uses the referenced document
- **WHEN** a client submits a quiz generation request with a `doc_id` referencing a document owned by the requesting user with status `ready`
- **THEN** the system generates the quiz using knowledge retrieved from that document (optionally supplemented by web search)

#### Scenario: doc_id references a document not owned by the user
- **WHEN** a client submits a `doc_id` that does not belong to the requesting user (or does not exist)
- **THEN** the system rejects the request with a clear error and does not create a quiz task

#### Scenario: doc_id references a document that is not ready
- **WHEN** a client submits a `doc_id` whose document status is `processing` or `failed`
- **THEN** the system rejects the request with a clear error indicating the document is not ready for use

### Requirement: Agentic retrieval chooses between knowledge base and web search
When a valid `doc_id` is provided, the system SHALL use an agent with access to a knowledge-base retrieval tool (scoped to the requesting user and the specified document) and, when web search is enabled and configured, the existing web search tools. The agent SHALL autonomously decide which tool(s) to invoke to produce a knowledge summary for quiz generation.

#### Scenario: Agent retrieves from knowledge base only
- **WHEN** the knowledge base retrieval tool returns sufficient relevant content for the topic
- **THEN** the agent produces a knowledge summary based on the retrieved document chunks without necessarily calling web search tools

#### Scenario: Agent supplements with web search
- **WHEN** the knowledge base retrieval tool returns insufficient or no relevant content and web search is enabled
- **THEN** the agent MAY additionally call web search tools to supplement the knowledge summary

#### Scenario: Web search unavailable, knowledge base still used
- **WHEN** web search is disabled or not configured but a valid `doc_id` is provided
- **THEN** the agent uses only the knowledge-base retrieval tool to produce the knowledge summary

#### Scenario: Retrieval agent failure degrades gracefully
- **WHEN** the retrieval agent raises an exception or times out
- **THEN** the system logs a warning and proceeds to generate the quiz without a knowledge summary, rather than failing the entire request

### Requirement: Knowledge base retrieval is scoped and isolated per user and document
The knowledge-base retrieval tool SHALL only search vectors belonging to the requesting user and the specified `doc_id`. It SHALL NOT return content from other users' documents or the same user's other documents.

#### Scenario: Retrieval scoped to the specified document
- **WHEN** the agent invokes the knowledge-base retrieval tool with a query
- **THEN** returned results only include chunks whose metadata matches the requesting user and the specified `doc_id`
