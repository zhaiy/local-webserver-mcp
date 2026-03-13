from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_httpx_client() -> Iterator[dict[str, AsyncMock]]:
    # Mock safe_request in all tool modules where it's imported
    with patch("mcp_web_server.tools.http.safe_request", new_callable=AsyncMock) as mock_http:
        with patch("mcp_web_server.tools.extract.safe_request", new_callable=AsyncMock) as mock_extract:
            with patch("mcp_web_server.tools.search.safe_request", new_callable=AsyncMock) as mock_search:
                yield {
                    "request": mock_http,
                    "get": mock_http,
                    "http": mock_http,
                    "extract": mock_extract,
                    "search": mock_search,
                }


@pytest.fixture
def sample_html_page() -> str:
    return """
    <html>
      <head><title>Sample Page</title></head>
      <body>
        <main>
          <h1>Main Heading</h1>
          <p>First paragraph with meaningful content.</p>
          <h2>Sub Heading</h2>
          <p>Second paragraph content appears here.</p>
          <ul><li>Item 1</li><li>Item 2</li></ul>
          <blockquote>Important quote</blockquote>
          <table><tr><th>K</th><th>V</th></tr><tr><td>a</td><td>1</td></tr></table>
          <pre><code>print("hello")</code></pre>
          <a href="https://example.com/docs">Docs</a>
        </main>
      </body>
    </html>
    """
