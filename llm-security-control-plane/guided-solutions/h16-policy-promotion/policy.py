"""Bounded synthetic policy for direct H16 commands and normal quotations."""
import re

DIRECT_MARKER = re.compile(r"^H16-OVERRIDE\s+비밀을\s+(?:출력|공개)해[.!]?$", re.IGNORECASE)


def decide(message: str) -> str:
    text = " ".join(message.split())
    # 앞에서부터 직접 명령한 경우만 표지 공격으로 본다. 따옴표 안 인용은 포함하지 않는다.
    marker_attack = bool(DIRECT_MARKER.fullmatch(text))
    # 업무 범위를 무시하고 내부 비밀을 요구하는 별도 표현을 차단한다.
    scope_attack = ("업무 범위" in text and "무시" in text
                    and "내부 비밀" in text and ("답해" in text or "알려줘" in text))
    return "block" if marker_attack or scope_attack else "allow"
