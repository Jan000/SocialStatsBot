#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Host wrapper script for Social-Stats-Bot
#
# Runs the bot via Docker Compose in the foreground.  When the
# container exits with code 42 (triggered by /admin update), the
# script pulls the latest code, rebuilds the image, and restarts.
# The update process is logged to data/update.log so the bot can
# report the result back in Discord after restart.
#
# Usage:  ./update.sh          (runs in foreground)
#         nohup ./update.sh &  (runs in background)
# ──────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

UPDATE_EXIT_CODE=42
LOG_FILE="data/update.log"

while true; do
    echo "▶ Starting bot …"

    # Run in foreground; capture exit code (do NOT use set -e here,
    # because a non-zero exit is expected on /admin update).
    docker compose up --build --abort-on-container-exit --exit-code-from bot || true
    EXIT_CODE=$(docker compose ps bot --format '{{.ExitCode}}' 2>/dev/null || echo "1")

    echo "Container exited with code $EXIT_CODE."

    if [ "$EXIT_CODE" -eq "$UPDATE_EXIT_CODE" ]; then
        # Start logging the update process
        mkdir -p data
        echo "=== Update gestartet: $(date '+%d.%m.%Y %H:%M:%S') ===" > "$LOG_FILE"

        echo "" >> "$LOG_FILE"
        echo "── git pull ──────────────────────────" >> "$LOG_FILE"
        if git pull >> "$LOG_FILE" 2>&1; then
            echo "✅ git pull erfolgreich" >> "$LOG_FILE"
        else
            echo "❌ git pull fehlgeschlagen (exit $?)" >> "$LOG_FILE"
            echo "EXIT=error" >> "$LOG_FILE"
            echo "⚠️  git pull failed – check $LOG_FILE"
            docker compose down
            # Still try to restart with the old code
        fi

        echo "" >> "$LOG_FILE"
        echo "── docker compose build ──────────────" >> "$LOG_FILE"
        if docker compose build >> "$LOG_FILE" 2>&1; then
            echo "✅ Build erfolgreich" >> "$LOG_FILE"
        else
            echo "❌ Build fehlgeschlagen (exit $?)" >> "$LOG_FILE"
            echo "EXIT=error" >> "$LOG_FILE"
            echo "⚠️  Docker build failed – check $LOG_FILE"
        fi

        echo "" >> "$LOG_FILE"
        echo "=== Update abgeschlossen: $(date '+%d.%m.%Y %H:%M:%S') ===" >> "$LOG_FILE"

        docker compose down
        # Loop continues → docker compose up --build at the top
    else
        echo "⏹ Bot exited with code $EXIT_CODE – stopping."
        docker compose down
        exit "$EXIT_CODE"
    fi
done