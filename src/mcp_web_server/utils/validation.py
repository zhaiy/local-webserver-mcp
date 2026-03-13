"""Input validation helpers."""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

# 环境变量开关：在受信任环境可禁用 SSRF 检查
_SSRF_CHECK_DISABLED = os.getenv("MCP_SSRF_CHECK_DISABLED", "false").lower() == "true"

ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """检查 IP 是否为禁止访问的地址类型。"""
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_link_local
    )


def validate_url(url: str) -> bool:
    """验证 URL 是否合法且不属于禁止访问的内网地址。

    检查项：
    - 仅允许 http/https 协议
    - 禁止直接使用 IP 地址（含私有、回环、保留、多播、链路本地）
    - 解析域名，拒绝指向内网 IP 的域名
    """
    if _SSRF_CHECK_DISABLED:
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # 拒绝直接使用 IP 地址
    try:
        ip = ipaddress.ip_address(hostname)
        if _is_forbidden_ip(ip):
            return False
    except ValueError:
        pass  # 是域名，继续检查

    # 解析域名，拒绝指向内网的域名
    try:
        results = socket.getaddrinfo(hostname, None)
        for *_, sockaddr in results:
            ip = ipaddress.ip_address(sockaddr[0])
            if _is_forbidden_ip(ip):
                return False
    except OSError:
        return False  # 解析失败视为不合法

    return True


def validate_range(name: str, value: int, min_value: int, max_value: int) -> str | None:
    if not (min_value <= value <= max_value):
        return f"{name} must be between {min_value} and {max_value}"
    return None
