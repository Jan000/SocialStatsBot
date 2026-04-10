#!/bin/bash
# ──────────────────────────────────────────────────────────────
# Show status of the Social-Stats-Bot
#
# Usage:
#   bash status.sh          # Snapshot: service + container status
#   bash status.sh live     # Live logs (Ctrl+C to stop)
# ──────────────────────────────────────────────────────────────

cd "$(dirname "$0")"

SERVICE_NAME="social-stats-bot"
CONTAINER_NAME="social-stats-bot"

# ── Colours ──────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Colour

# ── Live mode ────────────────────────────────────────────────
if [ "$1" = "live" ]; then
    echo -e "📡 Live-Logs (Ctrl+C zum Beenden):\n"
    docker compose logs -f --tail 50
    exit 0
fi

# ── Snapshot mode ────────────────────────────────────────────
echo "═══════════════════════════════════════════"
echo "  Social-Stats-Bot – Status"
echo "═══════════════════════════════════════════"
echo ""

# 1) Docker container status
echo "── Docker Container ──────────────────────"
if docker inspect "$CONTAINER_NAME" > /dev/null 2>&1; then
    STATE=$(docker inspect --format '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null)
    HEALTH=$(docker inspect --format '{{.State.Health.Status}}' "$CONTAINER_NAME" 2>/dev/null)
    STARTED=$(docker inspect --format '{{.State.StartedAt}}' "$CONTAINER_NAME" 2>/dev/null)
    RESTARTS=$(docker inspect --format '{{.RestartCount}}' "$CONTAINER_NAME" 2>/dev/null)

    case "$STATE" in
        running)  echo -e "   Status:    ${GREEN}● Läuft${NC}" ;;
        exited)   echo -e "   Status:    ${RED}● Gestoppt${NC}" ;;
        restarting) echo -e "   Status:  ${YELLOW}● Neustart${NC}" ;;
        *)        echo -e "   Status:    ${YELLOW}● $STATE${NC}" ;;
    esac

    if [ -n "$STARTED" ] && [ "$STATE" = "running" ]; then
        echo "   Gestartet: $STARTED"
    fi
    if [ -n "$RESTARTS" ] && [ "$RESTARTS" != "0" ]; then
        echo "   Neustarts: $RESTARTS"
    fi
else
    echo -e "   Status:    ${RED}● Container nicht gefunden${NC}"
fi
echo ""

# 2) Systemd service status (if installed)
echo "── Systemd Service ───────────────────────"
if systemctl list-unit-files "$SERVICE_NAME.service" > /dev/null 2>&1 && \
   systemctl list-unit-files | grep -q "$SERVICE_NAME"; then
    IS_ENABLED=$(systemctl is-enabled "$SERVICE_NAME" 2>/dev/null)
    IS_ACTIVE=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null)

    case "$IS_ACTIVE" in
        active)   echo -e "   Status:    ${GREEN}● Aktiv${NC}" ;;
        inactive) echo -e "   Status:    ${YELLOW}● Inaktiv${NC}" ;;
        failed)   echo -e "   Status:    ${RED}● Fehlgeschlagen${NC}" ;;
        *)        echo -e "   Status:    ${YELLOW}● $IS_ACTIVE${NC}" ;;
    esac

    case "$IS_ENABLED" in
        enabled)  echo -e "   Autostart: ${GREEN}Aktiviert${NC}" ;;
        disabled) echo -e "   Autostart: ${YELLOW}Deaktiviert${NC}" ;;
        *)        echo -e "   Autostart: $IS_ENABLED" ;;
    esac
else
    echo "   Nicht installiert (sudo bash install-service.sh)"
fi
echo ""

# 3) Recent logs
echo "── Letzte Logs ───────────────────────────"
docker compose logs --tail 15 --no-log-prefix 2>/dev/null || echo "   Keine Logs verfügbar."
echo ""
echo "═══════════════════════════════════════════"
echo "Tipp: bash status.sh live  für Live-Logs"
