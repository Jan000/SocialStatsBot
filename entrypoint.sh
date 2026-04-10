#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Docker entrypoint for Social-Stats-Bot
#
# Wraps the bot process in a loop.  When the bot exits with
# code 42 (triggered by /admin update), git pull and pip install
# are run before the bot is restarted.
#
# Any other exit code causes the entrypoint to exit, letting
# Docker's restart policy handle recovery.
# ──────────────────────────────────────────────────────────────

UPDATE_EXIT_CODE=42
LOG_FILE="data/update.log"

# Ensure data directory exists
mkdir -p data

# Mark the working directory as safe for git (handles ownership
# mismatch when the source directory is bind-mounted).
git config --global --add safe.directory /app 2>/dev/null || true

while true; do
    python main.py
    EXIT_CODE=$?

    if [ "$EXIT_CODE" -ne "$UPDATE_EXIT_CODE" ]; then
        exit "$EXIT_CODE"
    fi

    # ── Update requested (exit code 42) ──────────────────────
    printf '=== Update gestartet: %s ===\n\n' \
        "$(date '+%d.%m.%Y %H:%M:%S')" > "$LOG_FILE"

    # Step 1: git pull
    echo "── git pull ──────────────────────────" >> "$LOG_FILE"
    if git pull >> "$LOG_FILE" 2>&1; then
        echo "✅ git pull erfolgreich" >> "$LOG_FILE"
    else
        echo "❌ git pull fehlgeschlagen" >> "$LOG_FILE"
        echo "EXIT=error" >> "$LOG_FILE"
    fi
    echo "" >> "$LOG_FILE"

    # Step 2: pip install (in case requirements changed)
    echo "── pip install ───────────────────────" >> "$LOG_FILE"
    if pip install --no-cache-dir -r requirements.txt >> "$LOG_FILE" 2>&1; then
        echo "✅ Dependencies aktualisiert" >> "$LOG_FILE"
    else
        echo "⚠ pip install fehlgeschlagen" >> "$LOG_FILE"
    fi
    echo "" >> "$LOG_FILE"

    echo "Bot wird neu gestartet …" >> "$LOG_FILE"
done
