## ADDED Requirements

### Requirement: Knowledge Agent fetches web context using tools
The system SHALL provide a knowledge acquisition Agent with 3 tools from `langchain-tavily`: `tavily_search_basic` (lightweight search, 3 results, snippets only), `tavily_search_deep` (deep search, 5 results, full page content), and `tavily_extract` (URL content extraction). The Agent SHALL autonomously decide which tool(s) to call and what parameters to use based on the user's input.

#### Scenario: User inputs a keyword/topic for simple knowledge
- **WHEN** user inputs a simple or commonly known topic like "什么是 HTTP"
- **THEN** the Agent calls `tavily_search_basic` with an appropriate query (returning up to 3 results with content snippets) and returns a knowledge summary

#### Scenario: User inputs a keyword/topic for complex knowledge
- **WHEN** user inputs a complex, specialized, or professional topic like "Harness Engineering"
- **THEN** the Agent calls `tavily_search_deep` with an appropriate query (returning up to 5 results with full page content) and returns a knowledge summary

#### Scenario: User inputs a URL
- **WHEN** user inputs a URL like "https://example.com/article"
- **THEN** the Agent calls `tavily_extract` with the URL to retrieve the full page content, and returns a knowledge summary based on the extracted content

#### Scenario: User inputs mixed content with URL and text
- **WHEN** user inputs text containing both a URL and descriptive text
- **THEN** the Agent MAY call both `tavily_extract` (for the URL) and `tavily_search_basic` or `tavily_search_deep` (for supplementary context), combining results into a unified knowledge summary

#### Scenario: Agent dynamically adjusts runtime parameters
- **WHEN** the Agent calls any search tool
- **THEN** the Agent MAY dynamically set runtime parameters including `search_depth`, `time_range`, `include_domains`, and `exclude_domains` based on the topic characteristics

#### Scenario: Agent adjusts for time-sensitive topics
- **WHEN** the user input mentions recent events or emerging technology
- **THEN** the Agent SHOULD set `time_range` to "week" or "month" to prioritize recent results

### Requirement: Knowledge Agent failure degrades gracefully
The system SHALL catch all exceptions from the knowledge Agent execution and continue with quiz generation without search context. The system SHALL log the failure at warning level.

#### Scenario: Agent execution timeout
- **WHEN** the Agent does not complete within 15 seconds
- **THEN** the system logs a warning and proceeds to generate quiz without search context

#### Scenario: Tavily API key invalid or missing
- **WHEN** the Tavily API key is not configured or is invalid
- **THEN** the system logs a warning and proceeds to generate quiz without search context

#### Scenario: Search disabled by configuration
- **WHEN** the `enable_web_search` config is set to `false`
- **THEN** the system skips the Agent step entirely and generates quiz using only the LLM's training data

### Requirement: Agent limits tool call count
The Agent SHALL be instructed via system prompt to call at most 2 tools per execution to prevent excessive API usage and latency.

#### Scenario: Agent stops after sufficient information
- **WHEN** the Agent has gathered enough information from 1-2 tool calls
- **THEN** the Agent stops calling tools and returns the knowledge summary

### Requirement: Knowledge summary is size-bounded
The knowledge summary output from the Agent SHALL be truncated to at most 3000 characters before being injected into the quiz generation prompt.

#### Scenario: Large URL content is truncated
- **WHEN** `TavilyExtract` returns page content exceeding 3000 characters
- **THEN** the system truncates the knowledge summary to 3000 characters

### Requirement: Quiz prompt includes search context
The system SHALL inject the Agent's knowledge summary into the quiz generation prompt as reference material. The prompt SHALL instruct the model to prioritize the reference material for accuracy while generating questions in its own words.

#### Scenario: Quiz generated with search context
- **WHEN** the Agent returns a non-empty knowledge summary
- **THEN** the quiz prompt includes the summary as "参考资料" section, and the generated questions reflect accurate, up-to-date information

#### Scenario: Quiz generated without search context
- **WHEN** the Agent returns empty results or is skipped
- **THEN** the quiz prompt omits the reference section and generates questions using only the LLM's training data, identical to current behavior

### Requirement: Search configuration is externalized
The system SHALL read search-related configuration from environment variables: `TAVILY_API_KEY`, `ENABLE_WEB_SEARCH` (default true).

#### Scenario: Default configuration
- **WHEN** no search-related environment variables are set except `TAVILY_API_KEY`
- **THEN** web search is enabled with Agent default parameters

#### Scenario: Search explicitly disabled
- **WHEN** `ENABLE_WEB_SEARCH` is set to `false`
- **THEN** the Agent step is completely skipped regardless of whether `TAVILY_API_KEY` is set

### Requirement: API contract unchanged
The `POST /api/v1/quiz/generate` endpoint SHALL maintain its existing request and response schema. The web search enhancement SHALL be transparent to the frontend.

#### Scenario: Request and response format unchanged
- **WHEN** a client sends the same request payload as before
- **THEN** the response structure remains identical, with the same fields and types
