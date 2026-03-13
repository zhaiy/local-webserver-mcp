from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcp_web_server.server import web_search


def _run_in_thread_inline(fn, *args, **kwargs):  # type: ignore[no-untyped-def]
    return fn(*args, **kwargs)


@pytest.mark.asyncio
async def test_web_search_success() -> None:
    class FakeDDGS:
        def __enter__(self) -> "FakeDDGS":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

        def text(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return [
                {"title": "A", "href": "https://a.com", "body": "sa"},
                {"title": "B", "href": "https://b.com", "body": "sb"},
            ]

    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "duckduckgo"):
        with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
            with patch("mcp_web_server.tools.search.DDGS", FakeDDGS):
                with patch(
                    "mcp_web_server.tools.search.asyncio.to_thread",
                    new=AsyncMock(side_effect=_run_in_thread_inline),
                ):
                    result = await web_search("python", num_results=2)

    assert result["success"] is True
    assert len(result["data"]) == 2
    assert result["data"][0]["url"] == "https://a.com"


@pytest.mark.asyncio
async def test_web_search_failure() -> None:
    class BrokenDDGS:
        def __enter__(self):  # type: ignore[no-untyped-def]
            raise RuntimeError("search failed")

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "duckduckgo"):
        with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
            with patch("mcp_web_server.tools.search.DDGS", BrokenDDGS):
                with patch(
                    "mcp_web_server.tools.search.asyncio.to_thread",
                    new=AsyncMock(side_effect=_run_in_thread_inline),
                ):
                    result = await web_search("python")

    assert result["success"] is False
    assert result["error"] == "Exception"


@pytest.mark.asyncio
async def test_web_search_empty_result() -> None:
    class EmptyDDGS:
        def __enter__(self) -> "EmptyDDGS":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
            return None

        def text(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            return []

    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "duckduckgo"):
        with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
            with patch("mcp_web_server.tools.search.DDGS", EmptyDDGS):
                with patch(
                    "mcp_web_server.tools.search.asyncio.to_thread",
                    new=AsyncMock(side_effect=_run_in_thread_inline),
                ):
                    result = await web_search("python")

    assert result["success"] is True
    assert result["data"] == []


@pytest.mark.asyncio
async def test_web_search_unknown_engine_returns_validation_error() -> None:
    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "unknown"):
        with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
            result = await web_search("python")

    assert result["success"] is False
    assert result["error"] == "ValidationError"
    assert "Unsupported search engine" in result["message"]


@pytest.mark.asyncio
async def test_web_search_bing_parse_result() -> None:
    html = """
    <html>
      <body>
        <li class="b_algo">
          <h2><a href="https://example.com/a">Result A</a></h2>
          <div class="b_caption"><p>Snippet A</p></div>
        </li>
      </body>
    </html>
    """

    response = MagicMock()
    response.text = html
    response.raise_for_status.return_value = None

    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "bing"):
        with patch("mcp_web_server.tools.search.BING_DOMAIN", "www.bing.com"):
            with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
                with patch("mcp_web_server.tools.search.safe_request", new=AsyncMock(return_value=response)) as mock_get:
                    result = await web_search("python", num_results=1, region="cn-zh", time="d")

    assert result["success"] is True
    assert result["data"] == [{"title": "Result A", "url": "https://example.com/a", "snippet": "Snippet A"}]
    mock_get.assert_awaited_once()
    assert mock_get.await_args.kwargs["params"]["cc"] == "cn"
    assert mock_get.await_args.kwargs["params"]["qft"] == "+filterui:age-lt24h"


