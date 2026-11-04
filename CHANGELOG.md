## v1.7.0-rc1 (2026-11-04)
- Independent APRS symbol table/icon/overlay settings for iGate and software DIGI; map markers and APRS-IS station beacons use the chosen symbols.
- Standard APRS 1.0 telemetry `T#` with `PARM`, `UNIT`, `EQNS`, `BITS`; rolling 15-minute counters and report intervals 15/30/60 minutes.
- Five analog channels: RX, USB TX, average distance from reported GPS, unique stations, RF→IS forwarded (iGate) or repeated (DIGI) packets. Additional web values include maximum distance, most distant station, RX/TX rates, forwarded fraction, and TX errors.
- Optional DIGI RF telemetry via KISS, explicit consent, DIRECT RF path by default, 12-second pacing, queued-frame cancellation on DIGI shutdown. No automatic RF output on fresh installs.
- Safety fix: AX.25 KISS encoder permits `T#` telemetry reports; queued RF telemetry is blocked if DIGI permission is cleared.
- Czech/English web telemetry controls and diagnostics, new Raspberry Pi deployment documentation and test suite.

## v1.6.0-rc1 (2026-11-04)
- Operations page (CZ/EN), KISS/APRS-IS/DIGI diagnostics and USB disconnect warning.
- SQLite event journal with rejection reasons and CSV export.
- JSON backup and safe restore (credentials excluded, automatic TX disabled).
- One-shot RF APRS object LIVE/KILL, own position and APRS status through KISS.
- 76 automated unit/integration tests, including simulated serial TX and authenticated HTTP routes.

# Changelog

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
