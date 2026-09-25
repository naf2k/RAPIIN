#!/bin/sh
# Truncate RAPIIN service logs that grow past a threshold.
#
# Why not newsyslog: these logs are written by launchd via StandardOutPath /
# StandardErrorPath, so the process holds the file descriptor open. newsyslog
# rotates by rename, after which the service keeps writing to the renamed file
# and the original never comes back. Truncating in place keeps the inode, so the
# running service and launchd both stay attached.
#
# Scheduled by ~/Library/LaunchAgents/com.rapiin.logrotate.plist.

set -eu

DATA_DIR="${RAPIIN_DATA_DIR:-/Users/haimac/orca/projects/rapiin/server/data}"
MAX_BYTES="${RAPIIN_LOG_MAX_BYTES:-5242880}"   # 5 MiB
KEEP_LINES="${RAPIIN_LOG_KEEP_LINES:-2000}"

[ -d "$DATA_DIR" ] || exit 0

for log in "$DATA_DIR"/*.log; do
    [ -f "$log" ] || continue
    size=$(wc -c < "$log" | tr -d ' ')
    [ "$size" -gt "$MAX_BYTES" ] || continue

    tmp="$log.rotate.$$"
    tail -n "$KEEP_LINES" "$log" > "$tmp"
    # `cat >` truncates in place instead of replacing the file.
    cat "$tmp" > "$log"
    rm -f "$tmp"
    echo "truncated $log (${size} -> $(wc -c < "$log" | tr -d ' ') bytes)"
done
