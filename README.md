# Social-Stats-Bot

Ein Discord-Bot, der YouTube-Abonnenten und Twitch-Follower-Zahlen trackt, als Discord-Rollen anzeigt und Scoreboards pflegt.

## Features

- **YouTube & Twitch Account-Verknüpfung** – Multi-Account-Support (mehrere Accounts pro User & Plattform)
- **Automatische Rollen** – Jeder Account bekommt eine eigene Rolle (z.B. `[YouTube] MeinKanal - 1.234 Abos`)
- **Scoreboards** – Leaderboards in konfigurierbaren Channels, auto-aktualisiert (alle Accounts, auto-split bei langen Listen)
- **Count-Channel** – Ein Channel pro Plattform, dessen Name bei jedem Refresh auf die aktuelle Gesamtzahl aktualisiert wird (z.B. `📺 1.234 YouTube Abos`)
- **Statistik-Commands** – Wachstumsanalyse über 7/30/90 Tage
- **Benutzerdefinierte Rollen-Designs** – Eigene Rollen-Muster je Abo-Bereich oder exakter Zahl
- **Autocomplete** – Account-Namen und Rollen-Design-IDs werden beim Tippen vorgeschlagen
- **Pagination** – Blättern durch lange Listen (Historie, Accounts) per Discord-Buttons
- **Rate-Limiting** – Token-Bucket Rate-Limiter für YouTube- und Twitch-API-Anfragen
- **Twitch EventSub** – Optionale WebSocket-Integration für Echtzeit-Channel-Updates
- **Docker-Support** – Deployment via `docker compose up`
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

### Docker

```bash
docker compose up -d
```

`data/`-Verzeichnis und `config.toml` werden als Volumes gemountet.

### Optionale Konfiguration

In `config.toml` unter `[bot]`:
- `dev_guild_id` – Guild-ID für sofortigen Slash-Command-Sync bei Entwicklung
- `enable_eventsub = true` – Twitch EventSub WebSocket für Echtzeit-Updates aktivieren

## Slash Commands

### Admin-Commands (`/admin ...`)
Standardmäßig auf Server-Administratoren beschränkt. Zugriff kann in Server-Einstellungen > Integrationen angepasst werden.

| Command | Beschreibung |
|---|---|
| `/admin link <user> <platform> <channel_input>` | YouTube-/Twitch-Kanal verknüpfen (URL, Handle, Login oder ID) |
| `/admin unlink <user> <platform> <account_name>` | Bestimmten Account entfernen (Autocomplete) |
| `/admin accounts <user>` | Alle verknüpften Accounts eines Users anzeigen (paginiert) |
| `/admin force_refresh [platform]` | Sofortiger Refresh aller Accounts |
| `/admin history <user> <platform> <account_name>` | Abo-/Follower-Verlauf anzeigen (Autocomplete, paginiert) |

### Statistik-Commands (`/stats ...`)
| Command | Beschreibung |
|---|---|
| `/stats growth <user> <platform> <account_name> [period]` | Wachstum eines Accounts über 7/30/90 Tage (Autocomplete) |
| `/stats overview <platform> [period]` | Übersicht aller Accounts mit Wachstumsdaten |

### Einstellungen (`/settings ...`)
| Command | Beschreibung |
|---|---|
| `/settings show` | Alle Einstellungen anzeigen |
| `/settings scoreboard_channel <platform> <channel>` | Scoreboard-Channel setzen |
| `/settings scoreboard_size <platform> <size>` | Anzahl Einträge im Scoreboard (1–50) |
| `/settings refresh_interval <platform> <seconds>` | Refresh-Intervall in Sekunden (60–86400) |
| `/settings role_pattern <platform> <pattern>` | Rollen-Pattern (`{name}` und `{count}` als Platzhalter) |
| `/settings role_color <platform> <hex_color>` | Standard-Rollen-Farbe |
| `/settings role_design <platform> ...` | Benutzerdefiniertes Design für Bereich |
| `/settings role_design_exact <platform> ...` | Design für exakte Zahl |
| `/settings list_role_designs <platform>` | Alle Designs anzeigen |
| `/settings remove_role_design <design_id>` | Design entfernen (Autocomplete) |
| `/settings count_channel <platform> <channel>` | Count-Channel setzen (Voice-/Text-Channel, wird bei Refresh umbenannt) |
| `/settings count_channel_pattern <platform> <pattern>` | Count-Channel-Pattern (`{count}` als Platzhalter) |

