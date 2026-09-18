# Desktop Agent Startup Test Matrix

Run each row on clean macOS and Windows machines using the versioned Python wheel installed from the terminal. Attach command output, OS version, artifact checksum, timestamps, and a screenshot of the device health page to the release record.

| Scenario | Commands / action | Required evidence |
|---|---|---|
| Clean install | Install the checksum-verified wheel with `uv tool install` or `pipx install`; run `rapiin --help` | Published checksum matches and command is available |
| Pair | `rapiin-agent setup --server https://... --workspace ...` | Device appears healthy with expected capabilities |
| Manual | `rapiin-agent autostart off`; `rapiin-agent run` | Jobs execute only while foreground agent runs |
| Auto | `rapiin-agent autostart on`; `rapiin-agent startup-probe record` | OS service entry exists |
| Reboot | Reboot; then `rapiin-agent startup-probe verify` | New boot ID, service present, heartbeat/poll succeeds |
| Disable | `rapiin-agent autostart off`; reboot | Agent stays offline until manually started |
| Reconnect | Interrupt network, restore it | Agent reconnects without duplicate file mutation |
| Revoke/re-pair | Revoke in Settings; verify old agent fails; run setup again | Old key rejected and new key works |
| Upgrade | Verify checksum; `rapiin-agent upgrade --wheel ...` | Version changes; configuration remains usable |
| Uninstall | `rapiin-agent uninstall`; remove package | Service and local credentials are absent |
