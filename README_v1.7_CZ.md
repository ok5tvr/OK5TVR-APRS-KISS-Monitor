# OK5TVR APRS KISS Monitor – verze 1.7.0 RC1

**Windows / Raspberry Pi OS / Debian · Quansheng UV-K1(8) · F4HWN Labs / USB KISS TNC**

Verze 1.7 přidává volitelné APRS ikony a překryvné znaky (overlay) pro iGate i DIGI a 15minutovou telemetrii. Zachovává příjem/vysílání přes KISS, APRS zprávy, mapu, iGate RF→APRS-IS, softwarový DIGI a diagnostiku.

> **Stav:** Experimentální release candidate. RX/TX z PC byl na UV-K1(8) dříve prakticky ověřen. Nová telemetrie a automatické funkce byly ověřeny simulovanými rámci, nikoliv skutečným RF provozem 24/7.

## 1. Nastavení ikon iGate a DIGI

V administraci `/control` (odkaz `admin` z `aprs_service.py --links`) zvol pro každou roli nezávisle:

- **Tabulka symbolů**: `/` (primární) nebo `\\` (alternativní).
- **APRS ikona**: např. `&` iGate, `#` DIGI, `-` QTH, `r` převaděč.
- **Overlay**: jeden znak **A–Z nebo 0–9**, pouze v alternativní tabulce `\\`. Prázdná hodnota znamená standardní symbol bez overlay.

Příklady APRS symbolového kódu:

| Role | Tabulka | Ikona | Overlay | Kód na APRS |
|---|---|---|---|---|
| Přijímací iGate | `\\` | `&` | `R` | `R&` |
| Fill-in DIGI | `\\` | `#` | `1` | `1#` |
| DIGI bez overlay | `/` | `#` | prázdné | `/#` |

Jde o zobrazení v APRS síti/mapě, nikoliv o nastavení ikony stanice v menu UV-K1. Samostatný DIGI maják se posílá **pouze do APRS-IS** a jen při zapnutém DIGI, pokud jej výslovně povolíš a je dostupný internet.

## 2. APRS telemetrie za posledních 15 minut

Ve výchozím stavu je **vypnutá**. Pro iGate a DIGI lze odděleně zapnout APRS telemetrii `T#nnn` a standardní definice `PARM`, `UNIT`, `EQNS`, `BITS`.

| Analogový kanál | Veličina | Význam |
|---|---|---|
| A1 | RX / 15 min | Platné KISS APRS rámce přijaté do programu |
| A2 | TX / 15 min | Úspěšně zapsané pakety do USB KISS (nikoliv ověřený RF výkon) |
| A3 | AVG km | Průměrná vypočtená vzdálenost z posledních udaných GPS pozic unikátních stanic |
| A4 | UNIQUE | Počet různých slyšených značek |
| A5 | IGATE / DIGI | Předané RF pakety do APRS-IS, resp. úspěšné USB zápisy opakovaných DIGI paketů |

Digitální bity indikují dostupnost USB, APRS-IS, DIGI, RF provoz, chybu TX, GPS polohu a povolenou telemetrii. Každá role má svůj zdrojový callsign a číslování rámců.

**Délka statistického okna je pevně 15 minut.** Nastavitelné je pouze odesílání reportů každých 15, 30 nebo 60 minut. Přesné počty a také další metriky (max. vzdálenost, DX značka, RX/min, TX/min, podíl RX předaných do IS a chyby USB) zůstávají na stránce **Diagnostika / objekty** a na mapě. APRS analogové hodnoty mají rozsah **0–255** – vyšší hodnoty se v rádiovém reportu saturují, nikoliv přenášejí jako skutečný počet.

**Upozornění k vzdálenosti:** průměr/maximální vzdálenost je vypočtena z GPS poloh hlášených příchozími stanicemi vůči poloze iGate. Nejde o měření dosaženého radiového dosahu, protože cestou může být digipeater.

## 3. Kam telemetrie odchází

