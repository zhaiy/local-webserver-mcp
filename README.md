# MCP Web Server

一个本地运行的 MCP server，提供免费的网络访问功能。可以配置到 Claude Desktop 或其他 MCP 客户端使用。

## 功能

- **HTTP 请求**: 发送 GET/POST/PUT/DELETE 等 HTTP 请求
- **网页搜索**: 使用 DuckDuckGo 进行搜索（无需 API key）
- **网页内容提取**: 从网页中提取可读内容，去除广告和导航
- **JSON 获取**: 快速获取并解析 API 返回的 JSON 数据

## 安装

```bash
# 使用 uv（推荐）
uv pip install -e .

# 或使用 pip
pip install -e .
```

## 配置

###  Web 界面一键配置（推荐）

通过 Web 界面，可以轻松地一键配置 MCP Server，无需手动复制命令。

```bash
# 启动 Web 配置界面
uv run python run_web_config.py

# 或直接运行
python run_web_config.py
```

然后在浏览器中打开 **http://localhost:5000**，点击"立即安装"按钮即可完成配置。

![Web Config](https://via.placeholder.com/500x300?text=Web+Config+Interface)

### 手动配置

#### Claude Code

在终端执行以下命令：

```bash
claude mcp add web-server -s local -- uv run --directory /path/to/your/project python run_server.py
```

#### Claude Desktop (Legacy)

将以下配置添加到 `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) 或相应配置文件中：

#### Claude Desktop (Legacy)

将以下配置添加到 `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) 或相应配置文件中：

```json
{
  "mcpServers": {
    "web-server": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/your/project",
        "python",
        "run_server.py"
      ]
    }
  }
}
```

> 注意：将路径替换为你的实际项目路径。

### OpenCLI / 其他 MCP 客户端

配置方式类似，根据你的客户端文档添加 MCP server 配置。

## 可用工具

### `http_request`

发送 HTTP 请求：
- `url`: 请求的 URL
- `method`: HTTP 方法 (GET, POST, 等)
- `headers`: 可选的自定义 headers
- `json_data`: POST/PUT 请求的 JSON 数据
- `timeout`: 超时时间（秒）

### `web_search`

搜索网页：
- `query`: 搜索关键词
- `num_results`: 返回结果数量（默认 10）
- `region`: 地区代码（默认 wt-wt 全球）
- `time`: 时间过滤 - d (天), w (周), m (月), y (年)

### `extract_webpage_content`

提取网页内容：
- `url`: 网页 URL
- `include_links`: 是否包含链接（默认 false）
- `max_length`: 最大内容长度（默认 10000）

### `fetch_json`

获取 JSON 数据：
- `url`: JSON 数据的 URL
- `timeout`: 超时时间（秒）

## 运行测试

```bash
# 直接运行
python run_server.py

# 或使用 uv
uv run python run_server.py
```

## 依赖

- Python >= 3.10
- mcp >= 1.0.0
- httpx >= 0.27.0
- beautifulsoup4 >= 4.12.0
- ddgs >= 8.0.0 (DuckDuckGo 搜索)
