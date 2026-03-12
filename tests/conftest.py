from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_httpx_client() -> Iterator[dict[str, AsyncMock]]:
    with patch("mcp_web_server.http_client.HTTP_CLIENT.request", new_callable=AsyncMock) as mock_request:
        with patch("mcp_web_server.http_client.HTTP_CLIENT.get", new_callable=AsyncMock) as mock_get:
            yield {"request": mock_request, "get": mock_get}


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