- **iGate**: výhradně APRS-IS; vyžaduje ověřené připojení a zapnutou iGate.
- **DIGI**: výchozí APRS-IS; nebo volitelně **RF přes USB KISS TNC**, pokud výslovně zvolíš `RF`, uložíš konfiguraci s potvrzením a spustíš PC DIGI. Výchozí RF cesta je `DIRECT` bez hopu.
- Při RF DIGI telemetrii se odesílají jednotlivé rámce s odstupem nejméně **12 sekund**; při vysílání standardních `PARM/UNIT/EQNS/BITS` může jít o celkem **5 rámců**. Novou sadu není možné zařadit, dokud předchozí není dokončená.
- RF telemetrie i jiné čekající DIGI rámce se automaticky zruší při vypnutí DIGI nebo ztrátě USB spojení. Samotný monitor nikdy automaticky nepovolí DIGI RF bez souhlasu.
- Ruční odeslání na stránce **Diagnostika / objekty** vyžaduje potvrzení a má 60sekundový limit. Při volbě DIGI RF skutečně přidá RF pakety do KISS TX fronty.

Pro první test doporučujeme **APRS-IS only**. Na společném kanálu **144,800 MHz** používej RF telemetrii jen tehdy, když je vhodná pro místní provoz a nezatěžuje síť.

## 4. Instalace / aktualizace na Raspberry Pi

Službu zastav a před aktualizací zálohuj vlastní konfiguraci z webu:

```sh
sudo systemctl stop ok5tvr-aprs
# Z adresáře nového vydání, jako běžný uživatel:
sh install_raspberry.sh --lan
sudo systemctl status ok5tvr-aprs
python3 /opt/ok5tvr-aprs/aprs_service.py --links
```

Instalátor při běžné aktualizaci zachovává nastavení v `~/.config/ok5tvr-aprs/` (na některých starších instalacích přizpůsobeno uživateli služby), včetně tokenů. Pro zobrazení aktuálního umístění souborů prohlédni jednotku `systemctl cat ok5tvr-aprs`. Nové volby symbolů a telemetrie se do starších konfigurací doplní výchozími hodnotami.

Webové rozhraní má přepínač **CZ / EN**. Pokud po aktualizaci vidíš staré formuláře, obnov stránku `Ctrl+F5` a případně restartuj službu.

## 5. Windows

Spusť `spustit_sluzbu_windows.bat`, poté `zobrazit_odkazy_windows.bat`. Nová telemetrie a symboly se konfigurují na webu služby. Samostatné okno `aprs_kiss_monitor.py` zůstává pro monitorování; na jednom COM portu **neprovozuj obě aplikace zároveň**.

## 6. Bezpečnost a omezení

- UV-K1 musí být v aplikaci **KISS TNC**, při RF TX v režimu povolujícím vysílání. Interní aplikaci `APRS DIGI` v radiostanici nespouštěj zároveň s PC DIGI.
- Testy provedené bez fyzického rádia nemohou potvrdit skutečné vyzáření, obsazení kanálu ani dosah.
- V nové instalaci jsou APRS-IS i RF automatika vypnuté. Web je jen HTTP pro důvěryhodnou LAN, nikoliv pro přímé vystavení internetu.
- Radiostanice nemá nezávislý RF link-layer heartbeat přes KISS; otevřený COM port ještě neznamená, že rádiový přijímač funguje.
- Program nezajišťuje APRS-IS→RF zprávy; iGate je záměrně **RF→APRS-IS**.

## 7. Testy a dokumentace

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -p 'test*.py' -q
```

Průvodce: [README.md](README.md), [README_EN.md](README_EN.md). APRS reference: <https://www.aprs.org/doc/APRS101.PDF>.

73, **OK5TVR**

## Navigace mezi stránkami (oprava 1.7 RC1)

Mapa nyní obsahuje viditelné odkazy **Nastavení**, **APRS zprávy**,
**APRS objekty** a **Diagnostika**. Pro zásahy a RF TX je nutný administrátorský
klíč z `zobrazit_odkazy_windows.bat` nebo `aprs_service.py --links`.
Veřejný odkaz na mapu nedává automaticky oprávnění k vysílání.

Původní `spustit.bat` zobrazuje pouze klasický monitor, jeho web je read-only.
Tlačítka **APRS zprávy** a **APRS objekty** nabídnou přepnutí na
`aprs_service.py`, přičemž před spuštěním musí být uvolněný USB COM port.
Dva programy nesmí souběžně používat tentýž KISS TNC.

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