@pytest.mark.asyncio
async def test_web_search_bing_deduplicates_results() -> None:
    html = """
    <html>
      <body>
        <li class="b_algo">
          <h2><a href="https://example.com/a">Result A1</a></h2>
          <div class="b_caption"><p>Snippet A1</p></div>
        </li>
        <li class="b_algo">
          <h2><a href="https://example.com/a">Result A2</a></h2>
          <div class="b_caption"><p>Snippet A2</p></div>
        </li>
      </body>
    </html>
    """

    response = MagicMock()
    response.text = html
    response.raise_for_status.return_value = None

    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "bing"):
        with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
            with patch("mcp_web_server.tools.search.safe_request", new=AsyncMock(return_value=response)):
                result = await web_search("python", num_results=10)

    assert result["success"] is True
    assert len(result["data"]) == 1
    assert result["data"][0]["url"] == "https://example.com/a"


@pytest.mark.asyncio
async def test_web_search_baidu_parse_result() -> None:
    html = """
    <html>
      <body>
        <div class="result c-container">
          <h3><a href="https://example.com/b">Result B</a></h3>
          <div class="c-abstract">Snippet B</div>
        </div>
      </body>
    </html>
    """

    response = MagicMock()
    response.text = html
    response.raise_for_status.return_value = None

    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "baidu"):
        with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
            with patch("mcp_web_server.tools.search.safe_request", new=AsyncMock(return_value=response)):
                result = await web_search("python", num_results=1)

    assert result["success"] is True
    assert result["data"] == [{"title": "Result B", "url": "https://example.com/b", "snippet": "Snippet B"}]


@pytest.mark.asyncio
async def test_web_search_baidu_resolves_redirect_url() -> None:
    html = """
    <html>
      <body>
        <div class="result c-container">
          <h3><a href="https://www.baidu.com/link?url=abc">Result B</a></h3>
          <div class="c-abstract">Snippet B</div>
        </div>
      </body>
    </html>
    """

    search_response = MagicMock()
    search_response.text = html
    search_response.raise_for_status.return_value = None

    redirect_head_response = MagicMock()
    redirect_head_response.url = "https://target.example/article"

    async def mock_safe_request(method: str, url: str, **kwargs):  # type: ignore[no-untyped-def]
        if url == "https://www.baidu.com/s":
            return search_response
        if url == "https://www.baidu.com/link?url=abc" and method == "HEAD":
            return redirect_head_response
        raise AssertionError(f"unexpected call: method={method}, url={url}")

    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "baidu"):
        with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
            with patch("mcp_web_server.tools.search.safe_request", new=AsyncMock(side_effect=mock_safe_request)):
                result = await web_search("python", num_results=1)

    assert result["success"] is True
    assert result["data"][0]["url"] == "https://target.example/article"


@pytest.mark.asyncio
async def test_web_search_baidu_warns_for_ignored_region_and_time() -> None:
    response = MagicMock()
    response.text = "<html><body></body></html>"
    response.raise_for_status.return_value = None

    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "baidu"):
        with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
            with patch("mcp_web_server.tools.search.safe_request", new=AsyncMock(return_value=response)):
                with patch("mcp_web_server.tools.search.logger.warning") as warning:
                    result = await web_search("python", region="cn-zh", time="d")

    assert result["success"] is True
    warning.assert_any_call("baidu search currently ignores region=%s", "cn-zh")
    warning.assert_any_call("baidu search currently ignores time=%s", "d")


@pytest.mark.asyncio
async def test_web_search_bing_challenge_page_logs_warning() -> None:
    response = MagicMock()
    response.text = "<html><body>Please verify you are human</body></html>"
    response.raise_for_status.return_value = None

    with patch("mcp_web_server.tools.search.SEARCH_ENGINE", "bing"):
        with patch("mcp_web_server.tools.search.SEARCH_RATE_LIMITER.acquire", new=AsyncMock()):
            with patch("mcp_web_server.tools.search.safe_request", new=AsyncMock(return_value=response)):
                with patch("mcp_web_server.tools.search.logger.warning") as warning:
                    result = await web_search("python")

    assert result["success"] is True
    assert result["data"] == []
    warning.assert_any_call("bing search returned challenge page; query=%s", "python")
