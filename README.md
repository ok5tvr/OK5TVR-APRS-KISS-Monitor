# OK5TVR APRS KISS Monitor

**Release candidate 1.6.0-rc1 · CZ / EN · Windows / Raspberry Pi**

Software for **Quansheng UV-K1(8)** running F4HWN Labs KISS TNC over USB-C, and compatible USB KISS TNC devices. It monitors AX.25/APRS traffic, runs one-way RF → APRS-IS iGate and an opt-in RF digipeater, sends messages and APRS objects, and provides a local web dashboard.

**Status:** Basic RF KISS RX and TX were verified with UV-K1(8). The newest functions and full unattended operation were verified by automated/simulated tests; actual RF transmission, APRS-IS interoperability and long-term Pi operation still need field testing.

## Features / Funkce

- APRS live receiver, decoder, station list, offline map, statistics.
- RF → APRS-IS iGate (no automatic Internet → RF routing).
- Software DIGI with WIDE1-1, opt-in WIDEn-N/TRACE and duplicate/loop safeguards.
- APRS messaging: Inbox / Outbox, ACK/REJ, SQLite persistence.
- **RF APRS Objects/Items:** live/kill, symbol, GPS, path, opt-in scheduled repetition.
- **One-shot station status and position** over RF KISS.
- **Diagnostics & alerts:** USB reconnects, APRS-IS/DIGI status, prolonged silence and dropped packet reasons.
- **Persistent journal:** RX/TX/IS/DROP/SYSTEM, CSV export; **configuration JSON backup / safe restore**.
- CZ/EN switching in Windows GUI and all web pages; Raspberry Pi `systemd` headless service.

## Documentation

- **[Čeština – návod k verzi 1.6](README_v1.6_CZ.md)**
- **[English – installation and usage](README_EN.md)**
- [Changelog](CHANGELOG.md)

## Quick start / Rychlé spuštění

Raspberry Pi OS / Debian:

```sh
git clone https://github.com/ok5tvr/OK5TVR-APRS-KISS-Monitor.git
cd OK5TVR-APRS-KISS-Monitor
sh install_raspberry.sh --lan
python3 /opt/ok5tvr-aprs/aprs_service.py --links
```

Windows web service: `spustit_sluzbu_windows.bat` → `zobrazit_odkazy_windows.bat`. Desktop monitor: `spustit.bat` (do not use the same COM port in two programs).

**Important:** Automatic RF TX and iGate are off by default. Web admin uses token-based HTTP; never expose it to the public Internet. USB serial write does **not** prove an on-air transmission. Keep `config.json`, `secrets.json` and SQLite databases out of public commits. APRS objects and other transmitted data are public.

## Tests

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -p 'test*.py' -q
```

73, **OK5TVR**
