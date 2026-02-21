# Social-Stats-Bot

Ein Discord-Bot, der YouTube-Abonnenten, Twitch-Follower, Instagram-Follower und TikTok-Follower trackt, als Discord-Rollen anzeigt und Scoreboards pflegt.

## Features

- **4-Plattform-Support** – YouTube, Twitch, Instagram & TikTok
- **Account-Verknüpfung** – Multi-Account-Support (mehrere Accounts pro User & Plattform)
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
- **Flexible Eingabe** – YouTube-URLs, @Handles, Channel-IDs sowie Twitch-URLs, Login-Namen, Instagram-URLs/Usernames und TikTok-URLs/Usernames
- **Auto-Plattform-Erkennung** – Bei URL-Eingabe wird die Plattform automatisch erkannt (kein manuelles Auswählen nötig)
- **User-Anfragen-System** – Normale User können Link/Unlink-Anfragen stellen, Admins bestätigen per Button
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
   - (Instagram & TikTok benötigen keine API-Keys)
4. Bot starten:
   ```bash
   python main.py
   ```
5. **Berechtigungen konfigurieren**: In Discord unter Server-Einstellungen > Integrationen den Zugriff auf die Bot-Commands konfigurieren.

### Docker

```bash
# Einmaliger Start:
docker compose up -d --build

# Mit Auto-Update-Support (empfohlen):
./update.sh
```

`data/`-Verzeichnis und `config.toml` werden als Volumes gemountet.

Das Wrapper-Skript `update.sh` startet den Bot und wartet auf Exit-Code 42.
Wird `/admin update` in Discord ausgeführt, fährt der Bot herunter, das Skript
pullt die neueste Version und baut den Container automatisch neu.

### Optionale Konfiguration

In `config.toml` unter `[bot]`:
- `dev_guild_id` – Guild-ID für sofortigen Slash-Command-Sync bei Entwicklung
- `enable_eventsub = true` – Twitch EventSub WebSocket für Echtzeit-Updates aktivieren

## Slash Commands

### Admin-Commands (`/admin ...`)
Standardmäßig auf Server-Administratoren beschränkt. Zugriff kann in Server-Einstellungen > Integrationen angepasst werden.

| Command | Beschreibung |
|---|---|
| `/admin link <user> <channel_input> [platform]` | Account verknüpfen (Plattform wird aus URL erkannt oder manuell gewählt) |
| `/admin unlink <user> <platform> <account_name>` | Bestimmten Account entfernen (Autocomplete) |
| `/admin accounts <user>` | Alle verknüpften Accounts eines Users anzeigen (paginiert) |
| `/admin force_refresh [platform]` | Sofortiger Refresh aller Accounts |
| `/admin history <user> <platform> <account_name>` | Abo-/Follower-Verlauf anzeigen (Autocomplete, paginiert) |
| `/admin update` | Bot aktualisieren (git pull + rebuild). Nur Bot-Owner. |

### Statistik-Commands (`/stats ...`)
| Command | Beschreibung |
|---|---|
| `/stats growth <user> <platform> <account_name> [period]` | Wachstum eines Accounts über 7/30/90 Tage (Autocomplete) |
| `/stats overview <platform> [period]` | Übersicht aller Accounts mit Wachstumsdaten |

### Anfragen-Commands (`/request ...`)
Für alle User zugänglich. Anfragen werden im konfigurierten Anfragen-Kanal gepostet, wo Admins per Button bestätigen/ablehnen können.

| Command | Beschreibung |
|---|---|
| `/request link <channel_input> [platform]` | Anfrage zum Verknüpfen eines Accounts (Plattform wird aus URL erkannt) |
| `/request unlink <platform> <account_name>` | Anfrage zum Entfernen eines Accounts (Autocomplete) |

### Einstellungen (`/settings ...`)
| Command | Beschreibung |
|---|---|
| `/settings show` | Alle Einstellungen anzeigen |
| `/settings scoreboard_channel <platform> <channel>` | Scoreboard-Channel setzen |
| `/settings refresh_interval <platform> <seconds>` | Refresh-Intervall in Sekunden (60–86400) |
| `/settings role_pattern <platform> <pattern>` | Rollen-Pattern (`{name}` und `{count}` als Platzhalter) |
| `/settings role_color <platform> <hex_color>` | Standard-Rollen-Farbe |
| `/settings role_design <platform> ...` | Benutzerdefiniertes Design für Bereich |
| `/settings role_design_exact <platform> ...` | Design für exakte Zahl |
| `/settings list_role_designs <platform>` | Alle Designs anzeigen |
| `/settings remove_role_design <design_id>` | Design entfernen (Autocomplete) |
| `/settings count_channel <platform> <channel>` | Count-Channel setzen (Voice-/Text-Channel, wird bei Refresh umbenannt) |
| `/settings count_channel_pattern <platform> <pattern>` | Count-Channel-Pattern (`{count}` als Platzhalter) |
| `/settings request_channel <channel>` | Anfragen-Kanal für User-Link/Unlink-Requests setzen |

