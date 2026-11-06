# Version 1.8.2 RC1 — DIGI RF beacon + telemetry RF verification

- Audited v1.8.1: the DIGI position beacon was APRS-IS-only. Added explicitly confirmed DIGI beacon transport `is` / `rf` and RF path, retaining safe legacy `is` default.
- Immediate position beacon over KISS on DIGI activation, then 30/60/120 minute intervals while radio and software DIGI stay active. DISABLED by default and guarded on USB TX by `digi_allowed`.
- Verified RF telemetry T#/PARM/UNIT/EQNS/BITS remains independent and rate-limited with its 15/30/60-minute schedule and 12-second RF spacing. Prevent beacon/telemetry bursts from interleaving.
- Exposed controls in native CZ/EN desktop tab and optional headless web UI; new journal diagnostics and RF regression tests. KISS USB TX was simulated, not over-the-air verified.

# Version 1.8.1 RC1 — APRS position decoding and geographic course

- Position decoding covers Mic-E, APRS uncompressed/compressed/timestamped formats, APRS objects/items, NMEA RMC/GGA/GLL (GPS fix and optional checksum verified) and valid third-party encapsulated positions. Other packet types without position are not plotted.
- AX.25 **H-bit** routing classification: DIRECT when no digipeater address is marked as already used, VIA after repetition; third-party inner stations are not falsely classed as direct.
- Geographic range (km) and **initial true bearing (degrees, compass point)** computed from configured local iGate/DIGI QTH; absent QTH yields unavailable values.
- Light-blue rows for DIRECT stations and frames and light-blue position markers in native Tkinter desktop and the optional headless web dashboard.
- Native map displays course line from own QTH to the selected station; extra Path/km/Bearing columns with live data. Does not add automatic RF transmissions.
- Added ten hardware-independent routing, GPS decoder and geodesy regression tests and GUI smoke check.

# Version 1.8.0 RC1 — Unified native Windows GUI

- New single-window Tkinter application with seven tabs: Monitor/TX, offline Map, Messages, Objects, iGate/DIGI, Telemetry and Diagnostics/Journal.
- Desktop directly uses the headless `APRSService` engine (`run(with_web=False)`) and one USB KISS port; no web browser, localhost admin key, or split UI.
- Native Inbox/Outbox with ACK/REJ, reply, retry cancellation, additional receive SSIDs and diagnostics; APRS objects LIVE/KILL, status and GPS transmit.
- APRS-IS/DIGI configuration with icons/overlay, telemetry, SQLite activity journal, backup/restore and CZ/EN switching retained in the same window.
- Native offline map from bundled geography data; no map tile network dependency.
- `spustit.bat`, `spustit_sluzbu_windows.bat` and direct `aprs_kiss_monitor.py` now launch the unified desktop; standalone headless Windows server has a distinct filename.
- Desktop commands and data snapshots are sent via the shared service command queue, not a second USB receiver.
- Added unit/integration tests for one-engine startup without HTTP and simulated RF addressed message receive.

## v1.7.0-rc1 – oprava Inbox RX (2026-11-04)
- APRS Inbox přijímá zprávy pro přesnou značku iGate (např. OK5TVR-10) **i základní značku bez SSID** (OK5TVR).
- Další vlastní značky se nastavují na stránce Zprávy → Další přijímané značky / SSID (např. OK5TVR-7,OK5TVR-3); jen stejná základní volací značka.
- Nový diagnostický panel posledních přijatých adresovaných APRS rámců rozlišuje uložené zprávy, jiné adresáty, ACK/REJ a neplatný formát. Panel nezpřístupňuje žádnou možnost RF TX.
- Ruční i automatické ACK používá zdrojovou značku, které byla zpráva skutečně adresována.
- Poslední přijatý RF rámec je vidět také na stránce zpráv; otevřené USB samo o sobě nepotvrzuje příjem.
- Regresní testy pro skutečný KISS tok po USB a pro správu zpráv na webu; automatické RF TX i ACK jsou nadále výchozím stavem vypnuté.
- APRS zprávy přicházející pouze z internetu nejsou přijímány: tato verze používá pro Inbox pouze fyzický RF RX přes UV-K1(8); APRS-IS→RF není implementováno.

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
