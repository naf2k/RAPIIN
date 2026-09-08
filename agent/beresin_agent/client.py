"""HTTP client for the Desktop Agent -> BERESIN server."""
from __future__ import annotations

import httpx

from .config import DEFAULT_SERVER


class AgentAPI:
    def __init__(self, server_url: str | None = None):
        self.base = (server_url or DEFAULT_SERVER).rstrip("/")

    def _post(self, path: str, body: dict, timeout: float = 30.0) -> dict:
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(f"{self.base}{path}", json=body)
        except httpx.HTTPError as exc:
            raise ConnectionError(f"Tidak dapat terhubung ke server: {exc}") from exc
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise ConnectionError(f"Server menolak permintaan ({resp.status_code}): {detail}")
        return resp.json()

    def login(self, email: str, password: str) -> dict:
        return self._post("/api/auth/login", {"email": email, "password": password})

    def register_device(self, token: str, device_name: str, os_name: str, version: str, capabilities: list[str] | None = None, workspace_root: str | None = None, allowed_roots: list[str] | None = None) -> dict:
        return self._post_with_token(
            "/api/auth/register-device",
            {"device_name": device_name, "os": os_name, "agent_version": version, "capabilities": capabilities or [], "workspace_root": workspace_root, "allowed_roots": allowed_roots},
            token,
        )

    def _post_with_token(self, path: str, body: dict, token: str) -> dict:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{self.base}{path}",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code >= 400:
            raise ConnectionError(f"Server menolak permintaan ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def poll(self, device_id: int, device_key: str) -> dict:
        from .config import allowed_roots, workspace_root

        return self._post(
            "/api/agent/poll",
            {"device_id": device_id, "device_key": device_key, "workspace_root": str(workspace_root()), "allowed_roots": [str(root) for root in allowed_roots()]},
        )

    def report(self, job_id: int, device_id: int, device_key: str, status: str, result: dict | None = None, error: str | None = None) -> dict:
        return self._post(
            "/api/agent/result",
            {
                "job_id": job_id,
                "device_id": device_id,
                "device_key": device_key,
                "status": status,
                "result": result,
                "error": error,
            },
        )

    def heartbeat(self, device_id: int, device_key: str) -> dict:
        return self._post("/api/auth/heartbeat", {"device_key": device_key})

    def renew_lease(self, job_id: int, device_id: int, device_key: str) -> dict:
        return self._post("/api/agent/lease/renew", {"job_id": job_id, "device_id": device_id, "device_key": device_key})
