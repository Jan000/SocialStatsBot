#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Host wrapper script for Social-Stats-Bot
#
# Runs the bot via Docker Compose.  When the bot exits with code
# 42 (triggered by /admin update), the script pulls the latest
# code, rebuilds the container, and restarts automatically.
#
# Usage:  ./update.sh          (runs in foreground)
#         nohup ./update.sh &  (runs in background)
# ──────────────────────────────────────────────────────────────

set -euo pipefail
cd "$(dirname "$0")"

UPDATE_EXIT_CODE=42

while true; do
    echo "▶ Starting bot …"
    docker compose up --build
    EXIT_CODE=$?

    if [ "$EXIT_CODE" -eq "$UPDATE_EXIT_CODE" ]; then
        echo "🔄 Update requested – pulling latest changes …"
        git pull
        echo "🔨 Rebuilding and restarting …"
        # Loop continues → docker compose up --build at the top
    else
        echo "⏹ Bot exited with code $EXIT_CODE – stopping."
        exit "$EXIT_CODE"
    fi
done