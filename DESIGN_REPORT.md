# MCP Web Server 升级优化设计报告

> 生成日期: 2026-03-12
> 项目: mcp-web-server v0.1.0
> 目标: 提供可直接交给 LLM（GPT Codex 等）执行的任务清单

---

## 一、现状总结

### 项目架构

```
src/mcp_web_server/server.py  ← 核心：4 个 MCP 工具
web_config.py                  ← Flask Web 配置界面
run_server.py / run_web_config.py ← 入口脚本
```

### 现有工具

| 工具 | 功能 | 同步/异步 |
|------|------|-----------|
| `http_request` | 通用 HTTP 请求 | async |
| `web_search` | DuckDuckGo 搜索 | sync |
| `extract_webpage_content` | 网页正文提取 | async |
| `fetch_json` | 获取并解析 JSON | async |

### 依赖栈

- Python ≥ 3.10, mcp ≥ 1.0.0, httpx ≥ 0.27.0, beautifulsoup4 ≥ 4.12.0, ddgs ≥ 8.0.0

---

## 二、问题分析与优化项（按优先级排序）

### P0 — 必须修复

#### 2.1 错误处理不统一，部分工具无异常捕获

**现状:**
- `http_request`: 无 try/except，网络异常会直接抛出未处理异常
- `web_search`: 错误混入返回列表 `[{"error": str(e)}]`，调用方无法区分成功与失败
- `extract_webpage_content`: `raise_for_status()` 后无捕获，BeautifulSoup 解析非 HTML 内容会出错
- `fetch_json`: `response.json()` 在非 JSON 响应时会抛出 `JSONDecodeError`，未处理

**任务:**

```
文件: src/mcp_web_server/server.py

1. 为所有 4 个工具函数添加统一的 try/except 包装
2. 定义统一的错误返回格式:
   成功: {"success": True, "data": ...}
   失败: {"success": False, "error": "<错误类型>", "message": "<错误描述>"}
3. 区分并处理以下异常类型:
   - httpx.TimeoutException → 超时错误
   - httpx.ConnectError → 连接错误
   - httpx.HTTPStatusError → HTTP 状态码错误
   - json.JSONDecodeError → JSON 解析错误
   - Exception → 未知错误
4. web_search 的错误不再混入结果列表，改用上述统一格式
```

#### 2.2 httpx.AsyncClient 每次请求都新建连接

**现状:**
每个工具函数内部都用 `async with httpx.AsyncClient() as client:` 创建新客户端，无法复用连接池。

**任务:**

```
文件: src/mcp_web_server/server.py

1. 创建模块级的 httpx.AsyncClient 实例，配置连接池:
   - 设置 limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
   - 设置默认 headers=HTTP_HEADERS
   - 设置默认 timeout=httpx.Timeout(30.0, connect=10.0)
   - 设置 follow_redirects=True
2. 在 http_request / extract_webpage_content / fetch_json 中复用该客户端
3. 添加 atexit 或 MCP server shutdown hook 来关闭客户端
```

---

### P1 — 重要改进

#### 2.3 web_search 是同步函数，会阻塞事件循环

**现状:**
`web_search` 使用同步的 `DDGS().text()`，在 MCP 的异步框架中调用时会阻塞整个事件循环。

**任务:**

```
文件: src/mcp_web_server/server.py

1. 将 web_search 改为 async 函数
2. 使用 asyncio.to_thread() 包装 DDGS 的同步调用:
   async def web_search(...):
       def _search():
           with DDGS() as ddgs:
               return list(ddgs.text(...))
       ddg_results = await asyncio.to_thread(_search)
3. 或者使用 DDGS 的异步接口 (如果 ddgs 库支持 AsyncDDGS)
```

#### 2.4 extract_webpage_content 内容提取能力较弱

**现状:**
- 仅提取 `<p>` 标签，过滤掉长度 ≤ 10 的文本
- 对表格、列表、代码块等内容完全忽略
- headings 提取后未与正文内容关联（标题和段落的顺序丢失）

