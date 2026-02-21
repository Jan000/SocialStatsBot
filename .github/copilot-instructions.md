# Copilot Instructions – Social-Stats-Bot

## Projektübersicht

Discord-Bot in Python, der YouTube-Abonnenten, Twitch-Follower, Instagram-Follower und TikTok-Follower trackt, als Discord-Rollen anzeigt und Scoreboards pflegt. Ein Discord-User kann mehrere Accounts pro Plattform verknüpft haben. Alle Daten werden in einer SQLite-Datenbank gespeichert. **Phase: Feature-Complete.**

## Technologie-Stack

- **Python 3.11+**
- **discord.py 2.x** mit Slash-Commands (`app_commands`)
- **aiosqlite** für async SQLite-Zugriff
- **aiohttp** für HTTP-Requests (YouTube Data API v3, Twitch Helix API, Twitch EventSub WebSocket, Instagram/TikTok Web Scraping)
- **tomllib** (stdlib) für die Konfigurationsdatei
- **pytest** + **pytest-asyncio** für Unit-Tests (66 Tests)

## Projektstruktur

```
main.py                    # Entry Point
config.toml                # Bot-Token + API-Keys (nicht im Git)
pytest.ini                 # pytest-Konfiguration
Dockerfile                 # Docker-Image (python:3.11-slim)
docker-compose.yml         # Docker-Compose für einfaches Deployment
bot/
├── bot.py                 # SocialStatsBot(commands.Bot) – Haupt-Bot-Klasse
├── database.py            # Database-Klasse – async SQLite Wrapper (mit Migrationen)
├── roles.py               # Rollen-Erstellung, -Zuweisung, -Cleanup
├── scoreboard.py          # Scoreboard-Embed-Erstellung, Message-Update & Count-Channel-Rename
├── pagination.py          # PaginationView – Discord-Buttons für Seiten-Navigation
├── ratelimit.py           # Token-Bucket Rate-Limiter für API-Requests
├── cogs/
│   ├── __init__.py        # Shared platform constants & helpers (PLATFORM_CHOICES, resolve_platform, fetch_count etc.)
│   ├── admin.py           # Admin-Commands (link/unlink/refresh/history/accounts)
│   ├── settings.py        # Einstellungs-Commands (alle Guild-Settings inkl. Count-Channel)
│   ├── stats.py           # Statistik-Commands (growth/overview)
│   ├── refresh.py         # Background-Tasks (periodischer Count-Refresh + EventSub Bootstrap)
│   ├── request.py         # User-Anfragen (Link/Unlink mit Admin-Approval-Buttons + Scoreboard-Button)
└── services/
    ├── youtube.py          # YouTubeService – YouTube Data API v3 (rate-limited)
    ├── twitch.py           # TwitchService – Twitch Helix API + OAuth (rate-limited)
    ├── instagram.py        # InstagramService – Public Web API (rate-limited, kein API-Key)
    ├── tiktok.py           # TikTokService – HTML Scraping (rate-limited, kein API-Key)
    └── eventsub.py         # TwitchEventSub – WebSocket-Client für Echtzeit-Events
tests/
├── test_database.py       # 31 Tests für Database-Layer
├── test_roles.py          # 17 Tests für Role-Logic
└── test_cogs.py           # 18 Tests für Cog-Utilities
data/
└── bot.db                 # SQLite-Datenbank (auto-generiert)
docs/
└── todos.md               # Offene Aufgaben
```

## Architektur & Konventionen

### Bot-Klasse
- `SocialStatsBot` erbt von `commands.Bot` und trägt alle shared resources: `db`, `youtube`, `twitch`, `instagram`, `tiktok`
- **Kein eigenes Permission-System** – keine `default_permissions`-Einschränkung auf den Commands
- Server-Admins konfigurieren Command-Zugriffe ausschließlich über Server-Einstellungen > Integrationen
- Cogs werden in `setup_hook()` geladen

### Datenbank
- Alles async über `aiosqlite`
- Die `Database`-Klasse in `bot/database.py` kapselt alle Queries
- Tabellen: `guild_settings`, `linked_accounts`, `sub_history`, `role_designs`, `scoreboard_messages`, `account_requests`
- Neue Queries gehören als Methoden in die `Database`-Klasse
- `guild_settings` wird per `get_guild_settings()` lazy angelegt (INSERT bei erstem Zugriff)
- **Multi-Account**: UNIQUE auf `(guild_id, discord_user_id, platform, platform_id)` – ein User kann mehrere Accounts pro Plattform haben
- **History-Deduplizierung**: Bei gleichbleibendem Count werden nur Start- und End-Zeitstempel gespeichert

