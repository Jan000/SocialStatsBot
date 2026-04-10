#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Set up systemd autostart for the Social-Stats-Bot
#
# Creates a systemd service that starts the bot on boot and
# restarts it on failure.  Run with sudo.
#
# Usage:  sudo bash install-service.sh
# ──────────────────────────────────────────────────────────────

set -e

BOT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="social-stats-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

if [ "$(id -u)" -ne 0 ]; then
    echo "❌ Bitte mit sudo ausführen: sudo bash install-service.sh"
    exit 1
fi

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Social Stats Discord Bot
After=network-online.target docker.service
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${BOT_DIR}
ExecStart=/usr/bin/docker compose up -d --build
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo "✅ Systemd-Service '${SERVICE_NAME}' erstellt und aktiviert."
echo ""
echo "Befehle:"
echo "  sudo systemctl start ${SERVICE_NAME}    # Bot starten"
echo "  sudo systemctl stop ${SERVICE_NAME}     # Bot stoppen"
echo "  sudo systemctl status ${SERVICE_NAME}   # Status anzeigen"
echo "  sudo systemctl disable ${SERVICE_NAME}  # Autostart deaktivieren"
echo ""
echo "Logs:  docker compose logs -f  (im Projektverzeichnis)"
