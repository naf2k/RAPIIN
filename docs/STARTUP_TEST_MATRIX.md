# Desktop Agent Startup Test Matrix

Run each row on clean macOS and Windows machines using the versioned Python wheel installed from the terminal. Attach command output, OS version, artifact checksum, timestamps, and a screenshot of the device health page to the release record.

| Scenario | Commands / action | Required evidence |
|---|---|---|
| Clean install | Install the checksum-verified wheel with `uv tool install` or `pipx install`; run `beresin --help` | Published checksum matches and command is available |
| Pair | `beresin-agent setup --server https://... --workspace ...` | Device appears healthy with expected capabilities |
| Manual | `beresin-agent autostart off`; `beresin-agent run` | Jobs execute only while foreground agent runs |
| Auto | `beresin-agent autostart on`; `beresin-agent startup-probe record` | OS service entry exists |
| Reboot | Reboot; then `beresin-agent startup-probe verify` | New boot ID, service present, heartbeat/poll succeeds |
| Disable | `beresin-agent autostart off`; reboot | Agent stays offline until manually started |
| Reconnect | Interrupt network, restore it | Agent reconnects without duplicate file mutation |
| Revoke/re-pair | Revoke in Settings; verify old agent fails; run setup again | Old key rejected and new key works |
| Upgrade | Verify checksum; `beresin-agent upgrade --wheel ...` | Version changes; configuration remains usable |
| Uninstall | `beresin-agent uninstall`; remove package | Service and local credentials are absent |
