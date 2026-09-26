"""Prevent common credentials from entering provider prompts or private memory."""
from __future__ import annotations

import re

SENSITIVE_KEY = re.compile(r"(password|passwd|secret|token|api[_-]?key|credential|private[_-]?key)", re.I)
PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]{12,}"),
    re.compile(r"(?i)((?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in PATTERNS:
        redacted = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", redacted)
    return redacted


def redact_value(value):
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {key: "[REDACTED]" if SENSITIVE_KEY.search(str(key)) else redact_value(item) for key, item in value.items()}
    return value
