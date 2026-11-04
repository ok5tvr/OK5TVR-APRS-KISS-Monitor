# OK5TVR APRS KISS Monitor

**Windows / Raspberry Pi APRS monitor, one-way iGate, digipeater and messaging over USB KISS TNC**

Vyvíjený projekt pro **Quansheng UV-K1(8)** s firmwarem **F4HWN Labs** (aplikace **KISS TNC**). Aktuální verze zdrojových kódů: **v1.8.0-rc1**.

> **Stav testování:** USB KISS RX/TX byl ověřen na UV-K1(8). Webové služby, zprávy, automatický DIGI a iGate prošly simulovanými testy, ale celý provoz v reálné APRS síti a trvalý běh na Raspberry Pi je nutné ještě ověřit.

## Nově v1.8: všechno v jednom okně Windows

Windows verze používá nativní záložky **Příjem/TX, Mapa, Zprávy, Objekty, iGate/DIGI, Telemetrie, Diagnostika/deník**. Žádné přepínání do Chrome ani administrátorské tokeny pro desktop nejsou potřeba. Všechny tyto funkce běží ve společném backendu a sdílejí **jeden USB KISS COM port**. Spusť `spustit.bat` nebo `py -3 aprs_kiss_monitor.py`. Podrobný [český návod v1.8](README_v1.8_CZ.md).

Na Raspberry Pi zůstává samostatná headless služba s webovou správou; současné spuštění desktopu a služby na stejném COM portu není podporováno.

## Jazyk / Language

**CZ / EN**: v nativním Windows okně přímo nahoře, bez restartu; pro headless Raspberry Pi zůstává přepínač na webu. Anglický návod: [README_EN.md](README_EN.md); české poznámky k v1.5: [README_v1.5_CZ.md](README_v1.5_CZ.md).


## Nově v1.7: Symboly, overlay a telemetrie

- **iGate a DIGI** mají oddělené APRS symboly (tabulka `/` nebo `\\`, znak ikony, overlay A–Z / 0–9). Zobrazení na APRS mapě a volitelné APRS-IS poziční majáky používají tato nastavení.
- **Standardní telemetrie APRS `T#`, `PARM`, `UNIT`, `EQNS`, `BITS`** za klouzavých 15 minut: RX, TX, průměr vzdáleností z reportovaných GPS, unikátní značky, úspěšně předané/opakované pakety. Interval odesílání 15/30/60 minut.
- Telemetrie iGate se posílá **jen na APRS-IS**; DIGI také standardně na APRS-IS, nebo volitelně na **RF (KISS)** s výslovným potvrzením a odstupem 12 s na rámec. Všechny automatické výstupy jsou po nové instalaci vypnuté.
- Web navíc zobrazuje maximum vzdálenosti, DX značku, RX/TX za minutu, USB chyby a podíl RX předaných na APRS-IS. Úspěšný zápis do USB neprokazuje fyzické RF odvysílání.

Podrobný nový návod: [README_v1.7_CZ.md](README_v1.7_CZ.md).

## Nově v1.6: Diagnostika a APRS objekty

V administraci je odkaz **Diagnostika / objekty**, případně otevři odkaz `operations` z příkazu `python3 aprs_service.py --links`.

- **Diagnostika:** USB KISS port, počet připojení, čas posledního skutečně přijatého RF rámce, poslední chyba USB a APRS-IS, stav DIGI. USB odpojení déle než 45 s vyvolá varování na stránce (ne odeslání e-mailu). Chybějící APRS pakety **nemusí** znamenat poruchu.
- **Provozní deník:** SQLite `operations.sqlite3`, události RX/TX/USB/DIGI/APRS-IS, důvody filtrování a CSV export (posledních 200 záznamů na stránce, max. 20 000 uchovávaných řádků).
- **Záloha/obnova:** JSON soubor konfigurace bez APRS-IS passcode a webových klíčů. Po obnově jsou vždy deaktivované autostarty iGate/DIGI a automatické ACK. Tajné údaje se při obnově **nepřenášejí**.
- **APRS RF objekty:** živý (LIVE) nebo ukončený (KILL) objekt, jméno až 9 znaků, GPS, symbol, komentář a RF cesta. Pouze ruční jednorázové vysílání s potvrzením.
- **Ruční RF status a pozice:** status s volitelnou cestou a vlastní poloha podle GPS nastavení. Limit 1 provozní TX každých 30 sekund; neautomatizováno.

**Pozor:** Zápis do USB fronty nepotvrzuje fyzické odvysílání. U veřejných APRS objektů i u DIGI ověř skutečný RF provoz druhým přijímačem.

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

## APRS Inbox – diagnostika a nastavení příjmu (oprava RC1)

Otevři webovou službu (`spustit_sluzbu_windows.bat`) a přes administrátorský odkaz stránku **APRS zprávy**.
Přijímány jsou zprávy na značku iGate (např. `OK5TVR-10`) i na základní značku (`OK5TVR`).
Další vlastní SSID (`OK5TVR-7`, `OK5TVR-3`) lze uvést do pole **Další přijímané značky / SSID** oddělené čárkou a kliknout na **Uložit nastavení zpráv**.
Panel **Diagnostika příjmu zpráv** ukazuje i rámce cílené na jiné adresáty, které se v Inboxu správně nezobrazí.

Zkus odeslat testovací APRS zprávu přes **144,800 MHz FM** z jiné rádiové stanice (nikoliv pouze přes APRS-IS) na jednu z uvedených adres.
Pokud se ve webové mapě objevují obecné RX rámce, ale na stránce zpráv nejsou žádné zprávy, je pravděpodobné, že test není adresovanou zprávou, nebo do UV-K1 neprošel.
Samotná funkce tlačítka `2` v aplikaci KISS TNC testuje USB přenos, nevytváří APRS zprávu pro Inbox.

Pokud se rádio při vlastním vysílání z PC odpojuje, použij krátký USB kabel s ferritem u radiostanice (2–4 závity přes ferit vhodný pro VHF) a anténu dále od kabelu.
F4HWN KISS TNC je poloduplexní, proto při vysílání současně nepřijímá.
Příjem zpráv výhradně přes APRS-IS z internetu v této verzi není implementovaný.
