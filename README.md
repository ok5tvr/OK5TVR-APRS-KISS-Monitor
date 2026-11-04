# OK5TVR APRS KISS Monitor

**Windows / Raspberry Pi APRS monitor, one-way iGate, digipeater and messaging over USB KISS TNC**

Vyvíjený projekt pro **Quansheng UV-K1(8)** s firmwarem **F4HWN Labs** (aplikace **KISS TNC**). Aktuální verze zdrojových kódů: **v1.5.0-rc1**.

> **Stav testování:** USB KISS RX/TX byl ověřen na UV-K1(8). Webové služby, zprávy, automatický DIGI a iGate prošly simulovanými testy, ale celý provoz v reálné APRS síti a trvalý běh na Raspberry Pi je nutné ještě ověřit.

## Jazyk / Language

**CZ / EN**: přepínač na webové mapě, v administraci, APRS zprávách a ve Windows GUI. Anglický návod: [README_EN.md](README_EN.md); české poznámky k v1.5: [README_v1.5_CZ.md](README_v1.5_CZ.md).

## Funkce

- Příjem a dekódování AX.25/APRS rámců přes USB KISS; testovací TX.
- Mapa slyšených stanic (offline podklad / volitelný CARTO) a provozní statistiky.
- Jednosměrná iGate **RF → APRS-IS** s filtrováním duplicit.
- Softwarový digipeater (fill-in `WIDE1-1`, volitelně regionální `WIDEn-N` / `TRACE`).
- Vlastní GPS poloha iGate a volitelný APRS-IS poziční maják.
- APRS zprávy: **Inbox / Outbox**, RF cesty, ACK/REJ, omezené opakování, SQLite historie.
- Webové rozhraní z PC a telefonu; administrátorský a prohlížecí přístup.
- Headless služba pro Raspberry Pi / Debian s automatickým znovupřipojením USB.
- Původní samostatné okno Windows (`aprs_kiss_monitor.py`).

## Požadavky

- Radiostanice s firmwarem F4HWN Labs a aktivní aplikací **KISS TNC**; typicky UV-K1(8).
- APRS v ČR: **144,800 MHz FM**, bez CTCSS/DCS, správná anténa.
- Python 3.10 nebo novější a knihovna `pyserial`.
- Pro grafické okno na desktopu je potřebný Tkinter; pro webovou službu nikoli.

## Rychlé spuštění ve Windows

1. Připoj UV-K1(8) přes datový kabel USB-C a spusť v radiostanici `KISS TNC`.
2. Spusť `spustit_sluzbu_windows.bat` (nová webová služba).
3. V druhém okně spusť `zobrazit_odkazy_windows.bat` a otevři odkaz **map**, **admin** nebo **messages**.
4. Ve správě nastav COM port, značku a případně APRS-IS přihlašování. Příjem zkus před zapnutím automatického vysílání.

Starší GUI spouští `spustit.bat`; **nespouštěj ho současně s webovou službou na stejném COM portu**.

## Raspberry Pi OS / Debian

```sh
sh install_raspberry.sh --lan
sudo systemctl status ok5tvr-aprs
python3 /opt/ok5tvr-aprs/aprs_service.py --links
```

`--lan` zpřístupní web ostatním zařízením v **důvěryhodné** lokální síti. Pro místní provoz bez sdílení použij `sh install_raspberry.sh` bez přepínače.

## Bezpečnost a provozní upozornění

- **Automatický DIGI TX, iGate a automatické ACK jsou při nové instalaci vypnuté.** Vysílání zapínej až po ověření lokálních pravidel APRS.
- Web používá HTTP s přístupovými klíči v URL. **Nevystavuj jej přímo do internetu.** Vzdálený přístup řeš VPN a oddělenou domácí síť.
- Data zpráv na APRS nejsou důvěrná. Nezveřejňuj `config.json`, `secrets.json`, `messages.sqlite3` ani přístupové tokeny.
- Pro přímé TX přes KISS musí mít radiostanice povolený TX (nikoliv `RX ONLY`).
- Tato verze **neobsahuje** automatické předávání APRS-IS → RF.

## Dokumentace

Pro přepínání CZ/EN a aktualizaci viz [README_v1.5_CZ.md](README_v1.5_CZ.md). Podrobný popis v1.4: [README_v1.4_CZ.md](README_v1.4_CZ.md). English: [README_EN.md](README_EN.md).

## Testy

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -p 'test*.py' -q
```

## Poděkování / odkazy

- [F4HWN firmware pro Quansheng UV-K1 / K5 V3](https://github.com/armel/uv-k1-k5v3-firmware-custom)
- [APRS Protocol Reference](https://www.aprs.org/doc/APRS101.PDF)
- [APRS-IS IGate Details](https://www.aprs-is.net/IGateDetails.aspx)

**73, OK5TVR**
