# Projektstatus – NirukiSocialStats Discord Bot

**Stand:** 2026-02-20  
**Phase:** Major Refactor v2 abgeschlossen

---

## Erledigte Aufgaben

### Projektstruktur & Konfiguration
- [x] Projektstruktur angelegt (`bot/`, `bot/cogs/`, `bot/services/`, `docs/`)
- [x] `config.toml` und `config.toml.example` erstellt
- [x] `requirements.txt` mit allen Dependencies
- [x] `.gitignore` konfiguriert (schützt `config.toml`, `*.db`, `__pycache__`)
- [x] `README.md` mit vollständiger Dokumentation
- [x] `copilot-instructions.md` für Copilot-Kontext

### Datenbank (SQLite via aiosqlite)
- [x] Schema definiert: `guild_settings`, `linked_accounts`, `sub_history`, `role_designs`, `scoreboard_messages`
- [x] Vollständiger async Database-Wrapper mit allen CRUD-Operationen
- [x] Historien-Tracking mit Zeitstempel für alle Abo-/Follower-Änderungen
- [x] **Historien-Deduplizierung** – Gleichbleibende Counts werden nicht doppelt gespeichert (Start+End-Zeitstempel)
- [x] Auto-Erstellung der DB-Datei bei erstem Start
- [x] **Multi-Account-Support** – UNIQUE auf `(guild_id, discord_user_id, platform, platform_id)`
- [x] **Migration** – Bestehende DBs werden automatisch auf neues Schema migriert

### API-Services
- [x] **YouTube Data API v3** – Subscriber-Count & Channel-Info abrufen
- [x] **YouTube URL-Parsing** – Akzeptiert URLs, @Handles und Channel-IDs
- [x] **Twitch Helix API** – Follower-Count, User-Lookup, OAuth Token Management
- [x] **Twitch URL-Parsing** – Akzeptiert URLs und Login-Namen

### Bot-Kern
- [x] `SocialStatsBot`-Klasse mit Config-Loading, DB, YouTube- & Twitch-Service
- [x] **Kein eigenes Permission-System** – Discord `default_permissions(administrator=True)` steuert Zugriff
- [x] Strukturiertes Logging über Python `logging`-Modul
- [x] `main.py` Entry Point mit Logging-Setup

### Admin-Commands (Cog: `admin.py`, Gruppe `/admin`)
- [x] `/admin link_youtube` – YT-Channel verknüpfen (URL/@Handle/ID) + sofortiger Count-Fetch + Rolle
- [x] `/admin link_twitch` – Twitch-Account verknüpfen (URL/Login) + sofortiger Count-Fetch + Rolle
- [x] `/admin unlink` – Einen bestimmten Account entfernen (nach Account-Name)
- [x] `/admin accounts` – Alle verknüpften Accounts eines Users anzeigen
- [x] `/admin force_refresh` – Sofortiger Refresh aller Accounts (optional nach Plattform)
- [x] `/admin history` – Abo-/Follower-Verlauf für einen bestimmten Account

### Einstellungs-Commands (Cog: `settings.py`, Gruppe `/settings`)
- [x] `/settings show` – Alle Einstellungen anzeigen
- [x] `/settings scoreboard_channel` – Scoreboard-Channel setzen (YT/TW)
- [x] `/settings scoreboard_size` – Scoreboard-Größe (1-50)
- [x] `/settings refresh_interval` – Refresh-Intervall (60-86400s)
- [x] `/settings role_pattern` – Standard-Rollen-Pattern mit `{name}` und `{count}` Placeholder
- [x] `/settings role_color` – Standard-Rollen-Farbe (Hex)
- [x] `/settings role_design` – Benutzerdefiniertes Design für Bereich
- [x] `/settings role_design_exact` – Design für exakte Zahl
- [x] `/settings list_role_designs` – Alle Designs anzeigen
- [x] `/settings remove_role_design` – Design entfernen

### Rollen-Management (`roles.py`)
- [x] Automatische Rollen-Erstellung mit Plattform-Prefix (`[YouTube] ` / `[Twitch] `)
- [x] `{count}` und `{name}` Placeholder-Ersetzung in Rollen-Namen
- [x] Account-spezifische Rollen (jeder Account hat seine eigene Rolle)
- [x] Bereichs- und Exakt-Match für benutzerdefinierte Designs
- [x] Fallback auf Standard-Pattern wenn kein Design definiert
- [x] Automatische Entfernung nicht mehr benötigter Rollen
- [x] Farbaktualisierung bei Änderung

### Scoreboard (`scoreboard.py`)
- [x] Embed-Generierung mit Medaillen (🥇🥈🥉) und Ranking
- [x] Persistente Scoreboard-Message (wird editiert, nicht neu gesendet)
- [x] Separate Scoreboards für YouTube und Twitch
- [x] Account-Name wird im Scoreboard angezeigt

### Background-Refresh (Cog: `refresh.py`)
- [x] 30-Sekunden-Loop prüft fällige Accounts pro Guild/Plattform
- [x] Respektiert konfiguriertes Refresh-Intervall pro Plattform
- [x] Automatische Rollen- und Scoreboard-Aktualisierung nach Refresh
- [x] Fehler-Status-Tracking bei fehlgeschlagenen API-Calls

### Error Handling
- [x] `cog_app_command_error` Handler in Admin- und Settings-Cog
- [x] Forbidden-Fehler (fehlende Berechtigungen) → benutzerfreundliche Meldung
- [x] Permission-Check-Fehler → "Keine Berechtigung"-Meldung

---

## Architektur-Entscheidungen

| Entscheidung | Begründung |
|---|---|
| discord.py 2.x mit Slash-Commands | Moderner Standard, bessere UX |
| aiosqlite | Async-kompatibel mit discord.py event loop |
| Discord-native Permissions | Flexibler als eigenes Admin-System, Server-Admins können Zugriffe selbst konfigurieren |
| Multi-Account UNIQUE Constraint | Ein User kann mehrere YT/TW Accounts haben |
| History-Deduplizierung | Reduziert DB-Größe bei gleichbleibendem Count |
| Rollen mit `{name}` Placeholder | Jeder Account bekommt eigene, erkennbare Rolle |
| Alle anderen Settings in DB | Per Discord-Command editierbar wie gefordert |
| Rollen-Prefix `[YT]`/`[TW]` | Sicheres Identifizieren bot-verwalteter Rollen |
