#!/bin/bash
# Demo 2 file watcher — wakes on inotify write events on .sre-demo2-trigger.
# Spawns: claude -p DEMO2_AGENT.md when a real issueId appears.

TRIGGER_FILE="/home/kiu/bigdem/versus/.sre-demo2-trigger"
TRIGGER_DIR="$(dirname "$TRIGGER_FILE")"
TRIGGER_NAME="$(basename "$TRIGGER_FILE")"
LOCK_FILE="/tmp/demo2-agent.lock"
LOG_FILE="/home/kiu/pulse-demo2-agent.log"
WORKDIR="/home/kiu/bigdem/versus"
CLAUDE="/home/kiu/.local/bin/claude"

fire_if_triggered() {
  [ -f "$TRIGGER_FILE" ] || return

  ISSUE_ID=$(jq -r '.issueId // empty' "$TRIGGER_FILE" 2>/dev/null)
  STATUS=$(jq -r '.status // empty'   "$TRIGGER_FILE" 2>/dev/null)

  # Fallback: raw UUID string written directly by relay
  if [ -z "$ISSUE_ID" ]; then
    RAW=$(tr -d '[:space:]' < "$TRIGGER_FILE")
    if echo "$RAW" | grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'; then
      ISSUE_ID="$RAW"
      echo "{\"issueId\":\"$ISSUE_ID\"}" > "$TRIGGER_FILE"
      echo "[$(date)] Trigger normalised from raw UUID to JSON — issueId=$ISSUE_ID" >> "$LOG_FILE"
    fi
  fi

  # Fire only when issueId is present, not the test placeholder, and not already picked up
  [ -n "$ISSUE_ID" ] && [ "$ISSUE_ID" != "isue2jose" ] && [ -z "$STATUS" ] || return

  echo "[$(date)] Trigger detected — issueId=$ISSUE_ID" >> "$LOG_FILE"

  (
    flock -n 200 || { echo "[$(date)] Already running, skipping." >> "$LOG_FILE"; exit 1; }

    cd "$WORKDIR"
    source ~/.config/pulse-sre/env 2>/dev/null

    RUN_LOG=$(mktemp /tmp/demo2-run-XXXXXX.log)

    echo "[$(date)] Launching DEMO2_AGENT..." >> "$LOG_FILE"
    "$CLAUDE" --dangerously-skip-permissions \
          --append-system-prompt "$(cat "$WORKDIR/DEMO2_AGENT.md")" \
          -p "Execute your SRE remediation workflow now. Begin with Step 1." \
          --output-format text > "$RUN_LOG" 2>&1
    EXIT_CODE=$?

    cat "$RUN_LOG" >> "$LOG_FILE"

    if grep -qi "credit balance is too low\|your credit balance\|billing\|payment" "$RUN_LOG"; then
      echo "[$(date)] BILLING ERROR — clearing trigger. Top up at console.anthropic.com" >> "$LOG_FILE"
      echo '{}' > "$TRIGGER_FILE"
    elif grep -qi "authentication\|invalid api key\|api key" "$RUN_LOG" && [ $EXIT_CODE -ne 0 ]; then
      echo "[$(date)] AUTH ERROR — clearing trigger. Check ANTHROPIC_API_KEY in ~/.config/pulse-sre/env" >> "$LOG_FILE"
      echo '{}' > "$TRIGGER_FILE"
    elif [ $EXIT_CODE -eq 0 ]; then
      echo '{}' > "$TRIGGER_FILE"
      echo "[$(date)] Agent succeeded — trigger cleared." >> "$LOG_FILE"
    else
      echo "[$(date)] Agent failed (exit $EXIT_CODE) — trigger NOT cleared, will retry on next write." >> "$LOG_FILE"
    fi

    rm -f "$RUN_LOG"
  ) 200>"$LOCK_FILE"
}

echo "[$(date)] Demo2 watcher started (inotifywait)" >> "$LOG_FILE"

# Check once at startup in case a trigger was written while the service was down
fire_if_triggered

# Wait for writes to the trigger file, then check and fire.
# || true prevents the while loop from exiting if inotifywait errors/restarts.
while true; do
  /usr/bin/inotifywait -e close_write,moved_to,create -q \
    --include "$TRIGGER_NAME" "$TRIGGER_DIR" || true
  fire_if_triggered
done