### Datenbank-Migrationen
- **Der gegenwärtige Zustand der Datenbank ist immer unbekannt** – die `_migrate()`-Methode muss mit jeder möglichen Schema-Version umgehen
- **Bei jeder Schema-Änderung** muss eine Migration in `Database._migrate()` hinzugefügt werden
- Migrationen laufen automatisch bei jedem Bot-Start (in `connect()`)
- Jede Migration prüft via `PRAGMA table_info()` / `PRAGMA index_list()` ob die Änderung bereits angewendet wurde
- Migrationen sind idempotent – sie dürfen beliebig oft laufen ohne Fehler
- Das statische `_SCHEMA` enthält nur `CREATE TABLE IF NOT EXISTS` – neue Spalten/Indizes werden via `ALTER TABLE` in `_migrate()` hinzugefügt
- Reihenfolge in `_migrate()`: Erst Spalten hinzufügen, dann Indizes erstellen

### Slash-Commands
- Alle Commands nutzen `@app_commands.command()` (discord.py 2.x Slash-Commands)
- **Keine `default_permissions`** – alle Commands sind standardmäßig sichtbar; Einschränkung über Discord-Integrationseinstellungen
- Plattform-Auswahl über `@app_commands.choices(platform=PLATFORM_CHOICES)` mit `youtube`/`twitch`/`instagram`/`tiktok`
- `PLATFORM_CHOICES` und andere shared constants sind in `bot/cogs/__init__.py` definiert
- **Shared Helpers**: `resolve_platform(bot, platform, user_input)` und `fetch_count(bot, platform, account)` in `bot/cogs/__init__.py` – zentral für alle Cogs, keine Duplikate in einzelnen Cogs
- **Auto-Plattform-Erkennung**: `detect_platform_from_url()` in `bot/cogs/__init__.py` erkennt Plattform anhand der URL
- `/admin link` und `/request link` haben `platform` als optionalen Parameter – wird bei URL-Eingabe automatisch erkannt
- **Autocomplete** für Account-Namen (`account_name`) und Rollen-Design-IDs (`design_id`)
- Autocomplete-Methode `_account_autocomplete` liest `interaction.namespace.user` + `interaction.namespace.platform`
- Responses sind auf Deutsch
- Ephemeral-Responses für Admin-Commands (`ephemeral=True`)

### Anfragen-System (User Requests)
- Normale User können über `/request link` und `/request unlink` Anfragen stellen
- **Scoreboard-Button**: Jedes Scoreboard hat unten einen persistenten Button, über den User eine Link-Anfrage für die jeweilige Plattform stellen können
- Button öffnet `ScoreboardLinkModal` (Discord Modal mit Textfeld für URL/Username)
- `ScoreboardRequestView` ist eine persistente View mit einem Button pro Plattform (`custom_id`: `scoreboard_link_{platform}`)
- Modal-Submit-Handler validiert und erstellt die Anfrage wie `/request link`
- Anfragen werden im konfigurierten `request_channel_id` gepostet (Einstellung über `/settings request_channel`)
- Jede Anfrage wird vor dem Posten validiert (API-Check + DB-Duplikatprüfung)
- Embed mit Accept/Reject-Buttons (`RequestDecisionView`) – persistent, überlebt Bot-Neustarts
- Bei Annahme: Bot führt Link/Unlink-Logik automatisch aus (Rollen, DB, Scoreboard, Count-Channel)
- `account_requests`-Tabelle speichert alle Anfragen mit Status (pending/approved/rejected)
- `custom_id` für Buttons: `request_accept`, `request_reject`, `scoreboard_link_{platform}`
- Request-ID wird im Embed-Footer gespeichert: `Anfrage #123`
- Alle persistenten Views werden in `setup()` registriert: `RequestDecisionView` + `ScoreboardRequestView` (4×, je Plattform)

### Rollen-System
- Bot-verwaltete Rollen haben Prefixe: `[YouTube] `, `[Twitch] `, `[Instagram] `, `[TikTok] `
- `PLATFORM_PREFIX` und `PLATFORM_SETTINGS_PREFIX` Dicts in `bot/roles.py` mappen Plattform → Prefix
- `{count}` und `{name}` sind Platzhalter in Rollen-Patterns
- Beispiel: `[YouTube] MeinKanal - 1.234 Abos`
- Jeder Account bekommt seine eigene Rolle
- Nicht mehr benutzte Rollen werden automatisch gelöscht (`cleanup_unused_roles`)
- Rollen-Design-Priorität: exakter Match > Bereichs-Match > Standard-Pattern

