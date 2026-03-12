#!/usr/bin/env python3
"""Web configuration interface for MCP server installation."""

from flask import Flask, render_template_string, request, jsonify
import subprocess
import json
import os

app = Flask(__name__)

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


@app.route("/")
def index():
    """Render the configuration page."""
    # 获取当前项目路径作为默认值
    default_path = os.path.dirname(os.path.abspath(__file__))
    return render_template_string(HTML_TEMPLATE, default_path=default_path)


@app.route("/install", methods=["POST"])
def install():
    """Handle MCP server installation."""
    try:
        data = request.get_json()
        server_name = data.get("serverName", "web-server")
        install_path = data.get("installPath")
        scope = data.get("scope", "local")

        if not install_path:
            return jsonify({"success": False, "error": "安装路径不能为空"}), 400

        # 构建 claude mcp add 命令
        # 使用 stdio 方式，通过 uv 运行
        command = [
            "claude",
            "mcp",
            "add",
            server_name,
            "-s", scope,
            "--",
            "uv",
            "run",
            "--directory",
            install_path,
            "python",
            "run_server.py"
        ]

        # 执行命令
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            return jsonify({
                "success": True,
                "message": result.stdout or "安装成功"
            })
        else:
            return jsonify({
                "success": False,
                "error": result.stderr or result.stdout or "命令执行失败"
            }), 400

    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "命令执行超时"}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
