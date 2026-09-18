from rapiin.redaction import redact_text, redact_value


def test_credentials_are_redacted_before_provider_payload():
    text = "password=Rahasia123 token:abc123456789012345 Bearer eyJhbGciOiJub25l.abcdef123456"
    result = redact_text(text)
    assert "Rahasia123" not in result
    assert "abc123456789012345" not in result
    assert "eyJhbGci" not in result
    assert result.count("[REDACTED]") == 3
    assert redact_value({"api_key": "secret", "nested": ["token=abcdef1234567890"]}) == {
        "api_key": "[REDACTED]", "nested": ["token=[REDACTED]"]
    }


def test_credentials_cannot_be_saved_as_user_memory(client):
    registration = client.post("/api/auth/register", json={
        "email": "memory-secret@example.com", "name": "Memory", "password": "Password123!",
        "device_name": "PC", "os": "Test", "agent_version": "1.0",
    }).json()
    headers = {"Authorization": f"Bearer {registration['token']}"}
    assert client.post("/api/user/memory", json={"key": "api_key", "value": "hello"}, headers=headers).status_code == 422
    assert client.post("/api/user/memory", json={"key": "preference", "value": "token=abcdef1234567890"}, headers=headers).status_code == 422
