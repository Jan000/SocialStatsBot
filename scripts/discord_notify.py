#!/usr/bin/env python3
"""
Edit the original /admin update interaction response (live progress).

This script is called by update.sh on the HOST to send live status
updates to Discord while the bot is offline.  It uses only the
standard library so it works without any pip packages.

Usage:
    python3 scripts/discord_notify.py "status text"
    python3 scripts/discord_notify.py "status text" data/update.log
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

PENDING = Path("data/pending_update.json")

# Discord message content limit.
MAX_CONTENT = 2000


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences and carriage-return overwrites."""
    # Strip escape sequences (colours, cursor movement, …).
    text = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)
    # Collapse \r-based progress lines (keep only last overwrite per line).
    text = re.sub(r"[^\n]*\r(?!\n)", "", text)
    return text


def main() -> None:
    if not PENDING.exists():
        return

    try:
        info = json.loads(PENDING.read_text(encoding="utf-8"))
        app_id = info["application_id"]
        token = info["interaction_token"]
    except (json.JSONDecodeError, KeyError, OSError):
        return

    # First arg: status / label text  (supports literal \n for newlines).
    content = sys.argv[1].replace("\\n", "\n") if len(sys.argv) > 1 else "🔄 Update läuft …"

    # Optional second arg: path to a log file whose tail is appended.
    if len(sys.argv) > 2:
        log_path = Path(sys.argv[2])
        if log_path.exists():
            try:
                raw = log_path.read_text(encoding="utf-8", errors="replace")
                log_text = _strip_ansi(raw).strip()
                # Reserve room for the label + code-block markers.
                budget = MAX_CONTENT - len(content) - 15
                if budget > 0:
                    if len(log_text) > budget:
                        log_text = "…" + log_text[-budget:]
                    content += f"\n```\n{log_text}\n```"
            except OSError:
                pass

    # Hard-truncate to Discord limit.
    if len(content) > MAX_CONTENT:
        content = content[: MAX_CONTENT - 1] + "…"

    url = f"https://discord.com/api/v10/webhooks/{app_id}/{token}/messages/@original"
    payload = json.dumps({"content": content}).encode()
    req = Request(
        url,
        data=payload,
        method="PATCH",
        headers={"Content-Type": "application/json"},
    )
    try:
        urlopen(req, timeout=10)
    except (URLError, OSError):
        pass  # Best-effort; don't break the update process.


if __name__ == "__main__":
    main()
