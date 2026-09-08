#!/usr/bin/env python3
"""Credentialed smoke UAT for the loopback-only macOS deployment."""
from __future__ import annotations

import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "server" / "data"
BASE_URL = "http://127.0.0.1:8000"


def main() -> int:
    admin_password = (DATA / ".supervisor-password").read_text(encoding="utf-8").strip()
    user_password = (DATA / ".uat-user-password").read_text(encoding="utf-8").strip() + "Aa1"
    user_email = (DATA / ".uat-user-email").read_text(encoding="utf-8").strip()
    with httpx.Client(timeout=20) as client:
        admin = client.post(
            BASE_URL + "/api/auth/login",
            json={"email": "admin@beresin.example.com", "password": admin_password},
        )
        admin.raise_for_status()
        user = client.post(
            BASE_URL + "/api/auth/login",
            json={"email": user_email, "password": user_password},
        )
        user.raise_for_status()
        admin_headers = {"Authorization": "Bearer " + admin.json()["token"]}
        user_headers = {"Authorization": "Bearer " + user.json()["token"]}

        employees = client.get(BASE_URL + "/api/supervisor/employees", headers=admin_headers)
        employees.raise_for_status()
        devices = client.get(BASE_URL + "/api/user/devices", headers=user_headers)
        devices.raise_for_status()
        assert any(device["status"] == "ONLINE" for device in devices.json())
        assert client.get(BASE_URL + "/api/supervisor/employees", headers=user_headers).status_code == 403

        conversation = client.post(
            BASE_URL + "/api/user/conversations",
            headers=user_headers,
            json={"title": "UAT Lokal"},
        )
        conversation.raise_for_status()
        conversation_id = conversation.json()["conversation_id"]
        message = client.post(
            BASE_URL + f"/api/user/conversations/{conversation_id}/messages",
            headers=user_headers,
            json={"content": "Halo, jawab singkat: BERESIN siap."},
        )
        message.raise_for_status()
        task_id = message.json()["task_id"]
        status = "PROCESSING"
        for _ in range(60):
            task = client.get(BASE_URL + f"/api/user/tasks/{task_id}", headers=user_headers)
            task.raise_for_status()
            status = task.json()["status"]
            if status in {"COMPLETED", "FAILED"}:
                break
            time.sleep(1)
        assert status == "COMPLETED", status
        messages = client.get(
            BASE_URL + f"/api/user/conversations/{conversation_id}/messages",
            headers=user_headers,
        )
        messages.raise_for_status()
        assistant_messages = [
            item["content"].strip() for item in messages.json()
            if item["role"] == "assistant" and item["content"].strip()
        ]
        assert assistant_messages, "AI tidak menghasilkan jawaban"
        latest = assistant_messages[-1].lower()
        assert "siap" in latest, f"jawaban AI tidak sesuai kontrak: {assistant_messages[-1]}"
        assert "belum dapat menyelesaikan" not in latest, "fallback error dianggap sebagai sukses"
    print("local_uat_ok: login, RBAC, online device, supervisor view, and live AI chat passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
