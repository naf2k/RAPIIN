"""Sanitization and structured-output boundaries for Operations agents."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_SECRET_KEY = re.compile(r"(?i)(api[-_]?key|authorization|cookie|password|secret|token|device[-_]?key)")
_SECRET_VALUE = re.compile(
    r"(?i)(bearer\s+[a-z0-9._~+/=-]{8,}|sk-[a-z0-9_-]{12,}|(?:api[-_]?key|password|secret|token)\s*[:=]\s*[^\s,;]+)"
)
_INJECTION = re.compile(r"(?i)(ignore\s+(all\s+)?previous\s+instructions|system\s+prompt|developer\s+message|bypass\s+(security|approval))")


def sanitize_text(value: str, limit: int = 8000) -> str:
    clean = _SECRET_VALUE.sub("[REDACTED]", str(value))
    clean = _INJECTION.sub("[UNTRUSTED_INSTRUCTION]", clean)
    return clean[:limit]


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): "[REDACTED]" if _SECRET_KEY.search(str(k)) else sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value[:200]]
    if isinstance(value, str):
        return sanitize_text(value)
    return value


def content_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def parse_agent_report(output: str) -> dict:
    """Accept one JSON object and return only the documented report fields."""
    text = output.strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Agent tidak menghasilkan laporan JSON.")
    parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, dict) or not str(parsed.get("summary", "")).strip():
        raise ValueError("Laporan agent tidak memiliki summary.")
    confidence = parsed.get("confidence")
    if isinstance(confidence, str):
        confidence = {"high": 0.85, "medium": 0.6, "low": 0.35}.get(confidence.strip().lower())
    report = {
        "summary": sanitize_text(parsed["summary"], 4000),
        "findings": sanitize(parsed.get("findings", [])),
        "recommendation": sanitize(parsed.get("recommendation", "")),
        "confidence": confidence,
        "evidence_refs": sanitize(parsed.get("evidence_refs", [])),
        "residual_risks": sanitize(parsed.get("residual_risks", [])),
    }
    if not isinstance(report["confidence"], (int, float)) or not 0 <= report["confidence"] <= 1:
        raise ValueError("Confidence agent wajib berupa angka 0 sampai 1.")
    return report
