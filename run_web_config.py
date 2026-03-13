#!/usr/bin/env python3
"""Run the web configuration interface."""

import os

from web_config import app

if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    port = int(os.getenv("WEB_CONFIG_PORT", "5000"))
    print("🚀 Starting MCP Web Config Interface")
    print(f"📍 Open http://localhost:{port} in your browser")
    print("Press Ctrl+C to stop")
    app.run(debug=debug_mode, port=port)
