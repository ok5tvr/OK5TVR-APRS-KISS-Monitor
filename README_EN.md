# OK5TVR APRS KISS Monitor — English guide

**Version 1.5.0-rc1** · Windows / Raspberry Pi OS / Debian · Python 3.10+

A personal amateur-radio project for a **Quansheng UV-K1(8)** running F4HWN Labs with the **KISS TNC** application. Designed for 1200-baud AX.25 APRS over USB CDC (typically 144.800 MHz FM in Czechia).

## Main features

- USB KISS TNC RX decoding and manually confirmed TX tests.
- Map of heard stations, offline geographic data, optional CARTO map tiles.
- One-way **RF → APRS-IS** iGate with duplicate handling and loop prevention.
- Software APRS digipeater (fill-in WIDE1-1, optional regional WIDEn-N/TRACE); TX disabled by default.
- GPS position of the iGate and optional APRS-IS beacon (not automatically sent on RF).
- APRS messages over RF: Inbox, Outbox, configurable target and path, ACK/REJ, limited retries and SQLite history.
- Responsive web dashboard and admin page on Windows or Raspberry Pi, with an optional headless systemd service.
- **Language switcher CZ / EN** for the web map, control panel, messages page and Windows Tkinter desktop interface. The browser saves its language preference locally; desktop preferences are saved in `~/.ok5tvr_aprs_monitor.json`.

## Windows web service

1. Install Python 3.10 or later and run `spustit_sluzbu_windows.bat`.
2. On the UV-K1(8), select 144.800 MHz FM, launch **KISS TNC**, and connect the USB-C data cable.
3. Run `zobrazit_odkazy_windows.bat` to display the authenticated web links.
4. Choose **CZ** or **EN** in the top navigation of any web page.
5. Configure USB, callsign and optional APRS-IS credentials in the admin interface.

The classic desktop GUI is available with `spustit.bat`. Use its **CZ / EN** selector in the top bar. Do **not** run the GUI and headless service on the same serial port concurrently.

## Raspberry Pi OS / Debian

Install the project from its directory (as your ordinary account, not root):

```sh
sh install_raspberry.sh --lan
sudo systemctl status ok5tvr-aprs
python3 /opt/ok5tvr-aprs/aprs_service.py --links
```

Omit `--lan` to keep the web interface on the local host only. The service automatically retries USB after a disconnect and can reconnect to APRS-IS. On first install, **automatic RF TX, iGate forwarding and automatic ACK are all OFF**. Enable them explicitly after checking the configuration.

## Safety and limitations

- The web panel uses HTTP with access tokens; **never expose it directly to the public internet**. Use a VPN for remote access.
- APRS is publicly receivable; do not use APRS messages to transmit confidential information.
- USB write success means only that the frame reached the TNC, not that RF transmission was verified.
- The radio must run KISS TNC in TX-capable mode to transmit; do not use the radio's separate APRS DIGI app simultaneously with PC digipeating.
- Automatic iGate forwarding, software DIGI and messaging are still **experimental**, with simulated integration tests; on-air reliability and unattended operation require field testing.
- This program does not implement APRS-IS → RF forwarding.

## Development / tests

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -p 'test*.py' -q
```

See [README_v1.5_CZ.md](README_v1.5_CZ.md) for the Czech release notes and [README_v1.4_CZ.md](README_v1.4_CZ.md) for the v1.4 setup reference.

Firmware: [F4HWN UV-K1/K5 V3](https://github.com/armel/uv-k1-k5v3-firmware-custom). APRS specification: [APRS 1.0.1](https://www.aprs.org/doc/APRS101.PDF).

73, OK5TVR
