# Offene Aufgaben – NirukiSocialStats Discord Bot

**Stand:** 2026-02-20

---

## Hohe Priorität

- [ ] **Praxis-Test** – Bot mit echten API-Keys auf einem Discord-Server testen
- [ ] **Error Handling verbessern** – Bessere User-Feedback-Messages bei API-Fehlern (Rate Limits, ungültige IDs)
- [ ] **Slash-Command-Sync optimieren** – Guild-spezifisches Sync statt globalem (schneller bei Entwicklung)

## Mittlere Priorität

- [ ] **Statistik-Commands** – Visualisierung der gespeicherten Historien-Daten (z.B. Wachstum letzte 7/30 Tage)
- [ ] **Grafik-Export** – Abo-Verlauf als Diagramm (matplotlib/pillow) generieren und als Bild senden
- [ ] **Bulk-Refresh Command** – Alle Accounts einer Plattform auf einmal refreshen
- [ ] **Pagination** – Bei vielen Accounts/History-Einträgen mit Discord-Buttons blättern
- [ ] **Permission-System erweitern** – Mehrere Admins / Moderator-Rolle konfigurierbar
- [ ] **YouTube Channel-Suche** – Neben Channel-ID auch @handle oder Channel-URL akzeptieren

## Niedrige Priorität

- [ ] **Logging** – Strukturiertes Logging (statt print) mit Python logging-Modul
- [ ] **Docker-Support** – Dockerfile + docker-compose.yml für einfaches Deployment
- [ ] **Unit-Tests** – Tests für Database-Layer und Role-Logic
- [ ] **Rate-Limit-Management** – Intelligentes Queuing bei YouTube/Twitch API Limits
- [ ] **Webhook-Integration** – Optional Twitch EventSub statt Polling für Echtzeit-Updates
- [ ] **Konfigurierbare Bot-Sprache** – Mehrsprachige Bot-Responses (DE/EN)
- [ ] **Dashboard** – Web-Dashboard für Einstellungen (optional)
- [ ] **Backup-Command** – SQLite-DB als Datei per DM an Admin senden
