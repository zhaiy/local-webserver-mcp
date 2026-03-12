"""Shared response and exception helpers for tools."""

from __future__ import annotations

import json
from typing import Any

import httpx

from mcp_web_server.config import logger
from mcp_web_server.models import ErrorResponse, SuccessResponse


def success_response(data: Any) -> dict[str, Any]:
    return SuccessResponse(data=data).model_dump()


def error_response(error_type: str, message: str) -> dict[str, Any]:
    return ErrorResponse(error=error_type, message=message).model_dump()


def handle_common_exception(tool_name: str, exc: Exception) -> dict[str, Any]:
    logger.error("%s failed", tool_name, exc_info=True)
    if isinstance(exc, httpx.TimeoutException):
        return error_response("TimeoutException", str(exc))
    if isinstance(exc, httpx.ConnectError):
        return error_response("ConnectError", str(exc))
    if isinstance(exc, httpx.HTTPStatusError):
        return error_response("HTTPStatusError", str(exc))
    if isinstance(exc, json.JSONDecodeError):
        return error_response("JSONDecodeError", str(exc))
    return error_response("Exception", str(exc))
