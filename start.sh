#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Start the Social-Stats-Bot with Docker Compose
#
# Usage:  bash start.sh
# ──────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

if [ ! -f config.toml ]; then
    echo "❌ config.toml nicht gefunden."
    echo "   Kopiere config.toml.example nach config.toml und trage deine Keys ein."
    exit 1
fi

echo "▶ Bot wird gestartet …"
docker compose up -d --build

if [ $? -eq 0 ]; then
    echo "✅ Bot läuft. Logs: docker compose logs -f"
else
    echo "❌ Start fehlgeschlagen."
    exit 1
fi
