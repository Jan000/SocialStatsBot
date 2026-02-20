# Projektstatus – NirukiSocialStats Discord Bot

**Stand:** 2026-02-20  
**Phase:** Initiale Implementierung abgeschlossen

---

## Erledigte Aufgaben

### Projektstruktur & Konfiguration
- [x] Projektstruktur angelegt (`bot/`, `bot/cogs/`, `bot/services/`, `docs/`)
- [x] `config.toml` und `config.toml.example` erstellt
- [x] `requirements.txt` mit allen Dependencies
- [x] `.gitignore` konfiguriert (schützt `config.toml`, `*.db`, `__pycache__`)
- [x] `README.md` mit vollständiger Dokumentation

### Datenbank (SQLite via aiosqlite)
- [x] Schema definiert: `guild_settings`, `linked_accounts`, `sub_history`, `role_designs`, `scoreboard_messages`
- [x] Vollständiger async Database-Wrapper mit allen CRUD-Operationen
- [x] Historien-Tracking mit Zeitstempel für alle Abo-/Follower-Änderungen
- [x] Auto-Erstellung der DB-Datei bei erstem Start

### API-Services
- [x] **YouTube Data API v3** – Subscriber-Count & Channel-Info abrufen
- [x] **Twitch Helix API** – Follower-Count, User-Lookup, OAuth Token Management

### Bot-Kern
- [x] `SocialStatsBot`-Klasse mit Config-Loading, DB, YouTube- & Twitch-Service
- [x] Admin-Check basierend auf `config.toml` → `admin.user_id`
- [x] `main.py` Entry Point

### Admin-Commands (Cog: `admin.py`)
- [x] `/link_youtube` – YT-Channel verknüpfen + sofortiger Count-Fetch + Rolle
- [x] `/link_twitch` – Twitch-Account verknüpfen + sofortiger Count-Fetch + Rolle
- [x] `/unlink` – Verknüpfung entfernen + Rollen-Cleanup
- [x] `/list_accounts` – Alle Accounts eines Servers anzeigen
- [x] `/force_refresh` – Manueller Refresh für einen User
- [x] `/refresh_status` – Nächster Refresh, letzter Status, letzte Aktualisierung
- [x] `/history` – Abo-/Follower-Verlauf mit Diff-Anzeige

### Einstellungs-Commands (Cog: `settings.py`)
- [x] `/show_settings` – Alle Einstellungen anzeigen
- [x] `/set_scoreboard_channel` – Scoreboard-Channel setzen (YT/TW)
- [x] `/set_scoreboard_size` – Scoreboard-Größe (1-50)
- [x] `/set_refresh_interval` – Refresh-Intervall (60-86400s)
- [x] `/set_role_pattern` – Standard-Rollen-Pattern mit `{count}` Placeholder
- [x] `/set_role_color` – Standard-Rollen-Farbe (Hex)
- [x] `/add_role_design` – Benutzerdefiniertes Design für Bereich oder exakte Zahl
- [x] `/list_role_designs` – Alle Designs anzeigen
- [x] `/remove_role_design` – Design entfernen

### Rollen-Management (`roles.py`)
- [x] Automatische Rollen-Erstellung mit Plattform-Prefix (`[YT]` / `[TW]`)
- [x] `{count}` Placeholder-Ersetzung in Rollen-Namen
- [x] Bereichs- und Exakt-Match für benutzerdefinierte Designs
- [x] Fallback auf Standard-Pattern wenn kein Design definiert
- [x] Automatische Entfernung nicht mehr benötigter Rollen
- [x] Farbaktualisierung bei Änderung

### Scoreboard (`scoreboard.py`)
- [x] Embed-Generierung mit Medaillen (🥇🥈🥉) und Ranking
- [x] Persistente Scoreboard-Message (wird editiert, nicht neu gesendet)
- [x] Separate Scoreboards für YouTube und Twitch

### Background-Refresh (Cog: `refresh.py`)
- [x] 30-Sekunden-Loop prüft fällige Accounts pro Guild/Plattform
- [x] Respektiert konfiguriertes Refresh-Intervall pro Plattform
- [x] Rate-Limit-Schutz (0.5s Delay zwischen API-Calls)
- [x] Automatische Rollen- und Scoreboard-Aktualisierung nach Refresh
- [x] Fehler-Status-Tracking bei fehlgeschlagenen API-Calls

---

## Architektur-Entscheidungen

| Entscheidung | Begründung |
|---|---|
| discord.py 2.x mit Slash-Commands | Moderner Standard, bessere UX |
| aiosqlite | Async-kompatibel mit discord.py event loop |
| TOML für Config | Nur Admin-User-ID und API-Keys, nicht per Command änderbar |
| Alle anderen Settings in DB | Per Discord-Command editierbar wie gefordert |
| Rollen-Prefix `[YT]`/`[TW]` | Sicheres Identifizieren bot-verwalteter Rollen |
