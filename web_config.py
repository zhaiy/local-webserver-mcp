#!/usr/bin/env python3
"""Web configuration interface for MCP server installation."""

import os
import re
import subprocess
from typing import Any

from flask import Flask, Response, jsonify, render_template_string, request

app = Flask(__name__)

# 白名单：serverName 只允许字母、数字、连字符、下划线
SERVER_NAME_RE = re.compile(r'^[a-zA-Z0-9_-]{1,64}$')

# scope 白名单
VALID_SCOPES = {"local", "user", "project"}

# 简单 token 认证（通过环境变量注入）
WEB_CONFIG_TOKEN = os.getenv("WEB_CONFIG_TOKEN", "")

# HTML 模板 - 配置界面
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP Server 配置</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 20px;
        }
        .container {
            background: white;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            max-width: 500px;
            width: 100%;
            padding: 40px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 24px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 14px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
            font-size: 14px;
        }
        input[type="text"],
        input[type="url"],
        select {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.3s;
        }
        input:focus,
        select:focus {
            outline: none;
            border-color: #667eea;
        }
        .btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 30px rgba(102, 126, 234, 0.4);
        }
        .btn:active {
            transform: translateY(0);
        }
        .btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            transform: none;
        }
        .result {
            margin-top: 20px;
            padding: 16px;
            border-radius: 8px;
            display: none;
        }
        .result.success {
            background: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
            display: block;
        }
        .result.error {
            background: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
            display: block;
        }
        .loading {
            display: none;
            text-align: center;
            margin-top: 15px;
        }
        .loading.show {
            display: block;
        }
        .spinner {
            width: 24px;
            height: 24px;
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin: 0 auto 10px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        .info-box {
            background: #f0f4ff;
            border-radius: 8px;
            padding: 16px;
            margin-bottom: 25px;
        }
        .info-box p {
            color: #555;
            font-size: 13px;
            line-height: 1.6;
        }
        .command-preview {
            background: #f5f5f5;
            border-radius: 6px;
            padding: 12px;
            font-family: 'Monaco', 'Menlo', monospace;
            font-size: 12px;
            color: #333;
            margin-top: 8px;
            word-break: break-all;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 MCP Server 一键配置</h1>
        <p class="subtitle">将此 MCP Server 添加到 Claude Code</p>

        <div class="info-box">
            <p>点击下方的"立即安装"按钮，将自动执行配置命令，将此 MCP Server 添加到 Claude Code 的本地配置中。</p>
        </div>

        <form id="configForm">
            <div class="form-group">
                <label for="serverName">MCP Server 名称</label>
                <input type="text" id="serverName" name="serverName" value="web-server" placeholder="例如：web-server">
            </div>

            <div class="form-group">
                <label for="installPath">安装路径</label>
                <input type="text" id="installPath" name="installPath" value="{{ default_path }}" placeholder="/path/to/your/project">
            </div>

            <div class="form-group">
                <label for="scope">配置作用域</label>
                <select id="scope" name="scope">
                    <option value="local">Local (仅当前项目)</option>
                    <option value="user">User (当前用户)</option>
                    <option value="project">Project (项目级)</option>
                </select>
            </div>

            <button type="submit" class="btn" id="installBtn">立即安装</button>

            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>正在配置中...</p>
            </div>

            <div class="result" id="result"></div>
        </form>
    </div>

    <script>
        document.getElementById('configForm').addEventListener('submit', async function(e) {
            e.preventDefault();

            const btn = document.getElementById('installBtn');
            const loading = document.getElementById('loading');
            const result = document.getElementById('result');

            btn.disabled = true;
            loading.classList.add('show');
            result.className = 'result';

            const formData = {
                serverName: document.getElementById('serverName').value,
                installPath: document.getElementById('installPath').value,
                scope: document.getElementById('scope').value
            };

            try {
                const response = await fetch('/install', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(formData)
                });

                const data = await response.json();

                if (data.success) {
                    result.className = 'result success';
                    result.innerHTML = '<strong>✅ 安装成功!</strong><p>MCP Server 已添加到 Claude Code 配置。</p>';
                } else {
                    result.className = 'result error';
                    result.innerHTML = '<strong>❌ 安装失败</strong><p>' + (data.error || '未知错误') + '</p>';
                }
            } catch (error) {
                result.className = 'result error';
                result.innerHTML = '<strong>❌ 安装失败</strong><p>' + error.message + '</p>';
            } finally {
                btn.disabled = false;
                loading.classList.remove('show');
            }
        });
    </script>
</body>
</html>
"""


@app.after_request
def add_security_headers(response: Response) -> Response:
    """添加安全响应头。"""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.route("/")
def index() -> str:
    """Render the configuration page."""
    # 获取当前项目路径作为默认值
    default_path = os.path.dirname(os.path.abspath(__file__))
    return render_template_string(HTML_TEMPLATE, default_path=default_path)


@app.route("/install", methods=["POST"])
def install() -> tuple[Response, int]:
    """Handle MCP server installation."""
    try:
        # Token 认证（若配置了 token 则强制验证）
        if WEB_CONFIG_TOKEN:
            auth = request.headers.get("X-Install-Token", "")
            if auth != WEB_CONFIG_TOKEN:
                return jsonify({"success": False, "error": "未授权"}), 403

        data: dict[str, Any] = request.get_json() or {}
        server_name = data.get("serverName", "web-server")
        install_path = data.get("installPath")
        scope = data.get("scope", "local")

        # 验证 serverName 格式
        if not isinstance(server_name, str) or not SERVER_NAME_RE.match(server_name):
            return jsonify(
                {"success": False, "error": "serverName 只允许字母、数字、连字符和下划线，长度 1-64 字符"}
            ), 400

        # 验证 scope 白名单
        if not isinstance(scope, str) or scope not in VALID_SCOPES:
            return jsonify(
                {"success": False, "error": f"scope 必须是 {VALID_SCOPES} 之一"}
            ), 400

        # 验证 installPath
        if not install_path or not isinstance(install_path, str):
            return jsonify({"success": False, "error": "安装路径不能为空"}), 400

        # 解析符号链接、防路径穿越，并验证是否为存在的目录
        install_path = os.path.realpath(install_path)
        if not os.path.isdir(install_path):
            return jsonify({"success": False, "error": "安装路径不存在或不是目录"}), 400

        # 构建 claude mcp add 命令
        command = [
            "claude",
            "mcp",
            "add",
            server_name,
            "-s",
            scope,
            "--",
            "uv",
            "run",
            "--directory",
            install_path,
            "python",
            "run_server.py",
        ]

        # 执行命令
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            return jsonify({
                "success": True,
                "message": result.stdout or "安装成功",
            }), 200
        return jsonify({
            "success": False,
            "error": result.stderr or result.stdout or "命令执行失败",
        }), 400

    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "命令执行超时"}), 400
    except Exception as e:
        # 生产环境不暴露详细错误信息
        return jsonify({"success": False, "error": "内部错误，请查看服务日志"}), 500


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.getenv("WEB_CONFIG_PORT", "5000"))
    app.run(debug=debug_mode, port=port)