### Count-Channel
- Optionaler Voice-/Text-Channel pro Plattform, der bei jedem Refresh umbenannt wird
- Zeigt die Gesamtzahl aller verknüpften Accounts der Plattform an
- Settings: `{prefix}_count_channel_id`, `{prefix}_count_channel_pattern` (prefix = yt/tw/ig/tt)
- Standard-Patterns: `📺 {count} YouTube Abos` / `🎮 {count} Twitch Follower` / `📷 {count} Instagram Follower` / `🎵 {count} TikTok Follower`
- `{count}` wird durch `format_count(total)` ersetzt (Punkt-Tausendertrennung)
- `update_count_channel()` in `bot/scoreboard.py` – wird nach jedem Refresh und force_refresh aufgerufen

### API-Services
- `YouTubeService`, `TwitchService`, `InstagramService`, `TikTokService` in `bot/services/`
- Alle nutzen `aiohttp.ClientSession` (lazy erstellt)
- Alle akzeptieren URLs, Handles und IDs/Usernames als Input
- YouTube benötigt Data API v3 Key, Twitch nutzt Client-Credentials OAuth
- **Instagram & TikTok benötigen keine API-Keys** (Public Web Scraping)
- Methoden returnen `None` bei Fehlern (kein Exception-Raising)
- **Rate-Limiting**: Alle Services nutzen `RateLimiter` (Token-Bucket) aus `bot/ratelimit.py`
- **Twitch EventSub**: Optionaler WebSocket-Client (`bot/services/eventsub.py`) für Echtzeit-Channel-Updates
- Instagram nutzt `get_channel_info()` → `{id, display_name, follower_count}`
- TikTok nutzt `get_channel_info()` → `{id, display_name, follower_count}`
- Beide verwenden Username als stabile ID (nicht numerisch)

### Konfiguration
- `config.toml`: NUR Bot-Token und API-Keys für YouTube/Twitch (nicht per Command änderbar)
- Instagram & TikTok benötigen keine Keys in der Config
- Optionale Keys: `dev_guild_id` (Entwicklungs-Sync), `enable_eventsub` (Echtzeit-Updates)
- Alle anderen Einstellungen in `guild_settings`-Tabelle (per Slash-Command editierbar)
- Erlaubte Setting-Keys sind in `Database.update_guild_setting()` whitegelistet
- Setting-Prefixe: `yt_` (YouTube), `tw_` (Twitch), `ig_` (Instagram), `tt_` (TikTok)
- Count-Channel-Keys: `{prefix}_count_channel_id`, `{prefix}_count_channel_pattern`
- Globale Keys: `request_channel_id` (Anfragen-Kanal für User-Requests)

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
# Keine default_permissions – Discord regelt den Zugriff
class AdminCog(commands.GroupCog, group_name="admin"):
    ...

# Plattform-Auswahl (shared constant in bot/cogs/__init__.py)
from bot.cogs import PLATFORM_CHOICES
@app_commands.choices(platform=PLATFORM_CHOICES)

# Zentrale Plattform-Helpers (statt Duplikate in Cogs)
from bot.cogs import resolve_platform, fetch_count
info = await resolve_platform(self.bot, platform, channel_input)
count = await fetch_count(self.bot, platform, account)

# Datengetriebene Plattform-Iterationen (statt hardcoded Listen)
from bot.cogs import PLATFORM_DISPLAY_NAME, PLATFORM_EMOJI, PLATFORM_COUNT_LABEL
for plat in ("youtube", "twitch", "instagram", "tiktok"):
    label = f"{PLATFORM_EMOJI[plat]} {PLATFORM_DISPLAY_NAME[plat]}"

# Rollen-Name bauen
role_name, role_color = await compute_role_name_and_color(db, guild_id, platform, count, settings, platform_name)
await update_member_role(guild, member, platform, platform_name, role_name, role_color)
await cleanup_unused_roles(guild, platform)
```

## Datenbank-Schema Kurzübersicht

| Tabelle | Zweck |
|---|---|
| `guild_settings` | Pro-Guild-Konfiguration (Channels, Intervalle, Default-Patterns, Count-Channels) |
| `linked_accounts` | Discord-User ↔ Platform Mapping (multi-account, UNIQUE auf guild+user+platform+platform_id) |
| `sub_history` | Zeitgestempelte Abo-/Follower-Snapshots (dedupliziert) |
| `role_designs` | Benutzerdefinierte Rollen pro Bereich/exakter Zahl |
| `scoreboard_messages` | Persistente Scoreboard-Message-IDs |
| `account_requests` | User-Anfragen für Link/Unlink (pending/approved/rejected) |

## Dokumentation

- Offene Aufgaben in `docs/todos.md`
- `README.md` enthält Setup-Anleitung, Command-Referenz und Projektstatus