**任务:**

```
文件: src/mcp_web_server/server.py

1. 扩展内容提取范围，增加对以下标签的支持:
   - <ul>/<ol>/<li> → 列表内容
   - <table>/<tr>/<td> → 表格内容（转为简单文本表格）
   - <pre>/<code> → 代码块
   - <blockquote> → 引用
2. 保持内容的文档顺序（headings + paragraphs 混合排列）:
   遍历 content_tag 的所有子元素，按 DOM 顺序提取:
   - h1-h6 → "## 标题文本"
   - p → 段落文本
   - ul/ol → "- 列表项"
   - pre/code → "```\n代码内容\n```"
3. 添加 readability 算法（可选）:
   考虑引入 readability-lxml 或 trafilatura 库做更智能的正文提取
```

#### 2.5 缺少请求重试机制

**现状:**
所有 HTTP 请求在失败后立即报错，无重试。

**任务:**

```
文件: src/mcp_web_server/server.py

1. 使用 httpx 的 transport 层配置重试:
   transport = httpx.AsyncHTTPTransport(retries=2)
   在创建 AsyncClient 时传入 transport=transport
2. 或实现手动重试装饰器:
   - 最大重试 2 次
   - 仅对 5xx 错误和连接超时重试
   - 重试间隔: 1s, 2s（指数退避）
```

#### 2.6 缺少日志系统

**现状:**
代码中没有任何日志记录，调试困难。

**任务:**

```
文件: src/mcp_web_server/server.py

1. 在文件顶部添加 logging 配置:
   import logging
   logger = logging.getLogger("mcp-web-server")
2. 在关键节点添加日志:
   - 工具调用入口: logger.info("web_search called", extra={"query": query})
   - HTTP 请求: logger.debug("HTTP %s %s", method, url)
   - 错误发生: logger.error("Failed to ...", exc_info=True)
   - 性能数据: logger.info("Request completed in %.2fs", elapsed)
3. 日志级别通过环境变量 MCP_LOG_LEVEL 控制，默认 INFO
```

---

### P2 — 功能增强

#### 2.7 新增工具: web_search_and_extract（搜索 + 提取一体化）

**理由:**
LLM 使用时经常需要先搜索再提取内容，拆成两步会产生额外的 MCP 调用延迟。

**任务:**

```
文件: src/mcp_web_server/server.py

新增 MCP 工具:

@mcp.tool()
async def web_search_and_extract(
    query: str,
    num_results: int = 3,
    max_content_length: int = 5000,
    region: str = "wt-wt",
) -> dict:
    """
    搜索并提取前 N 个结果的网页内容。
    适合需要快速获取搜索结果详细内容的场景。

    返回:
    {
        "query": "...",
        "results": [
            {
                "title": "...",
                "url": "...",
                "snippet": "...",
                "content": "提取的网页正文..."
            }
        ]
    }
    """
    1. 先调用 web_search 获取搜索结果
    2. 并发调用 extract_webpage_content 提取前 num_results 个结果
    3. 使用 asyncio.gather(*tasks, return_exceptions=True) 并发提取
    4. 合并结果返回
```

#### 2.8 新增工具: batch_http_request（批量请求）

**理由:**
LLM 有时需要同时请求多个 URL（如比较多个 API 的结果），逐个调用效率低。

**任务:**

```
文件: src/mcp_web_server/server.py

新增 MCP 工具:

@mcp.tool()
async def batch_http_request(
    urls: list[str],
    method: str = "GET",
    headers: Optional[dict] = None,
    timeout: int = 30,
    max_concurrent: int = 5,
) -> list[dict]:
    """
    并发请求多个 URL。

    Args:
        urls: URL 列表
        max_concurrent: 最大并发数（防止目标服务器过载）
    """
    1. 使用 asyncio.Semaphore(max_concurrent) 控制并发
    2. 使用 asyncio.gather 并发请求
    3. 每个结果包含 url + 响应数据 或 错误信息
```

