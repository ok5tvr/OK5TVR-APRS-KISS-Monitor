# Changelog

## 1.6.0-rc1 — Diagnostics, RF objects, configuration backup

- Adds a separate bilingual **Objects & RF** page with APRS Object/Item LIVE/KILL, UTC object timestamp, GPS, symbol, comment, configurable RF path and explicit session-only periodic repeat.
- One-shot RF station status and station position packets.
- Adds a separate bilingual **Diagnostics & journal** page with KISS, APRS-IS and DIGI status, USB reconnect counters, alerts for disconnected USB or quiet channel (not a definitive radio heartbeat).
- SQLite operations journal stores RX / TX / IS / DROP / SYSTEM events; CSV export, bounded retention and filter controls.
- JSON configuration export/import **without secrets**; restores do not start iGate/DIGI/auto ACK.
- Preserves previous CZ/EN toggle, APRS messaging, Pi systemd, and legacy Windows GUI.
- RF transmissions remain disabled by default; real-RF on-air validation is still pending.


## 1.5.0-rc1 — Czech / English UI

- Live CZ/EN switch across the web map, admin interface, and Inbox/Outbox.
- English translations of controls, status labels, key dialogs, hints, and message delivery statuses.
- Language preference persisted separately in the browser and Windows desktop settings.
- Windows Tkinter GUI translated without restarting or modifying stored APRS messages.
- English documentation and localization tests.
- Raspberry Pi installer and Windows PyInstaller recipe include the new localization script.
- No change to RF DIGI, KISS TX/RX, APRS-IS forwarding, or AX.25 packet formatting.

## 1.4 — APRS messaging (experimental)

- Inbox / Outbox, selectable RF path, ACK/REJ and SQLite message history.
- Retains headless Raspberry Pi service and PC interface from v1.3.
