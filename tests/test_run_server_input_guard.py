import pytest

from run_server import _parse_jsonrpc_line, _resolve_invalid_input_policy


def test_parse_jsonrpc_line_ignores_blank_input() -> None:
    assert _parse_jsonrpc_line("\n") is None
    assert _parse_jsonrpc_line("   \r\n") is None


def test_parse_jsonrpc_line_ignores_invalid_json() -> None:
    assert _parse_jsonrpc_line("{not-json}\n", invalid_policy="ignore") is None


def test_parse_jsonrpc_line_warn_policy_still_ignores_invalid_json() -> None:
    assert _parse_jsonrpc_line("{not-json}\n", invalid_policy="warn") is None


def test_parse_jsonrpc_line_strict_policy_raises() -> None:
    with pytest.raises(ValueError):
        _parse_jsonrpc_line("{not-json}\n", invalid_policy="strict")


def test_parse_jsonrpc_line_accepts_valid_jsonrpc() -> None:
    line = '{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}\n'
    message = _parse_jsonrpc_line(line)
    assert message is not None
    assert message.model_dump()["method"] == "ping"


def test_invalid_policy_env_fallbacks_to_warn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_STDIN_INVALID_INPUT_POLICY", "bad-value")
    assert _resolve_invalid_input_policy() == "warn"


def test_invalid_policy_env_honors_valid_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_STDIN_INVALID_INPUT_POLICY", "STRICT")
    assert _resolve_invalid_input_policy() == "strict"