#### 2.9 新增工具: screenshot_webpage（网页截图）

**理由:**
多模态 LLM 可以直接"看"网页截图来理解页面布局和视觉内容。

**任务:**

```
文件: src/mcp_web_server/server.py
新增依赖: pyproject.toml 添加 playwright (可选依赖组)

1. 添加可选依赖组 [project.optional-dependencies] 中增加:
   screenshot = ["playwright>=1.40.0"]

2. 新增工具（仅在 playwright 可用时注册）:
   @mcp.tool()
   async def screenshot_webpage(url: str, full_page: bool = False, width: int = 1280, height: int = 720) -> dict:
       """
       对网页进行截图，返回 base64 编码的图片。
       需要安装 playwright: uv pip install -e ".[screenshot]" && playwright install chromium
       """
       - 使用 playwright 的 async API
       - 返回 {"url": url, "image_base64": "...", "width": ..., "height": ...}

3. 在模块加载时检查 playwright 是否可用:
   try:
       from playwright.async_api import async_playwright
       HAS_PLAYWRIGHT = True
   except ImportError:
       HAS_PLAYWRIGHT = False

   仅在 HAS_PLAYWRIGHT=True 时注册该工具
```

#### 2.10 支持代理和自定义 User-Agent 配置

**现状:**
User-Agent 和代理硬编码，部分网站可能会封禁。

**任务:**

```
文件: src/mcp_web_server/server.py

1. 支持通过环境变量配置:
   - MCP_HTTP_PROXY: HTTP 代理地址（如 http://127.0.0.1:7890）
   - MCP_HTTPS_PROXY: HTTPS 代理地址
   - MCP_USER_AGENT: 自定义 User-Agent
   - MCP_DEFAULT_TIMEOUT: 默认超时时间
2. 在创建 httpx.AsyncClient 时应用:
   proxies = {}
   if os.environ.get("MCP_HTTP_PROXY"):
       proxies["http://"] = os.environ["MCP_HTTP_PROXY"]
   if os.environ.get("MCP_HTTPS_PROXY"):
       proxies["https://"] = os.environ["MCP_HTTPS_PROXY"]
3. User-Agent 轮换（可选）:
   维护一个 UA 列表，每次请求随机选择
```

---

### P3 — 工程质量

#### 2.11 添加自动化测试

**现状:**
仅有 `test_tools.py` 手动测试脚本，无 pytest 测试套件。

**任务:**

```
创建以下文件:

tests/__init__.py          (空文件)
tests/conftest.py          (pytest fixtures)
tests/test_http_request.py
tests/test_web_search.py
tests/test_extract_webpage.py
tests/test_fetch_json.py

1. conftest.py:
   - 使用 pytest-httpx 或 respx 库 mock HTTP 请求
   - 添加 fixture: mock_httpx_client
   - 添加 fixture: sample_html_page (包含各种标签的测试 HTML)

2. 每个测试文件需要覆盖:
   - 正常请求成功
   - 超时处理
   - 网络错误处理
   - 无效输入处理
   - 边界条件（空响应、超大响应、非 UTF-8 编码等）

3. test_web_search.py:
   - mock DDGS 类
   - 测试正常搜索
   - 测试搜索失败
   - 测试结果为空

4. test_extract_webpage.py:
   - 测试提取 <p> 标签内容
   - 测试提取 <h1>-<h3> 标题
   - 测试 include_links=True
   - 测试 max_length 截断
   - 测试非 HTML 内容（如纯文本、XML）

5. 在 pyproject.toml 中添加:
   [tool.pytest.ini_options]
   asyncio_mode = "auto"
   testpaths = ["tests"]

6. 在 dev 依赖中添加:
   "respx>=0.21.0" 或 "pytest-httpx>=0.30.0"
```

#### 2.12 添加类型标注和 Pydantic 模型

**现状:**
返回值全部是裸 dict，无类型约束。

**任务:**

