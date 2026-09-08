"""AI Provider abstraction - OpenAI-compatible chat/tool client.

V1 points to the local 9router. Providers are swappable without touching
Hermes Core, satisfying PRD section 24.
"""
from __future__ import annotations

import json
import time

import httpx

from ..config import settings


class AIProviderError(Exception):
    pass


def _parse_sse_json(text: str) -> dict:
    """Extract the first JSON object from an SSE stream body.

    Some compatible routers return `text/event-stream` even for non-stream
    requests, ending with `data: [DONE]`. We scan the body for JSON objects
    and return the first complete one that contains a `choices` key.
    """
    decoder = json.JSONDecoder()
    idx = 0
    length = len(text)
    while idx < length:
        start = text.find("{", idx)
        if start == -1:
            break
        try:
            obj, end = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(obj, dict) and "choices" in obj:
            return obj
        idx = end
    raise AIProviderError("Penyedia AI tidak mengembalikan data percakapan yang valid.")


class OpenAICompatibleProvider:
    """Minimal OpenAI-compatible chat completions client with tool calling."""

    def __init__(self, *, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.base_url = (base_url or settings.ai_base_url).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.ai_api_key
        self.model = model or settings.ai_model
        self.timeout = settings.ai_timeout_seconds
        self._max_retries = 3

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {"model": self.model, "messages": messages}
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["max_tokens"] = max_tokens

        started = time.monotonic()
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(url, headers=headers, json=payload)
            except httpx.HTTPError as exc:
                last_error = exc
                time.sleep(1.5 * (attempt + 1))
                continue

            if resp.status_code == 200:
                content_type = resp.headers.get("content-type", "")
                try:
                    if "text/event-stream" in content_type:
                        data = _parse_sse_json(resp.text)
                    else:
                        data = resp.json()
                except (ValueError, AIProviderError) as exc:
                    raise AIProviderError(
                        "Penyedia AI tidak mengembalikan data percakapan yang valid."
                    ) from exc

                latency_ms = (time.monotonic() - started) * 1000
                try:
                    message = data["choices"][0]["message"]
                except (KeyError, IndexError) as exc:
                    raise AIProviderError("Respons penyedia AI tidak valid.") from exc

                return {
                    "message": message,
                    "latency_ms": latency_ms,
                    "raw": data,
                }

            # Retry transient upstream/router errors (429, 5xx).
            if resp.status_code in {429, 500, 502, 503, 504} and attempt < self._max_retries - 1:
                last_error = AIProviderError(
                    f"Penyedia AI mengembalikan status {resp.status_code}; mencoba ulang."
                )
                time.sleep(1.5 * (attempt + 1))
                continue

            raise AIProviderError(
                f"Penyedia AI mengembalikan status {resp.status_code}: {resp.text[:500]}"
            )

        raise AIProviderError(f"Penyedia AI tidak dapat dihubungi: {last_error}")

    def chat_stream(self, messages: list[dict], tools: list[dict] | None = None, on_delta=None) -> dict:
        """Consume OpenAI-compatible streaming chunks and rebuild one message.

        Text chunks are forwarded immediately; fragmented tool calls are merged
        so Hermes Core keeps the same provider-independent contract.
        """
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload: dict = {"model": self.model, "messages": messages, "stream": True}
        if tools:
            payload["tools"] = tools
        started = time.monotonic()
        content_parts: list[str] = []
        calls: dict[int, dict] = {}
        last_error: Exception | None = None
        for attempt in range(self._max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    with client.stream("POST", url, headers=headers, json=payload) as resp:
                        if resp.status_code in {429, 500, 502, 503, 504} and attempt < self._max_retries - 1:
                            last_error = AIProviderError(
                                f"Penyedia AI mengembalikan status {resp.status_code}; mencoba ulang."
                            )
                            resp.read()
                            time.sleep(1.5 * (attempt + 1))
                            continue
                        if resp.status_code >= 400:
                            raise AIProviderError(f"Penyedia AI mengembalikan status {resp.status_code}: {resp.read()[:500]!r}")
                        for line in resp.iter_lines():
                            if not line.startswith("data:"):
                                continue
                            raw = line[5:].strip()
                            if not raw or raw == "[DONE]":
                                continue
                            try:
                                chunk = json.loads(raw)
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                            except (ValueError, IndexError):
                                continue
                            text = delta.get("content") or ""
                            if text:
                                content_parts.append(text)
                                if on_delta:
                                    on_delta(text)
                            for tc in delta.get("tool_calls") or []:
                                idx = int(tc.get("index", 0))
                                merged = calls.setdefault(idx, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                                if tc.get("id"):
                                    merged["id"] += tc["id"]
                                fn = tc.get("function") or {}
                                merged["function"]["name"] += fn.get("name") or ""
                                merged["function"]["arguments"] += fn.get("arguments") or ""
                        break
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._max_retries - 1 and not content_parts and not calls:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise AIProviderError(f"Penyedia AI tidak dapat dihubungi: {exc}") from exc
        else:
            raise AIProviderError(f"Penyedia AI tidak dapat dihubungi: {last_error}")
        message: dict = {"role": "assistant", "content": "".join(content_parts) or None}
        if calls:
            message["tool_calls"] = [calls[i] for i in sorted(calls)]
        return {"message": message, "latency_ms": (time.monotonic() - started) * 1000, "raw": None}

    def tools_schema(self) -> list[dict]:
        """Schema descriptors for the tools exposed by the Tool Gateway."""
        from ..tools.registry import get_tools_schema

        return get_tools_schema()

    def tool_result_message(self, call_id: str, content: str, name: str = "") -> dict:
        msg: dict = {
            "role": "tool",
            "tool_call_id": call_id,
            "content": content,
        }
        if name:
            msg["name"] = name
        return msg


def get_provider() -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider()
