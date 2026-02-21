#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Host wrapper script for Social-Stats-Bot
#
# Runs the bot via Docker Compose in the foreground.  When the
# container exits with code 42 (triggered by /admin update), the
# script pulls the latest code, rebuilds the image, and restarts.
#
# Progress is posted back to Discord as a live log by editing the
# original ephemeral interaction response via the Discord webhook
# (scripts/discord_notify.py).  The full log is written to
# data/update.log so the bot can show a final embed on restart.
#
# Usage:  bash update.sh          (runs in foreground)
#         nohup bash update.sh &  (runs in background)
# ──────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

UPDATE_EXIT_CODE=42
LOG_FILE="data/update.log"

# ── Helpers ──────────────────────────────────────────────────

notify() {
    python3 scripts/discord_notify.py "$@" 2>/dev/null || true
}

# Run a command, appending its output to LOG_FILE, while updating
# the Discord message every 5 seconds with the latest log tail.
run_live() {
    local label="$1"; shift
    "$@" >> "$LOG_FILE" 2>&1 &
    local pid=$!
    while kill -0 "$pid" 2>/dev/null; do
        notify "$label" "$LOG_FILE"
        sleep 5
    done
    wait "$pid"
    return $?
}

# ── Main loop ────────────────────────────────────────────────

while true; do
    echo "▶ Starting bot …"

    # --exit-code-from bot makes docker compose exit with the
    # container's exit code.  Capture it directly from $?.
    docker compose up --build --abort-on-container-exit --exit-code-from bot
    EXIT_CODE=$?

    echo "Container exited with code $EXIT_CODE."

    if [ "$EXIT_CODE" -eq "$UPDATE_EXIT_CODE" ]; then
        mkdir -p data
        printf '=== Update gestartet: %s ===\n\n' "$(date '+%d.%m.%Y %H:%M:%S')" > "$LOG_FILE"

        # ── Step 1: git pull ─────────────────────────────────
        echo "── git pull ──────────────────────────" >> "$LOG_FILE"
        notify "🔄 git pull läuft …"
        if run_live "🔄 git pull läuft …" git pull; then
            echo "✅ git pull erfolgreich" >> "$LOG_FILE"
            GIT_OK=1
        else
            echo "❌ git pull fehlgeschlagen" >> "$LOG_FILE"
            echo "EXIT=error" >> "$LOG_FILE"
            GIT_OK=0
        fi
        echo "" >> "$LOG_FILE"

        # ── Step 2: docker compose build ─────────────────────
        echo "── docker compose build ──────────────" >> "$LOG_FILE"
        if [ "$GIT_OK" -eq 1 ]; then
            BUILD_LABEL="✅ Git pull abgeschlossen. 🔄 Docker build läuft …"
        else
            BUILD_LABEL="⚠️ Git pull fehlgeschlagen. 🔄 Docker build läuft …"
        fi
        if run_live "$BUILD_LABEL" docker compose build; then
            echo "✅ Build erfolgreich" >> "$LOG_FILE"
        else
            echo "❌ Build fehlgeschlagen" >> "$LOG_FILE"
            echo "EXIT=error" >> "$LOG_FILE"
        fi
        echo "" >> "$LOG_FILE"

        printf '=== Update abgeschlossen: %s ===\n' "$(date '+%d.%m.%Y %H:%M:%S')" >> "$LOG_FILE"

        notify "✅ Build abgeschlossen. 🔄 Bot startet neu …"

        docker compose down
        # Loop continues → docker compose up --build at the top
    else
        echo "⏹ Bot exited with code $EXIT_CODE – stopping."
        docker compose down
        exit "$EXIT_CODE"
    fi
done