```
文件: src/mcp_web_server/server.py (或新建 src/mcp_web_server/models.py)

1. 为每个工具的返回值定义 Pydantic 模型:

   from pydantic import BaseModel, Field

   class HttpResponse(BaseModel):
       status_code: int
       headers: dict[str, str]
       body: str

   class SearchResult(BaseModel):
       title: str
       url: str
       snippet: str

   class WebpageContent(BaseModel):
       url: str
       title: str
       content: str
       headings: list[str]
       links: list[dict[str, str]] | None = None

   class ErrorResponse(BaseModel):
       success: bool = False
       error: str
       message: str

2. 工具函数使用这些模型作为返回类型标注
3. 使返回数据结构可预测，便于 LLM 解析
```

#### 2.13 添加输入验证

**现状:**
未对输入参数做任何校验（如 URL 格式、method 合法性等）。

**任务:**

```
文件: src/mcp_web_server/server.py

1. URL 验证:
   from urllib.parse import urlparse
   def validate_url(url: str) -> bool:
       parsed = urlparse(url)
       return parsed.scheme in ("http", "https") and bool(parsed.netloc)

   在 http_request / extract_webpage_content / fetch_json 入口处调用

2. HTTP method 验证:
   ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
   if method.upper() not in ALLOWED_METHODS:
       return ErrorResponse(...)

3. 数值范围验证:
   - num_results: 1-50
   - timeout: 1-120
   - max_length: 100-100000
   - max_concurrent (batch): 1-20
```

#### 2.14 添加速率限制

**理由:**
防止 LLM 在循环中大量调用导致被目标网站封禁或 DuckDuckGo 限流。

**任务:**

```
文件: src/mcp_web_server/server.py

1. 实现简单的令牌桶限流器:
   import time

   class RateLimiter:
       def __init__(self, max_calls: int, period: float):
           self.max_calls = max_calls
           self.period = period
           self.calls = []

       async def acquire(self):
           now = time.monotonic()
           self.calls = [t for t in self.calls if now - t < self.period]
           if len(self.calls) >= self.max_calls:
               sleep_time = self.period - (now - self.calls[0])
               await asyncio.sleep(sleep_time)
           self.calls.append(time.monotonic())

2. 配置不同工具的限流:
   - web_search: 5 次/分钟（DuckDuckGo 有隐式限流）
   - http_request: 30 次/分钟
   - extract_webpage_content: 10 次/分钟

3. 限流参数可通过环境变量覆盖:
   MCP_RATE_LIMIT_SEARCH=5
   MCP_RATE_LIMIT_HTTP=30
```

---

### P4 — 文档与配置

#### 2.15 修复 README 问题

**任务:**

```
文件: README.md

1. 删除重复的 "Claude Desktop (Legacy)" 章节（第 53-56 行重复）
2. 添加 "运行测试" 章节:
   ```bash
   uv pip install -e ".[dev]"
   pytest
   ```
3. 添加环境变量配置说明（在完成 2.10 后）
4. 添加架构图（可用 mermaid）
5. 添加 CHANGELOG 或版本记录
```

#### 2.16 清理重复配置文件

**现状:**
`mcp.json` 与 `claude_desktop_config.example.json` 内容完全一致。

**任务:**

```
1. 删除 mcp.json（或将其改为指向 example 的说明）
2. 在 README 中统一引用 claude_desktop_config.example.json 作为配置示例
```

---

## 三、新架构建议

### 目标文件结构

```
src/mcp_web_server/
├── __init__.py
├── server.py          ← MCP 工具注册入口（精简）
├── models.py          ← Pydantic 数据模型
├── http_client.py     ← httpx 客户端管理（连接池、重试、代理）
├── tools/
│   ├── __init__.py
│   ├── http.py        ← http_request, batch_http_request, fetch_json
│   ├── search.py      ← web_search, web_search_and_extract
│   ├── extract.py     ← extract_webpage_content
│   └── screenshot.py  ← screenshot_webpage（可选）
├── utils/
│   ├── __init__.py
│   ├── validation.py  ← URL/参数校验
│   └── rate_limit.py  ← 速率限制器
└── config.py          ← 环境变量配置统一管理

tests/
├── __init__.py
├── conftest.py
├── test_http.py
├── test_search.py
├── test_extract.py
└── test_fetch_json.py
```

