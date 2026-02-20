# Copilot Instructions – NirukiSocialStats Discord Bot

## Projektübersicht

Discord-Bot in Python, der YouTube-Abonnenten und Twitch-Follower-Zahlen trackt, als Discord-Rollen anzeigt und Scoreboards pflegt. Ein Discord-User kann mehrere YouTube- und Twitch-Accounts verknüpft haben. Alle Daten werden in einer SQLite-Datenbank gespeichert.

## Technologie-Stack

- **Python 3.11+**
- **discord.py 2.x** mit Slash-Commands (`app_commands`)
- **aiosqlite** für async SQLite-Zugriff
- **aiohttp** für HTTP-Requests (YouTube Data API v3, Twitch Helix API, Twitch EventSub WebSocket)
- **tomllib** (stdlib) für die Konfigurationsdatei
- **pytest** + **pytest-asyncio** für Unit-Tests

## Projektstruktur

```
main.py                    # Entry Point
config.toml                # Bot-Token + API-Keys (nicht im Git)
pytest.ini                 # pytest-Konfiguration
Dockerfile                 # Docker-Image (python:3.11-slim)
docker-compose.yml         # Docker-Compose für einfaches Deployment
bot/
├── bot.py                 # SocialStatsBot(commands.Bot) – Haupt-Bot-Klasse
├── database.py            # Database-Klasse – async SQLite Wrapper
├── roles.py               # Rollen-Erstellung, -Zuweisung, -Cleanup
├── scoreboard.py          # Scoreboard-Embed-Erstellung & Message-Update
├── pagination.py          # PaginationView – Discord-Buttons für Seiten-Navigation
├── ratelimit.py           # Token-Bucket Rate-Limiter für API-Requests
├── cogs/
│   ├── admin.py           # Admin-Commands (link/unlink/refresh/history/accounts)
│   ├── settings.py        # Einstellungs-Commands (alle Guild-Settings)
│   ├── stats.py           # Statistik-Commands (growth/overview)
│   └── refresh.py         # Background-Tasks (periodischer Count-Refresh + EventSub Bootstrap)
└── services/
    ├── youtube.py          # YouTubeService – YouTube Data API v3 (rate-limited)
    ├── twitch.py           # TwitchService – Twitch Helix API + OAuth (rate-limited)
    └── eventsub.py         # TwitchEventSub – WebSocket-Client für Echtzeit-Events
tests/
├── test_database.py       # 20 Tests für Database-Layer
└── test_roles.py          # 11 Tests für Role-Logic
data/
└── bot.db                 # SQLite-Datenbank (auto-generiert)
docs/
├── status.md              # Entwicklungs-Fortschritt
└── todos.md               # Offene Aufgaben
```

## Architektur & Konventionen

### Bot-Klasse
- `SocialStatsBot` erbt von `commands.Bot` und trägt alle shared resources: `db`, `youtube`, `twitch`
- **Kein eigenes Permission-System** – Berechtigungen werden über Discords `default_permissions(administrator=True)` gesteuert
- Server-Admins können Command-Zugriffe in Server-Einstellungen > Integrationen konfigurieren
- Cogs werden in `setup_hook()` geladen

### Datenbank
- Alles async über `aiosqlite`
- Die `Database`-Klasse in `bot/database.py` kapselt alle Queries
- Tabellen: `guild_settings`, `linked_accounts`, `sub_history`, `role_designs`, `scoreboard_messages`
- Neue Queries gehören als Methoden in die `Database`-Klasse
- `guild_settings` wird per `get_guild_settings()` lazy angelegt (INSERT bei erstem Zugriff)
- **Multi-Account**: UNIQUE auf `(guild_id, discord_user_id, platform, platform_id)` – ein User kann mehrere Accounts pro Plattform haben
- **History-Deduplizierung**: Bei gleichbleibendem Count werden nur Start- und End-Zeitstempel gespeichert

### Slash-Commands
- Alle Commands nutzen `@app_commands.command()` (discord.py 2.x Slash-Commands)
- Admin-Einschränkung über `@app_commands.default_permissions(administrator=True)` auf GroupCog-Ebene
- Plattform-Auswahl über `@app_commands.choices(platform=[...])` mit `youtube`/`twitch`
- Responses sind auf Deutsch
- Ephemeral-Responses für Admin-Commands (`ephemeral=True`)