## Rollen-System

Rollen werden automatisch erstellt und zugewiesen. Jeder verknüpfte Account bekommt seine eigene Rolle:
- YouTube: `[YouTube] {name} - {count} Abos` (z.B. `[YouTube] MeinKanal - 1.234 Abos`)
- Twitch: `[Twitch] {name} - {count} Follower` (z.B. `[Twitch] MeinKanal - 567 Follower`)
- Instagram: `[Instagram] {name} - {count} Follower`
- TikTok: `[TikTok] {name} - {count} Follower`

Platzhalter im Pattern:
- `{name}` – Account-/Kanal-Name
- `{count}` – Aktuelle Zahl (mit Punkt-Tausendertrennung)

Nicht mehr benötigte Rollen werden automatisch gelöscht.

## Count-Channel

Ein optionaler Voice- oder Text-Channel pro Plattform, dessen Name bei jedem Refresh auf die Gesamtzahl aller verknüpften Accounts aktualisiert wird.

- Standard-Pattern YouTube: `📺 {count} YouTube Abos`
- Standard-Pattern Twitch: `🎮 {count} Twitch Follower`
- Standard-Pattern Instagram: `📷 {count} Instagram Follower`
- Standard-Pattern TikTok: `🎵 {count} TikTok Follower`
- Platzhalter: `{count}` – Gesamtzahl aller Accounts (mit Punkt-Tausendertrennung)
- Konfigurierbar über `/settings count_channel` und `/settings count_channel_pattern`

## Anfragen-System

Normale User können über `/request link` und `/request unlink` Anfragen stellen. Der Bot:
1. **Validiert** die Eingabe (prüft, ob Account auf der Plattform existiert)
2. **Prüft Duplikate** (Link: nicht bereits verknüpft; Unlink: muss existieren)
3. **Postet** die Anfrage als Embed mit ✅/❌-Buttons im konfigurierten Admin-Kanal
4. Ein **Admin klickt** auf Annehmen oder Ablehnen – der Bot führt die Aktion automatisch aus

Konfiguration: `/settings request_channel <channel>` setzt den Kanal für Anfragen.

## Tests

```bash
pytest tests/ -v
```

66 Tests für Database-Layer, Role-Logic und Utility-Funktionen.

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
│   │   ├── __init__.py       # Shared platform constants
│   │   ├── admin.py         # Admin-Commands (Link/Unlink/Accounts/History)
│   │   ├── settings.py      # Einstellungs-Commands
│   │   ├── stats.py         # Statistik-Commands (Growth/Overview)
│   │   ├── refresh.py       # Background-Refresh-Loop + EventSub Bootstrap
│   │   └── request.py       # User-Anfragen (Link/Unlink mit Admin-Approval)
│   └── services/
│       ├── youtube.py        # YouTube Data API v3 (rate-limited)
│       ├── twitch.py         # Twitch Helix API + OAuth (rate-limited)
│       ├── instagram.py      # Instagram Public Web API (rate-limited)
│       ├── tiktok.py         # TikTok HTML Scraping (rate-limited)
│       └── eventsub.py       # Twitch EventSub WebSocket-Client
├── tests/
│   ├── test_database.py     # 31 Database-Tests
│   ├── test_roles.py        # 17 Role-Logic-Tests
│   └── test_cogs.py         # 18 Cog-Utility-Tests
├── data/                    # SQLite DB (auto-erstellt)
└── docs/
    └── todos.md             # Aufgaben
```

## Status

**Phase:** Feature-Complete

Alle geplanten Features sind implementiert:
- Vollständige YouTube, Twitch, Instagram & TikTok Integration mit Rate-Limiting
- Multi-Account-Verknüpfung, automatische Rollen, Scoreboards, Count-Channels
- Statistik-Commands mit Wachstumsanalyse
- Background-Refresh mit konfigurierbarem Intervall
- Optionale Twitch EventSub WebSocket-Integration
- 66 Unit-Tests (Database + Role-Logic + Utilities)
- Docker-Support für einfaches Deployment

### Architektur-Entscheidungen

| Entscheidung | Begründung |
|---|---|
| discord.py 2.x Slash-Commands | Moderner Standard, bessere UX |
| aiosqlite | Async-kompatibel mit discord.py event loop |
| Discord-native Permissions | Flexibler als eigenes Admin-System |
| Multi-Account UNIQUE Constraint | Ein User kann mehrere Accounts pro Plattform haben |
| Instagram/TikTok ohne API-Key | Public Web Scraping, kein Entwickler-Account nötig |
| History-Deduplizierung | Reduziert DB-Größe bei gleichbleibendem Count |
| Token-Bucket Rate-Limiting | Respektiert API-Quotas |
| EventSub WebSocket (optional) | Echtzeit-Updates ohne öffentliche URL |
| Docker-Support | Einfaches Deployment mit `docker compose up` |
