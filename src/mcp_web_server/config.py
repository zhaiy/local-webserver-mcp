"""Centralized configuration for MCP Web Server."""

from __future__ import annotations

import logging
import os


LOG_LEVEL = os.getenv("MCP_LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO))
logger = logging.getLogger("mcp-web-server")

DEFAULT_USER_AGENT = os.getenv(
    "MCP_USER_AGENT",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
)
DEFAULT_TIMEOUT = float(os.getenv("MCP_DEFAULT_TIMEOUT", "30"))

HTTP_PROXY = os.getenv("MCP_HTTP_PROXY")
HTTPS_PROXY = os.getenv("MCP_HTTPS_PROXY")

RATE_LIMIT_SEARCH = int(os.getenv("MCP_RATE_LIMIT_SEARCH", "5"))
RATE_LIMIT_HTTP = int(os.getenv("MCP_RATE_LIMIT_HTTP", "30"))
RATE_LIMIT_EXTRACT = int(os.getenv("MCP_RATE_LIMIT_EXTRACT", "10"))
