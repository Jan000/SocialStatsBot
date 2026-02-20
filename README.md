# NirukiSocialStats Discord Bot

Ein Discord-Bot, der YouTube-Abonnenten und Twitch-Follower-Zahlen trackt und als Discord-Rollen anzeigt.

## Features

- **YouTube & Twitch Account-Verknüpfung** – Admin verknüpft Discord-User mit YouTube/Twitch Accounts
- **Automatische Rollen** – Jeder verknüpfte User bekommt eine Rolle mit seiner aktuellen Abo-/Follower-Zahl
- **Scoreboards** – Top-N Leaderboards in konfigurierbaren Channels, auto-aktualisiert
- **Benutzerdefinierte Rollen-Designs** – Eigene Rollen-Muster je Abo-Bereich oder exakter Zahl
- **Vollständige Konfiguration per Discord-Commands** – Intervalle, Channels, Scoreboard-Größe, Rollen-Design
- **Historien-Tracking** – Alle Änderungen mit Zeitstempel in SQLite gespeichert

## Setup

1. **Python 3.11+** erforderlich
2. Dependencies installieren:
   ```bash
   pip install -r requirements.txt
   ```
3. `config.toml.example` nach `config.toml` kopieren und ausfüllen:
   - Discord Bot Token
   - Admin User ID
   - YouTube API Key
   - Twitch Client ID & Secret
4. Bot starten:
   ```bash
   python main.py
   ```

## Slash Commands

### Admin-Commands (nur Admin-User)
| Command | Beschreibung |
|---|---|
| `/link_youtube` | Discord-User mit YouTube-Kanal verknüpfen |
| `/link_twitch` | Discord-User mit Twitch-Account verknüpfen |
| `/unlink` | Verknüpfung entfernen |
| `/list_accounts` | Alle verknüpften Accounts anzeigen |
| `/force_refresh` | Sofortigen Refresh für einen User erzwingen |
| `/refresh_status` | Refresh-Status aller Accounts anzeigen |
| `/history` | Abo-/Follower-Verlauf anzeigen |

### Einstellungen (nur Admin-User)
| Command | Beschreibung |
|---|---|
| `/show_settings` | Alle Einstellungen anzeigen |
| `/set_scoreboard_channel` | Scoreboard-Channel setzen |
| `/set_scoreboard_size` | Anzahl User im Scoreboard (1-50) |
| `/set_refresh_interval` | Refresh-Intervall in Sekunden (60-86400) |
| `/set_role_pattern` | Standard-Rollen-Pattern (`{count}` = Platzhalter) |
| `/set_role_color` | Standard-Rollen-Farbe (Hex) |
| `/add_role_design` | Benutzerdefiniertes Design für Bereich/exakte Zahl |
| `/list_role_designs` | Alle benutzerdefinierten Designs anzeigen |
| `/remove_role_design` | Design entfernen |

## Rollen-System

Rollen werden automatisch erstellt und zugewiesen. Das Format:
- YouTube: `[YT] {Pattern}` (z.B. `[YT] 1,234 YouTube Abos`)
- Twitch: `[TW] {Pattern}` (z.B. `[TW] 567 Twitch Follower`)

`{count}` im Pattern wird durch die aktuelle Zahl ersetzt.

Nicht mehr benötigte Rollen werden automatisch gelöscht.

## Projektstruktur

```
├── main.py                  # Entry point
├── config.toml              # Bot-Konfiguration (nicht im Git)
├── config.toml.example      # Beispiel-Konfiguration
├── requirements.txt         # Python dependencies
├── bot/
│   ├── __init__.py
│   ├── bot.py               # Haupt-Bot-Klasse
│   ├── database.py          # SQLite Datenbank-Layer
│   ├── roles.py             # Rollen-Management
│   ├── scoreboard.py        # Scoreboard-Embeds
│   ├── cogs/
│   │   ├── __init__.py
│   │   ├── admin.py         # Admin-Commands (Link/Unlink/Status)
│   │   ├── settings.py      # Einstellungs-Commands
│   │   └── refresh.py       # Background-Refresh-Loop
│   └── services/
│       ├── __init__.py
│       ├── youtube.py        # YouTube Data API v3
│       └── twitch.py         # Twitch Helix API
├── data/                    # SQLite DB (auto-erstellt)
└── docs/
    ├── status.md            # Entwicklungs-Fortschritt
    └── todos.md             # Offene Aufgaben
```