### Rollen-System
- Bot-verwaltete Rollen haben Prefixe: `[YouTube] ` für YouTube, `[Twitch] ` für Twitch
- `{count}` und `{name}` sind Platzhalter in Rollen-Patterns
- Beispiel: `[YouTube] Niruki - 1.234 Abos`
- Jeder Account bekommt seine eigene Rolle
- Nicht mehr benutzte Rollen werden automatisch gelöscht (`cleanup_unused_roles`)
- Rollen-Design-Priorität: exakter Match > Bereichs-Match > Standard-Pattern

### API-Services
- `YouTubeService` und `TwitchService` in `bot/services/`
- Beide nutzen `aiohttp.ClientSession` (lazy erstellt)
- Beide akzeptieren URLs, Handles und IDs als Input (`parse_youtube_input`, `parse_twitch_input`)
- Twitch nutzt Client-Credentials OAuth (App Access Token)
- Methoden returnen `None` bei Fehlern (kein Exception-Raising)
- **Rate-Limiting**: Beide Services nutzen `RateLimiter` (Token-Bucket) aus `bot/ratelimit.py`
- **Twitch EventSub**: Optionaler WebSocket-Client (`bot/services/eventsub.py`) für Echtzeit-Channel-Updates

### Konfiguration
- `config.toml`: NUR Bot-Token und API-Keys (nicht per Command änderbar)
- Optionale Keys: `dev_guild_id` (Entwicklungs-Sync), `enable_eventsub` (Echtzeit-Updates)
- Alle anderen Einstellungen in `guild_settings`-Tabelle (per Slash-Command editierbar)
- Erlaubte Setting-Keys sind in `Database.update_guild_setting()` whitegelistet

## Git-Workflow

- **Nach jeder Änderung** einen Git-Commit erstellen
- Commit-Messages auf Englisch im Conventional-Commits-Format: `feat:`, `fix:`, `docs:`, `refactor:`, etc.
- Zusammengehörige Änderungen in einem Commit bündeln

## Code-Style

- Type Hints überall (`from __future__ import annotations`)
- Docstrings für Klassen und wichtige Methoden
- Async/await durchgängig (kein blocking I/O)
- Deutsche Bot-Responses, englische Code-Kommentare und Variablennamen
- Fehler in API-Services werden gefangen und als `None` / Status `"error"` zurückgegeben
- Strukturiertes Logging über Python `logging`-Modul

## Wichtige Patterns

```python
# Permission via Discord (auf GroupCog-Ebene)
@app_commands.default_permissions(administrator=True)
class AdminCog(commands.GroupCog, group_name="admin"):
    ...

# Plattform-Auswahl
@app_commands.choices(platform=[
    app_commands.Choice(name="YouTube", value="youtube"),
    app_commands.Choice(name="Twitch", value="twitch"),
])

# Rollen-Name bauen
role_name, role_color = await compute_role_name_and_color(db, guild_id, platform, count, settings, platform_name)
await update_member_role(guild, member, platform, platform_name, role_name, role_color)
await cleanup_unused_roles(guild, platform)
```

## Datenbank-Schema Kurzübersicht

| Tabelle | Zweck |
|---|---|
| `guild_settings` | Pro-Guild-Konfiguration (Channels, Intervalle, Default-Patterns) |
| `linked_accounts` | Discord-User ↔ YouTube/Twitch Mapping (multi-account, UNIQUE auf guild+user+platform+platform_id) |
| `sub_history` | Zeitgestempelte Abo-/Follower-Snapshots (dedupliziert) |
| `role_designs` | Benutzerdefinierte Rollen pro Bereich/exakter Zahl |
| `scoreboard_messages` | Persistente Scoreboard-Message-IDs |

## Dokumentation

- Fortschritt wird in `docs/status.md` festgehalten
- Offene Aufgaben in `docs/todos.md`
- `README.md` enthält Setup-Anleitung und Command-Referenz
