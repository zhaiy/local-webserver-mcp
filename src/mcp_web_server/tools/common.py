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
    logger.error("%s failed", tool_name, exc_info=True)  # 详细错误仅写入日志
    if isinstance(exc, httpx.TimeoutException):
        return error_response("TimeoutException", "请求超时")
    if isinstance(exc, httpx.ConnectError):
        return error_response("ConnectError", "连接失败")
    if isinstance(exc, httpx.HTTPStatusError):
        # 只返回状态码，不返回完整 URL
        return error_response("HTTPStatusError", f"HTTP 错误: {exc.response.status_code}")
    if isinstance(exc, json.JSONDecodeError):
        return error_response("JSONDecodeError", "响应不是有效的 JSON")
    return error_response("Exception", "内部错误，请查看服务日志")
