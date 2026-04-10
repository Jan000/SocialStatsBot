#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Stop the Social-Stats-Bot
#
# Usage:  bash stop.sh
# ──────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

echo "⏹ Bot wird gestoppt …"
docker compose down

if [ $? -eq 0 ]; then
    echo "✅ Bot gestoppt."
else
    echo "❌ Stoppen fehlgeschlagen."
    exit 1
fi
