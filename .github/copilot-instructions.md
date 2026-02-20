# Copilot Instructions – NirukiSocialStats Discord Bot

## Projektübersicht

Discord-Bot in Python, der YouTube-Abonnenten und Twitch-Follower-Zahlen trackt, als Discord-Rollen anzeigt und Scoreboards pflegt. Alle Daten werden in einer SQLite-Datenbank gespeichert.

## Technologie-Stack

- **Python 3.11+**
- **discord.py 2.x** mit Slash-Commands (`app_commands`)
- **aiosqlite** für async SQLite-Zugriff
- **aiohttp** für HTTP-Requests (YouTube Data API v3, Twitch Helix API)
- **toml** für die Konfigurationsdatei

## Projektstruktur

```
main.py                    # Entry Point
config.toml                # Nur Admin-User-ID + API-Keys (nicht im Git)
bot/
├── bot.py                 # SocialStatsBot(commands.Bot) – Haupt-Bot-Klasse
├── database.py            # Database-Klasse – async SQLite Wrapper
├── roles.py               # Rollen-Erstellung, -Zuweisung, -Cleanup
├── scoreboard.py          # Scoreboard-Embed-Erstellung & Message-Update
├── cogs/
│   ├── admin.py           # Admin-Commands (link/unlink/refresh/history)
│   ├── settings.py        # Einstellungs-Commands (alle Guild-Settings)
│   └── refresh.py         # Background-Tasks (periodischer Count-Refresh)
└── services/
    ├── youtube.py          # YouTubeService – YouTube Data API v3
    └── twitch.py           # TwitchService – Twitch Helix API + OAuth
data/
└── bot.db                 # SQLite-Datenbank (auto-generiert)
docs/
├── status.md              # Entwicklungs-Fortschritt
└── todos.md               # Offene Aufgaben
```

## Architektur & Konventionen

### Bot-Klasse
- `SocialStatsBot` erbt von `commands.Bot` und trägt alle shared resources: `db`, `youtube`, `twitch`
- Admin-Check via `bot.is_admin(user_id)` – Admin-User-ID kommt aus `config.toml`
- Cogs werden in `setup_hook()` geladen

### Datenbank
- Alles async über `aiosqlite`
- Die `Database`-Klasse in `bot/database.py` kapselt alle Queries
- Tabellen: `guild_settings`, `linked_accounts`, `sub_history`, `role_designs`, `scoreboard_messages`
- Neue Queries gehören als Methoden in die `Database`-Klasse
- `guild_settings` wird per `get_guild_settings()` lazy angelegt (INSERT bei erstem Zugriff)

### Slash-Commands
- Alle Commands nutzen `@app_commands.command()` (discord.py 2.x Slash-Commands)
- Admin-Beschränkung über den `admin_only()` Check-Decorator (in jedem Cog definiert)
- Plattform-Auswahl über `@app_commands.choices(platform=[...])` mit `youtube`/`twitch`
- Responses sind auf Deutsch
- Ephemeral-Responses für Admin-Commands (`ephemeral=True`)

### Rollen-System
- Bot-verwaltete Rollen haben Prefixe: `[YT] ` für YouTube, `[TW] ` für Twitch
- `{count}` ist der Platzhalter in Rollen-Patterns (wird durch formatierte Zahl ersetzt)
- Nicht mehr benutzte Rollen werden automatisch gelöscht (`cleanup_unused_roles`)
- Rollen-Design-Priorität: exakter Match > Bereichs-Match > Standard-Pattern

### API-Services
- `YouTubeService` und `TwitchService` in `bot/services/`
- Beide nutzen `aiohttp.ClientSession` (lazy erstellt)
- Twitch nutzt Client-Credentials OAuth (App Access Token)
- Methoden returnen `None` bei Fehlern (kein Exception-Raising)

### Konfiguration
- `config.toml`: NUR Admin-User-ID und API-Keys (nicht per Command änderbar)
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

## Wichtige Patterns

```python
# Admin-Check Decorator (in jedem Cog)
def admin_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        bot: SocialStatsBot = interaction.client
        return bot.is_admin(interaction.user.id)
    return app_commands.check(predicate)

# Plattform-Auswahl
@app_commands.choices(platform=[
    app_commands.Choice(name="YouTube", value="youtube"),
    app_commands.Choice(name="Twitch", value="twitch"),
])

# Rollen-Name bauen
role_name, role_color = await compute_role_name_and_color(db, guild_id, platform, count, settings)
await update_member_role(guild, member, platform, role_name, role_color)
await cleanup_unused_roles(guild, platform)
```

## Datenbank-Schema Kurzübersicht

| Tabelle | Zweck |
|---|---|
| `guild_settings` | Pro-Guild-Konfiguration (Channels, Intervalle, Default-Patterns) |
| `linked_accounts` | Discord-User ↔ YouTube/Twitch Mapping + aktueller Count |
| `sub_history` | Zeitgestempelte Abo-/Follower-Snapshots für Statistiken |
| `role_designs` | Benutzerdefinierte Rollen pro Bereich/exakter Zahl |
| `scoreboard_messages` | Persistente Scoreboard-Message-IDs |

## Dokumentation

- Fortschritt wird in `docs/status.md` festgehalten
- Offene Aufgaben in `docs/todos.md`
- `README.md` enthält Setup-Anleitung und Command-Referenz
