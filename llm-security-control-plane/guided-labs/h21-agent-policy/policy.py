"""Learner-owned Agent Gateway admission policy for H21."""

from __future__ import annotations

from dataclasses import dataclass


class PolicyDenied(ValueError):
    """Stop before the model provider or MCP server is contacted."""


@dataclass(frozen=True)
class Admission:
    principal: str
    model: str
    server_id: str
    tool: str
    max_tool_calls: int
    max_result_bytes: int
    tool_timeout_ms: int


POLICIES = {
    "support-agent": {
        "models": {"us.amazon.nova-lite-v1:0"},
        "servers": {"training-notice-mcp"},
        "tools": {"lookup_notice", "oversized_context", "slow_context"},
        "max_tool_calls": 2,
        "max_result_bytes": 160,
        "tool_timeout_ms": 250,
    }
}


def authorize(
    principal: str,
    model: str,
    server_id: str,
    tool: str,
    requested_tool_calls: int,
    requested_result_bytes: int,
    requested_timeout_ms: int,
    state_owner: str,
) -> Admission:
    """Return server-owned limits after validating every Agent boundary."""
    configured = POLICIES.get(principal)
    if configured is None:
        raise PolicyDenied("principal not configured")
    # TODO 2: 아래 False를 model·server·tool 허용 목록 및 state_owner의
    # 정책 위반 조건으로 바꾸세요. if/raise 구조는 그대로 사용합니다.
    if False:
        raise PolicyDenied("agent boundary denied")
    # TODO 3: 요청값이 정책 상한보다 커도 여기서 일괄 거부하지 않습니다.
    # Host가 아래 Admission의 서버 상한으로 실제 호출·결과·시간을 제한합니다.
    # 요청값 대신 configured의 세 상한을 Admission에 넣으세요.
    return Admission(
        principal=principal,
        model=model,
        server_id=server_id,
        tool=tool,
        max_tool_calls=requested_tool_calls,
        max_result_bytes=requested_result_bytes,
        tool_timeout_ms=requested_timeout_ms,
    )