## Rollen-System

Rollen werden automatisch erstellt und zugewiesen. Jeder verknüpfte Account bekommt seine eigene Rolle:
- YouTube: `[YouTube] {name} - {count} Abos` (z.B. `[YouTube] MeinKanal - 1.234 Abos`)
- Twitch: `[Twitch] {name} - {count} Follower` (z.B. `[Twitch] MeinKanal - 567 Follower`)

Platzhalter im Pattern:
- `{name}` – Account-/Kanal-Name
- `{count}` – Aktuelle Zahl (mit Punkt-Tausendertrennung)

Nicht mehr benötigte Rollen werden automatisch gelöscht.

## Count-Channel

Ein optionaler Voice- oder Text-Channel pro Plattform, dessen Name bei jedem Refresh auf die Gesamtzahl aller verknüpften Accounts aktualisiert wird.

- Standard-Pattern YouTube: `📺 {count} YouTube Abos`
- Standard-Pattern Twitch: `🎮 {count} Twitch Follower`
- Platzhalter: `{count}` – Gesamtzahl aller Accounts (mit Punkt-Tausendertrennung)
- Konfigurierbar über `/settings count_channel` und `/settings count_channel_pattern`

## Tests

```bash
pytest tests/ -v
```

31 Tests für Database-Layer und Role-Logic.

## Projektstruktur

```
├── main.py                  # Entry Point
├── config.toml              # Bot-Konfiguration (nicht im Git)
├── config.toml.example      # Beispiel-Konfiguration
├── requirements.txt         # Python Dependencies
├── pytest.ini               # pytest-Konfiguration
├── Dockerfile               # Docker-Image
├── docker-compose.yml       # Docker-Compose
├── bot/
│   ├── bot.py               # Haupt-Bot-Klasse (SocialStatsBot)
│   ├── database.py          # SQLite Datenbank-Layer (async, mit Migrationen)
│   ├── roles.py             # Rollen-Management
│   ├── scoreboard.py        # Scoreboard-Embeds & Count-Channel-Rename
│   ├── pagination.py        # PaginationView (Discord-Buttons)
│   ├── ratelimit.py         # Token-Bucket Rate-Limiter
│   ├── cogs/
│   │   ├── admin.py         # Admin-Commands (Link/Unlink/Accounts/History)
│   │   ├── settings.py      # Einstellungs-Commands
│   │   ├── stats.py         # Statistik-Commands (Growth/Overview)
│   │   └── refresh.py       # Background-Refresh-Loop + EventSub Bootstrap
│   └── services/
│       ├── youtube.py        # YouTube Data API v3 (rate-limited)
│       ├── twitch.py         # Twitch Helix API + OAuth (rate-limited)
│       └── eventsub.py       # Twitch EventSub WebSocket-Client
├── tests/
│   ├── test_database.py     # 20 Database-Tests
│   └── test_roles.py        # 11 Role-Logic-Tests
├── data/                    # SQLite DB (auto-erstellt)
└── docs/
    └── todos.md             # Aufgaben
```

## Status

**Phase:** Feature-Complete

Alle geplanten Features sind implementiert:
- Vollständige YouTube & Twitch API-Integration mit Rate-Limiting
- Multi-Account-Verknüpfung, automatische Rollen, Scoreboards, Count-Channels
- Statistik-Commands mit Wachstumsanalyse
- Background-Refresh mit konfigurierbarem Intervall
- Optionale Twitch EventSub WebSocket-Integration
- 31 Unit-Tests (Database + Role-Logic)
- Docker-Support für einfaches Deployment

### Architektur-Entscheidungen

| Entscheidung | Begründung |
|---|---|
| discord.py 2.x Slash-Commands | Moderner Standard, bessere UX |
| aiosqlite | Async-kompatibel mit discord.py event loop |
| Discord-native Permissions | Flexibler als eigenes Admin-System |
| Multi-Account UNIQUE Constraint | Ein User kann mehrere YT/TW Accounts haben |
| History-Deduplizierung | Reduziert DB-Größe bei gleichbleibendem Count |
| Token-Bucket Rate-Limiting | Respektiert API-Quotas |
| EventSub WebSocket (optional) | Echtzeit-Updates ohne öffentliche URL |
| Docker-Support | Einfaches Deployment mit `docker compose up` |
