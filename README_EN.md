# OK5TVR APRS KISS Monitor (Windows / Raspberry Pi)

**Version 1.6.0-rc1** – a bilingual Czech/English APRS KISS TNC monitor, one-way RF → APRS-IS iGate, controlled digipeater, messaging, objects/items, diagnostics, and local web panel.

Designed for **Quansheng UV-K1(8)** with **F4HWN Labs KISS TNC** over USB-C. Basic RX/TX has been tested with a real radio; new object TX, automated DIGI, full iGate operation and 24/7 Raspberry Pi operation still require on-air verification. This is a release candidate, not a declared stable release.

## Capabilities

- USB KISS (AX.25) RX and user-confirmed TX; live decoder and offline APRS map.
- APRS-IS one-way iGate (RF → Internet), with loop/duplicate suppression.
- Conservative fill-in WIDE1-1 or opt-in regional WIDEn-N/TRACE digipeating.
- Addressed APRS messages: Inbox/Outbox, ACK/REJ, retry limits and SQLite history.
- **APRS Objects and Items:** save location, symbol, comment, path, send LIVE/KILL, opt-in interval repetition; also manual station position and status packets.
- **Diagnostics & journal:** KISS, APRS-IS and DIGI status; timestamped RX/TX/IS/DROP/SYSTEM entries with drop reasons, SQLite history and CSV export.
- **TNC health monitoring:** alerts for disconnected USB or extended silence. A silent channel does **not** prove the radio or KISS firmware has failed.
- **Portable configuration backup/restore:** JSON without passcodes, bearer tokens or database history. Autostart iGate/DIGI and auto ACK are disabled on import.
- Windows desktop GUI and Raspberry Pi / Debian `systemd` service, plus read-only map and token-protected admin pages.
- Live **CZ / EN** switch on all web pages and Windows desktop.

## Install on Raspberry Pi OS / Debian

```sh
git clone https://github.com/ok5tvr/OK5TVR-APRS-KISS-Monitor.git
cd OK5TVR-APRS-KISS-Monitor
sh install_raspberry.sh --lan
python3 /opt/ok5tvr-aprs/aprs_service.py --links
sudo systemctl status ok5tvr-aprs
```

Use `--lan` only on a trusted private LAN. For existing installations, update the source checkout and run the installer again. Credentials/configuration remain in the user's home directory.

## Windows

Run `spustit_sluzbu_windows.bat`, then `zobrazit_odkazy_windows.bat`. For the legacy GUI, use `spustit.bat`. Never run the desktop GUI and headless service on the same COM port simultaneously.

## Web pages

`map` (offline map), `admin` (settings), `messages` (Inbox/Outbox), `objects` (RF objects/items/status/position), `diagnostics` (KISS/IS/DIGI, export and backup). All pages have a CZ/EN language switch.

## RF Objects

Create an object (9-character name, UTC timestamp, GPS, symbol and printable ASCII comment) or item (variable-length name, no timestamp). Save it without RF, then use the one-shot LIVE or KILL action. Optional repeating objects must be **explicitly enabled each service session** and are stopped on USB loss. Object broadcasts and status/position transmissions are written to the KISS serial interface, not proven transmitted on RF: verify with a separate receiver. The frame's source callsign is the configured iGate callsign.

## Security

- RF digipeater, scheduled objects, iGate and automatic ACK are off on a fresh installation. Every manual RF action must be confirmed.
- The admin interface uses HTTP with bearer keys in URL. **Do not expose this HTTP server to the public Internet.** Use VPN for remote access.
- Backup excludes APRS-IS passcode, access keys and message history. Restore disables automatic transmissions and iGate until you review settings.
- Your radio must run `KISS TNC` with TX enabled, have a suitable antenna and use the applicable local APRS frequency and operating rules.
- APRS-IS → RF automatic forwarding is **not** implemented. Neither are weather sensors, live GPS tracking, or every optional feature in the APRS specification.

## Tests

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -p 'test*.py' -q
```

Protocol references: [APRS 1.0.1](https://www.aprs.org/doc/APRS101.PDF) and [APRS-IS IGate Details](https://www.aprs-is.net/IGateDetails.aspx).

73, **OK5TVR**
