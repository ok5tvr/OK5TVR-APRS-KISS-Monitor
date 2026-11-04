## New in 1.8.1 RC1 — Position formats, DIRECT reception, range and bearing

The single-window desktop **Map** tab now shows callsign, DIRECT/VIA route, great-circle distance in kilometres, and initial true bearing from the configured iGate/DIGI QTH. **DIRECT** packet rows are highlighted in light blue. Position markers heard directly over RF are also light blue; clicking a station shows a course line from QTH. No web browser is required for desktop operation.

Supported position-bearing packet types include uncompressed and compressed APRS, timestamped positions, **Mic-E**, APRS objects/items, **NMEA RMC/GGA/GLL** and encapsulated **third-party** positions. Not all APRS packet types carry GPS coordinates. Ambiguous/invalid coordinates are never treated as precise positions.

**DIRECT** means no digipeater H-bit was set in the actual AX.25 RF packet. A `WIDE1-1` path *without* the H-bit can still be direct. DIRECT is not independent proof of physical line of sight. The displayed distance and true bearing are geographic calculations, not measured RF range or direction of signal arrival. To enable them, configure the station's own GPS position first. All existing TX safeguards remain in force.

# Windows native tabbed app (v1.8 RC1)

**All Windows modules now run inside one native desktop window**: Monitor/TX, Offline Map, Messages (Inbox/Outbox, ACK/REJ), APRS Objects (LIVE/KILL), iGate/DIGI, Telemetry, Diagnostics and Packet Journal. No Chrome or administration URL is required on Windows; the app uses the same APRS service backend with HTTP **disabled** in desktop mode, so only one process owns the serial port. Use `spustit.bat` or `py -3 aprs_kiss_monitor.py`. Czech [v1.8 guide](README_v1.8_CZ.md).

The standalone Raspberry Pi/headless service retains optional browser access as an independent deployment mode. Do not start both desktop and headless service against the same TNC.

# OK5TVR APRS KISS Monitor — English guide

**Version 1.7.0-rc1** · Windows / Raspberry Pi OS / Debian · Python 3.10+

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

## New in v1.7: separate iGate/DIGI symbols and APRS telemetry

Both iGate and DIGI have independent APRS **symbol-table** (`/` primary or `\\` alternate), **icon** (e.g. `&` iGate, `#` digi), and optional single-character **overlay** (A–Z or 0–9 on alternate table only). Examples: `R&` is a receive-only iGate, `1#` a fill-in digi. These settings affect their map markers and APRS-IS position beacons, not the radio's display.

Telemetry is disabled on new installations. Enable it separately for iGate or DIGI on the **Settings / Admin** page:

- **iGate** transmits telemetry to **APRS-IS only**, when connected. **DIGI** also uses APRS-IS by default; an explicit, confirmed configuration can instead transmit DIGI telemetry via **RF KISS TNC** while PC digipeating is active.
- `T#` reports have five 0–255 analog channels: **received KISS packets over the last 15 minutes**, **USB TX writes over 15 minutes**, **average distance (km)** from latest decoded GPS positions, **unique heard callsigns**, and **APRS-IS gated** (iGate) or **DIGI-repeat USB TX** counts (DIGI).
- Standard `PARM`, `UNIT`, `EQNS` and `BITS` definitions are transmitted with the first report and periodically. Report every 15, 30 or 60 minutes, always measuring the previous **15 minutes**.
- Extra web diagnostics show longest GPS-based distance, DX station, RX/min, TX/min, percentage of received packets forwarded to APRS-IS, USB write errors and link state.
- APRS analog data saturates at 255; the live web statistics retain exact values. USB writes **do not prove actual on-air RF transmission**. Distance calculated from a station's claimed position **is not** a verified direct RF reception range.

**Optional DIGI RF telemetry** uses the `DIRECT` RF path by default and spaces frames by **at least 12 seconds**. A full first report is five frames (four metadata + one data). Changing DIGI state or losing USB clears queued RF telemetry. Manual send is separately confirmed and rate-limited. Before enabling RF telemetry on 144.800 MHz, verify the local channel plan and network load.

See [README_v1.7_CZ.md](README_v1.7_CZ.md) for full Czech instructions, symbol examples and the Raspberry Pi upgrade procedure.

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


## v1.6 operational extensions (release candidate)

Open the **Operations / Diagnostics** page via the `operations` link printed by `python3 aprs_service.py --links`. It includes:

- USB/KISS health and disconnect warning, latest RF frame timestamp, APRS-IS status, DIGI statistics and last errors. USB connected does not prove RF reception.
- Durable SQLite activity journal (RX/TX, accepted/rejected DIGI and IGate, USB events) and CSV export.
- Portable JSON configuration backup without APRS-IS passcode or web tokens. Restoring always disables DIGI/IGate autostart and automatic ACK.
- Manually transmitted live/killed APRS RF objects, own RF position and status text; one packet per confirmation, 30 s cooldown.

These features operate via the headless web service on Windows or Raspberry Pi. The legacy Tkinter window remains available, but does not expose the new management pages itself. APRS-IS→RF gating remains unsupported. Do not expose the administrative HTTP interface to the public Internet.

## APRS Inbox RX fix – troubleshooting

The web Inbox now accepts packets addressed to the configured iGate callsign (e.g. `OK5TVR-10`) **and the base callsign** (`OK5TVR`). Add any other SSIDs you operate, e.g. `OK5TVR-7,OK5TVR-3`, in the **Additional receive callsigns / SSIDs** field on the Messages administration page. All aliases must share your own base callsign.

The **Message reception diagnostics** panel displays both stored messages and received messages addressed to other stations, with reasons for not entering Inbox. The last RF frame timestamp helps distinguish a silent TNC from a wrong message addressee. Manual/automatic ACKs use the destination callsign of the received message as their own RF source. Auto ACK and automatic RF TX remain off by default.

Send a test **on-air** addressed message to one of the configured receive callsigns. The KISS TNC key `2` injects a USB test packet but does not create an addressed APRS message. APRS-IS-only Internet messages do not reach the RF-only Inbox, and there is no APRS-IS→RF gateway in this release.

If the radio resets its USB connection when keying up, try a short USB cable with a VHF ferrite near the radio and keep the antenna away from the cable. KISS TNC is half-duplex.
