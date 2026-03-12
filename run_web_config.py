#!/usr/bin/env python3
"""Run the web configuration interface."""

from web_config import app

if __name__ == "__main__":
    print("🚀 Starting MCP Web Config Interface")
    print("📍 Open http://localhost:5000 in your browser")
    print("Press Ctrl+C to stop")
    app.run(debug=True, port=5000)
