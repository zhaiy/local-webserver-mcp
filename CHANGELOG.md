# Changelog

## 0.2.0 - 2026-03-12

- Unified tool error handling with consistent success/error response envelopes.
- Reused module-level `httpx.AsyncClient` with connection pooling, retries, and graceful shutdown.
- Made `web_search` async via thread offloading to avoid event-loop blocking.
- Improved webpage extraction (DOM-order headings/paragraphs/lists/tables/code/quotes).
- Added structured logging, input validation, and configurable rate limiting.
- Added new tools: `web_search_and_extract`, `batch_http_request`, optional `screenshot_webpage`.
- Added environment-variable-driven proxy/user-agent/timeout configuration.
- Introduced Pydantic response models and expanded pytest-based mock test suite.
