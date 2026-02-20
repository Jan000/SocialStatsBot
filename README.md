# NirukiSocialStats Discord Bot

Ein Discord-Bot, der YouTube-Abonnenten und Twitch-Follower-Zahlen trackt und als Discord-Rollen anzeigt.

## Features

- **YouTube & Twitch Account-Verknüpfung** – Admins verknüpfen Discord-User mit YouTube/Twitch Accounts
- **Multi-Account-Support** – Ein User kann mehrere Accounts pro Plattform haben
- **Automatische Rollen** – Jeder Account bekommt eine eigene Rolle mit Name und Zahl (z.B. `[YouTube] Niruki - 1.234 Abos`)
- **Scoreboards** – Top-N Leaderboards in konfigurierbaren Channels, auto-aktualisiert
- **Benutzerdefinierte Rollen-Designs** – Eigene Rollen-Muster je Abo-Bereich oder exakter Zahl
- **Vollständige Konfiguration per Discord-Commands** – Intervalle, Channels, Scoreboard-Größe, Rollen-Design
- **Historien-Tracking** – Alle Änderungen dedupliziert in SQLite gespeichert
- **Flexible Eingabe** – YouTube-URLs, @Handles, Channel-IDs sowie Twitch-URLs und Login-Namen
- **Discord-native Permissions** – Zugriff wird über Server-Einstellungen > Integrationen gesteuert

## Setup

1. **Python 3.11+** erforderlich
2. Dependencies installieren:
   ```bash
   pip install -r requirements.txt
   ```
3. `config.toml.example` nach `config.toml` kopieren und ausfüllen:
   - Discord Bot Token
   - YouTube API Key
   - Twitch Client ID & Secret
4. Bot starten:
   ```bash
   python main.py
   ```
5. **Berechtigungen konfigurieren**: In Discord unter Server-Einstellungen > Integrationen den Zugriff auf die Bot-Commands konfigurieren.

## Slash Commands

### Admin-Commands (`/admin ...`)
Standardmäßig auf Server-Administratoren beschränkt. Zugriff kann in Server-Einstellungen > Integrationen angepasst werden.

| Command | Beschreibung |
|---|---|
| `/admin link_youtube <user> <channel_input>` | YouTube-Kanal verknüpfen (URL, @Handle oder ID) |
| `/admin link_twitch <user> <channel_input>` | Twitch-Account verknüpfen (URL oder Login-Name) |
| `/admin unlink <user> <platform> <account_name>` | Bestimmten Account entfernen |
| `/admin accounts <user>` | Alle verknüpften Accounts eines Users anzeigen |
| `/admin force_refresh [platform]` | Sofortiger Refresh aller Accounts |
| `/admin history <user> <platform> <account_name>` | Abo-/Follower-Verlauf anzeigen |

### Einstellungen (`/settings ...`)
| Command | Beschreibung |
|---|---|
| `/settings show` | Alle Einstellungen anzeigen |
| `/settings scoreboard_channel <platform> <channel>` | Scoreboard-Channel setzen |
| `/settings scoreboard_size <platform> <size>` | Anzahl Einträge im Scoreboard (1-50) |
| `/settings refresh_interval <platform> <seconds>` | Refresh-Intervall in Sekunden (60-86400) |
| `/settings role_pattern <platform> <pattern>` | Rollen-Pattern (`{name}` und `{count}` = Platzhalter) |
| `/settings role_color <platform> <hex_color>` | Standard-Rollen-Farbe |
| `/settings role_design <platform> ...` | Benutzerdefiniertes Design für Bereich |
| `/settings role_design_exact <platform> ...` | Design für exakte Zahl |
| `/settings list_role_designs <platform>` | Alle Designs anzeigen |
| `/settings remove_role_design <design_id>` | Design entfernen |

## Rollen-System

Rollen werden automatisch erstellt und zugewiesen. Jeder verknüpfte Account bekommt seine eigene Rolle:
- YouTube: `[YouTube] {name} - {count} Abos` (z.B. `[YouTube] Niruki - 1.234 Abos`)
- Twitch: `[Twitch] {name} - {count} Follower` (z.B. `[Twitch] Niruki - 567 Follower`)

Platzhalter im Pattern:
- `{name}` – Account-/Kanal-Name
- `{count}` – Aktuelle Zahl (mit Punkt-Tausendertrennung)

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
│   │   ├── admin.py         # Admin-Commands (Link/Unlink/Accounts/History)
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
