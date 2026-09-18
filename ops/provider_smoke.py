#!/usr/bin/env python3
"""Non-destructive contract smoke test for the configured production provider."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))


def main() -> int:
    from rapiin.config import settings

    settings.validate_for_startup()
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=settings.ai_base_url)
    parser.add_argument("--model", default=settings.ai_model)
    args = parser.parse_args()
    api_key = settings.ai_api_key
    if not args.base_url or not api_key:
        raise SystemExit("AI_BASE_URL and AI_API_KEY are required")
    from rapiin.ai.provider import OpenAICompatibleProvider
    provider = OpenAICompatibleProvider(base_url=args.base_url, api_key=api_key, model=args.model)
    deltas: list[str] = []
    streamed = provider.chat_stream(
        [{"role": "user", "content": "Jawab persis dengan kata: siap"}], on_delta=deltas.append
    )
    if not streamed["message"].get("content") or not deltas:
        raise SystemExit("streaming text contract failed")
    tools = [{"type": "function", "function": {"name": "release_probe", "description": "Release contract probe",
              "parameters": {"type": "object", "properties": {"value": {"type": "string"}}, "required": ["value"]}}}]
    called = provider.chat(
        [{"role": "user", "content": "Panggil tool release_probe dengan value siap. Jangan melakukan hal lain."}], tools=tools
    )["message"].get("tool_calls") or []
    if not called or called[0].get("function", {}).get("name") != "release_probe":
        raise SystemExit("tool-calling contract failed")
    json.loads(called[0]["function"].get("arguments") or "{}")
    print("provider_contract_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
