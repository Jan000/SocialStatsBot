#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Host wrapper script for Social-Stats-Bot
#
# Runs the bot via Docker Compose in the foreground.  When the
# container exits with code 42 (triggered by /admin update), the
# script pulls the latest code, rebuilds the image, and restarts.
# Any other exit code stops the script.
#
# Usage:  ./update.sh          (runs in foreground)
#         nohup ./update.sh &  (runs in background)
# ──────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

UPDATE_EXIT_CODE=42

while true; do
    echo "▶ Starting bot …"

    # Run in foreground; capture exit code (do NOT use set -e here,
    # because a non-zero exit is expected on /admin update).
    docker compose up --build --abort-on-container-exit --exit-code-from bot || true
    EXIT_CODE=$(docker compose ps bot --format '{{.ExitCode}}' 2>/dev/null || echo "1")

    echo "Container exited with code $EXIT_CODE."

    if [ "$EXIT_CODE" -eq "$UPDATE_EXIT_CODE" ]; then
        echo "🔄 Update requested – pulling latest changes …"
        git pull
        echo "🔨 Rebuilding and restarting …"
        docker compose down
        # Loop continues → docker compose up --build at the top
    else
        echo "⏹ Bot exited with code $EXIT_CODE – stopping."
        docker compose down
        exit "$EXIT_CODE"
    fi
done