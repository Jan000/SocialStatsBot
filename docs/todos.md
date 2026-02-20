# Offene Aufgaben – NirukiSocialStats Discord Bot

**Stand:** 2026-02-20

---

## Mittlere Priorität

- [ ] **Statistik-Commands** – Visualisierung der gespeicherten Historien-Daten (z.B. Wachstum letzte 7/30 Tage)
- [ ] **Pagination** – Bei vielen Accounts/History-Einträgen mit Discord-Buttons blättern
- [ ] **Guild-spezifischer Slash-Command-Sync** – Schnellerer Sync bei Entwicklung

## Niedrige Priorität

- [ ] **Docker-Support** – Dockerfile + docker-compose.yml für einfaches Deployment
- [ ] **Unit-Tests** – Tests für Database-Layer und Role-Logic
- [ ] **Rate-Limit-Management** – Intelligentes Queuing bei YouTube/Twitch API Limits
- [ ] **Webhook-Integration** – Optional Twitch EventSub statt Polling für Echtzeit-Updates

## Erledigt (v2 Refactor)

- [x] ~~Error Handling verbessern~~ – cog_app_command_error Handler
- [x] ~~Bulk-Refresh Command~~ – `/admin force_refresh` refresht alle Accounts
- [x] ~~YouTube Channel-Suche~~ – URLs, @Handles und Channel-IDs akzeptiert
- [x] ~~Twitch URL-Parsing~~ – URLs und Login-Namen akzeptiert
- [x] ~~Logging~~ – Strukturiertes Logging mit Python logging-Modul
- [x] ~~Multi-Account-Support~~ – Mehrere Accounts pro User pro Plattform
- [x] ~~Permission-System entfernt~~ – Discord-native Permissions via default_permissions
- [x] ~~History-Deduplizierung~~ – Gleichbleibende Counts werden zusammengefasst