### server.py 重构后的样子

```python
"""MCP Web Server - 精简入口"""
from mcp.server.fastmcp import FastMCP
from .tools.http import register_http_tools
from .tools.search import register_search_tools
from .tools.extract import register_extract_tools
from .config import settings

mcp = FastMCP("Web Server")

register_http_tools(mcp)
register_search_tools(mcp)
register_extract_tools(mcp)

# 可选: 截图工具
try:
    from .tools.screenshot import register_screenshot_tools
    register_screenshot_tools(mcp)
except ImportError:
    pass

def main():
    mcp.run()
```

---

## 四、实施路线图

### 第一阶段: 稳定性（预计 2-3h）

| 序号 | 任务 | 对应章节 |
|------|------|----------|
| 1 | 统一错误处理 | 2.1 |
| 2 | 复用 httpx 客户端 | 2.2 |
| 3 | web_search 异步化 | 2.3 |
| 4 | 添加日志系统 | 2.6 |
| 5 | 添加输入验证 | 2.13 |

### 第二阶段: 增强功能（预计 3-4h）

| 序号 | 任务 | 对应章节 |
|------|------|----------|
| 6 | 增强网页内容提取 | 2.4 |
| 7 | 添加重试机制 | 2.5 |
| 8 | 支持代理配置 | 2.10 |
| 9 | 新增 web_search_and_extract | 2.7 |
| 10 | 新增 batch_http_request | 2.8 |

### 第三阶段: 工程质量（预计 3-4h）

| 序号 | 任务 | 对应章节 |
|------|------|----------|
| 11 | 重构为模块化架构 | 第三节 |
| 12 | 添加 Pydantic 模型 | 2.12 |
| 13 | 添加自动化测试 | 2.11 |
| 14 | 添加速率限制 | 2.14 |

### 第四阶段: 锦上添花（预计 2h）

| 序号 | 任务 | 对应章节 |
|------|------|----------|
| 15 | 网页截图工具 | 2.9 |
| 16 | 修复文档 | 2.15 |
| 17 | 清理冗余文件 | 2.16 |

---

## 五、给 LLM 开发者的执行指引

> 以下内容可直接作为 prompt 提供给 GPT Codex / Claude 等 LLM 进行开发。

### Prompt 模板

```
你是一个 Python 开发者。请按照以下设计文档对 mcp-web-server 项目进行升级。

项目使用:
- Python 3.10+
- mcp (FastMCP) 框架
- httpx 做 HTTP 请求
- beautifulsoup4 解析 HTML
- ddgs (DuckDuckGo) 搜索
- pyproject.toml + uv 管理依赖

请按以下顺序执行任务（每完成一个任务提交一次）:

任务 1: [粘贴 2.1 的内容]
任务 2: [粘贴 2.2 的内容]
...

约束:
- 保持向后兼容，不要改变现有工具的函数签名（可以增加可选参数）
- 所有新代码需要有类型标注
- 保持代码简洁，不要过度工程化
- 测试代码中使用 mock，不要实际发起网络请求
```

---

## 六、风险与注意事项

1. **DuckDuckGo 限流**: ddgs 库依赖 DuckDuckGo 的非官方接口，高频调用可能被限流。速率限制（2.14）是必要的防护措施。
2. **Playwright 体积**: screenshot 功能引入 playwright 会增加约 200MB+ 的浏览器二进制文件，建议作为可选依赖。
3. **向后兼容**: 重构为模块化架构时，需确保 `from mcp_web_server.server import mcp, main` 仍然可用。
4. **MCP 协议版本**: 当前依赖 `mcp>=1.0.0`，需关注 MCP SDK 的 breaking changes，建议锁定到 `mcp>=1.0.0,<2.0.0`。
