"""Keep every agent test isolated from the operator's real ~/.rapiin state."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_agent_home(tmp_path, monkeypatch):
    from rapiin_agent import config

    config_dir = tmp_path / ".rapiin"
    monkeypatch.setattr(config, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(config, "CONFIG_FILE", config_dir / "config.json")
    monkeypatch.setattr(config, "STATE_FILE", config_dir / "state.json")
