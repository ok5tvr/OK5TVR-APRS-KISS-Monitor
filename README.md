## APRS objekty a přehledné provozní stránky

Živá mapa nyní zobrazuje mapu a stanice bez statistických bloků. Statistiky zůstávají v části Telemetrie. Objekty mají vlastní celostránkový přehled `/objects`; Diagnostika je samostatná.

V **Nastavení → APRS objekty** (`/settings/objects`) lze uložit až **5 objektů**. Každý obsahuje název, polohu, symbol, komentář, LIVE/KILL, RF cestu a samostatnou volbu **RF / INET**. RF používá společnou frontu KISS TNC; INET připojený iGate / APRS-IS a neposílá objekt přes RF. Přehled umožňuje ruční odeslání uloženého objektu.

Plán: pouze ručně, interval 1–1440 minut nebo nejvýše 24 denních časů `HH:MM`. Denní časy používají místní hodiny zařízení, zobrazené na stránce. Po uložení je nutné v Nastavení zapnout plánování. Interval počítá od zapnutí; více splatných objektů se zařazuje s odstupem nejméně 5 sekund. Zmeškané časy se nedohánějí. Uložení konfigurace, restart, obnova, přepnutí režimu a odpojení TNC plánování zastaví. Definice zůstávají uložené; samotné otevření stránky nic nevysílá. Smazání definice nevysílá KILL automaticky.

The live map no longer contains statistics. Up to five persistent APRS objects are configured in Settings, with independent RF or INET transport, manual transmission, intervals or daily times using the displayed device local clock. Scheduling requires explicit runtime activation and stops on configuration save, restart, restore, mode change or TNC disconnect. Missed deadlines are skipped. Queue acceptance is not confirmation of RF reception.

# OK5TVR APRS KISS Monitor

**Windows / Raspberry Pi APRS TNC Command Center · v2.5 dev · bidirectional selective iGate, multi-KISS RX, DIGI and messaging**

Vyvíjený projekt pro **Quansheng UV-K1(8)** s firmwarem **F4HWN Labs** (aplikace **KISS TNC**). Aktuální vývojová verze zdrojových kódů: **v2.5 dev**.

> **Stav testování:** USB KISS RX/TX byl ověřen na UV-K1(8). Webové služby, zprávy, automatický DIGI a iGate prošly simulovanými testy, ale celý provoz v reálné APRS síti a trvalý běh na Raspberry Pi je nutné ještě ověřit.

## v2.5 dev – rozcestník APRS / BBS / Nastavení

Po přihlášení se otevře rozcestník se třemi velkými navigačními tlačítky. **Kliknutí na APRS, BBS ani Nastavení nic nezapíná ani nevypíná.** Zelená označuje skutečně aktivní provozní režim, červená vypnutý. Lišta ukazuje CALL, připojení TNC, místní čas prohlížeče, IP zařízení a verzi.

Pod tlačítky je živý terminál posledních 150 dekódovaných rámců v časovém pořadí. Zobrazuje čas, zdroj, cíl, cestu, typ, obsah a dekódovaný popis. Pozastavení, automatické posouvání a vyčištění výpisu ovlivňují pouze pohled v prohlížeči; nezastavují příjem ani nemažou archiv.

APRS (`/aprs`), BBS (`/bbs`) a Nastavení (`/settings`) jsou samostatné stránky přes celé okno. Nevkládají se pod úvodní tlačítka ani do pracovního iframe. Jednotná horní navigace umožňuje návrat na Úvod. Mapový graf historie může nadále používat izolovanou mapovou komponentu.

**Veškerá konfigurace a zapínání režimů jsou v Nastavení.** Společná nabídka obsahuje CALL/SSID/TNC, iGate/DIGI/GPS, APRS zprávy, USB/displej, TNC/síť/archiv, telemetrii, IS→RF, upozornění/MQTT, blokované stanice, BBS server a zálohu/obnovu. Přepínače APRS ON / BBS ON / Vypnout jsou pouze v této sekci; ovládání BBS serveru je v Nastavení → BBS server. Provozní stránky obsahují příjem, mapy, poštu a terminál klienta.

- **APRS**: příjem, mapy, iGate, DIGI, zprávy, objekty a telemetrie. BBS je z vnitřní APRS navigace odstraněna.
- **BBS**: místní PBBS server / pošta a nový AX.25 klient. Klient používá vlastní SSID, naváže DIRECT spojení se vzdálenou BBS, zobrazí terminál a odešle ASCII řádky do 100 znaků. Server a klient se střídají na jednom TNC.
- **Nastavení**: jediný základní CALL bez SSID, samostatné číselné SSID pro iGate / DIGI / BBS server / BBS klient a společné USB/TCP TNC. SSID 0 znamená značku bez přípony. Odvozené značky jsou v jednotlivých sekcích pouze pro čtení.
- **Přihlášení**: uživatelské jméno je základní CALL (velikost písmen se nerozlišuje); heslem zůstává dosavadní administrátorský přístupový token. Změna CALL se projeví bez restartu webu. Token se nemění. APRS-IS passcode se při změně CALL odstraní, protože patří původní značce; nastav správný pro novou značku.
- **Přepnutí režimu** zastaví iGate, DIGI a BBS, přeruší čekající APRS zprávy, zruší RF oprávnění a zavře starou frontu TNC. Znovu se připojí stejné nakonfigurované TNC. Serverové kontroly nepovolí APRS vysílání v BBS režimu ani BBS v APRS režimu. Volba režimu sama nezapíná RF server ani DIGI/iGate; tyto funkce mají vlastní potvrzená tlačítka.
- **Raspberry HDMI** se povolí zvolením APRS nebo BBS a automaticky mění rozložení: APRS ukazuje rámce, stanice a statistiky; BBS ukazuje server/klienta, protistanici, poštu, frontu a v režimu klienta terminál. Vypnutí režimu obrazovku skryje. Zůstává nutná běžící grafická relace a desktopový autostart panelu.

Při migraci se CALL převezme ze stávající značky iGate, číselná SSID z dosavadních nastavení. Zálohuj celé `~/.config/ok5tvr-aprs` po zastavení služby. Po aktualizaci obnov web přes **Ctrl+F5**. Login vede na `/app`; APRS je na `/aprs` a starý odkaz `/unified` zůstává podporovaný.

BBS klient je testován virtuálním propojením dvou KISS TNC včetně SABM/UA, textu, RR a DISC/UA. Skutečnou RF kompatibilitu UV-K1 a fyzické rozložení HDMI panelu je potřeba ověřit na zařízení. Spojovaná BBS nadále patří na vhodný packet-radio kanál, nikoli na 144,800 MHz APRS.

## Modernizované webové rozhraní

- Jednotný tmavý vzhled konzole, nastavení, mapy, zpráv, BBS a přihlášení. Sdílený lokální styl bez CDN nebo dalších závislostí.
- Boční navigace na počítači; na mobilu výběr všech stránek v jednom poli. Aktuální stránka má vlastní nadpis a zvýraznění. Funguje historie prohlížeče a ovládání záložek šipkami, Home/End.
- Čitelnější karty, formuláře, tabulky a zvýraznění klávesového fokusu. Volba CZ/EN v Nastavení překládá i novou navigaci.
- Upozornění na přerušené spojení se službou na každé stránce; po obnovení spojení se automaticky skryje.
- Opravené měření výšky vložených stránek, které dříve mohlo při obnovování postupně zvětšovat iframe.

Aktualizace vyžaduje znovu spustit `sh install_raspberry.sh --lan` z této větve a obnovit web přes **Ctrl+F5**. Instalační i Windows EXE skript zahrnují `web_theme.css`.

## v2.4 – úpravy jednotného webu / Heard Map / CZ–EN

- **Jednotný přepínač jazyka:** nefunkční/duplicitní volby CZ/EN v pravé části hlavičky a v podpůrných stránkách byly odstraněny. Jazyk se nyní volí na **Nastavení / iGate / DIGI → Jazyk webového rozhraní**. Pamatuje si ho prohlížeč (localStorage) pro všechny připojené stránky, včetně mapy, APRS zpráv, operací a BBS. Samostatně otevřené stránky používají naposledy uloženou volbu.
- **Doplněné CZ/EN:** úvodní rozcestník, Heard Map, TNC, SQLite diagnostika, filtry IS → RF, počasí, konverzace, upozornění a webová správa BBS. Přijatá APRS data (značky, zprávy, obsah paketů) se **nikdy strojově nepřekládají**.
- **Nová Mapa doslechu:** nahoře číselné statistiky a skutečná interaktivní mapa, pod nimi detailní tabulka. Výběr **1 hodina / 24 h / 7 dní / 30 dní** a **konkrétního KISS přijímače** filtruje shodně mapu, statistiky i tabulku podle `/api/heard`. Mapu lze přibližovat, posouvat a zobrazit nad OpenStreetMap; při výpadku online dlaždic zůstává offline podklad. Modré značky měly alespoň jeden DIRECT příjem. Do statistiky se započítávají pouze rámce, z nichž lze získat GPS polohu, nikoliv veškerý RF provoz. DX je vzdálenost vypočtená z udané GPS, **nikoliv změřené RF pokrytí**.
- **Přehlednější konzole:** navigace na úzkých obrazovkách s vodorovným posunem, karty úvodní stránky v pořadí 01–14, upravené rozložení a překlady průběžně aktualizovaných stavů.
- **Provozní zátěž:** historická mapa obnovuje svůj archiv každých 60 s (běžná živá APRS mapa dál po 2,5 s). Nepřibyla žádná RF funkce, nezměnily se limity TX, iGate, DIGI ani BBS. Používá existující SQLite a mapové podklady.

Po instalaci otevři `http://IP_RASPBERRY:8765/`, obnov stránku přes **Ctrl+F5**, pro volbu EN přejdi do Nastavení. Testy `test_web_ux_v24.py` a `test_weather_locale_regression.py` chrání před regresí jazykových formulářů a nepřesnou mapou historického doslechu.

## Vylepšení poštovní schránky BBS

- Celé zprávy do 800 ASCII znaků bez původního omezení na 15 řádků. Zachování prázdných řádků a odsazení; CR, LF i CRLF a oprava překlepů Backspace. Řádek nad 100 znaků se zahodí s hlášením, nikoli tiše zkrátí.
- `L [stránka]`, `LM [stránka]`, `LN [stránka]` (nepřečtené), `N` (další stránka): 15 zpráv na RF stránku. `*` označuje nepřečtenou poštu. `R číslo` přečte celou zprávu; příznak přečtení znamená vyžádání čtení, nikoli doklad doručení celého textu přes RF.
- `RE číslo` připraví odpověď původnímu odesílateli s předmětem `Re:`. `/ABORT` zruší koncept včetně rozepsaného předmětu. `/EX` uloží text. `K číslo YES` po potvrzení smaže zprávu, jejímž je připojená značka odesílatelem nebo adresátem; cizí veřejný bulletin mazat nemůže.
- Web: psaní osobní pošty nebo bulletinu (`ALL`), odpovědi, stránkování po 50 zprávách, celý text a stav přečtení. Zprávy správce mají odesílatele nastavenou BBS značku. Uložení funguje i při vypnuté BBS a samo nepřidává RF rámce. Koncept přetrvá pravidelné obnovování; po potvrzeném uložení se vymaže.
- Diagnostika: čekající znaky, opakování rámce, doba nečinnosti, RNR protistanice, chyby KISS a poslední důvod odpojení. Správce může vyžádat ukončení aktuálního spojení, BBS zůstane zapnutá.
- SQLite přidá tabulku stavů čtení; stávající zprávy i jejich ID zachová. Značky se nadále rozlišují včetně SSID. Před aktualizací zastav službu a zálohuj celé `~/.config/ok5tvr-aprs` včetně databází.

Příklad: `SP OK1ABC-7` → předmět → text → `/EX`; adresát se později připojí jako `OK1ABC-7`, použije `LN`, `R číslo` a případně `RE číslo`.

Rozšíření nemění primární TNC, zákaz souběhu BBS s APRS iGate/DIGI, výchozí vypnutí RF ani požadavky na potvrzení. Druhé TX rádio, BBS forwarding a skutečný RF test s UV-K1 nejsou součástí této aktualizace. Automatické testy jsou bez rádiového hardwaru.

## v2.4 dev – AX.25 connected-mode Packet BBS (PBBS) přes KISS TNC

Rozšíření pro **klasické spojované packet radio**, nikoliv klasické APRS zprávy. Bez DSP/AFSK modemu: rádio/externí KISS TNC obstarává modulaci a FCS; software implementuje omezenou AX.25 modulo-8 stop-and-wait linkovou vrstvu (SABM/UA, I/PID F0, RR/RNR/REJ, DISC/DM), textovou osobní poštovní schránku a samostatnou webovou správu.

**Co umí:**
- Samostatná BBS značka (např. `OK5TVR-8`) **odlišná od** iGate/DIGI SSID.
- Jedno AX.25 RF spojení najednou, DIRECT bez DIGI cesty, okno 1, max. 96 ASCII bytů na I-rámec, potvrzování a omezený retry.
- Textové příkazy vzdáleného uživatele: `H`, `I`, `L`, `LM`, `R <id>`, `SP <CALL>`, `SB`, `Q`.
- Psaní osobních zpráv a bulletinů řádky ukončenými `/EX`, až 800 ASCII znaků / zpráva, 3 nové zprávy na spojení, nejvýše 50–2000 uložených příspěvků.
- SQLite `bbs.sqlite3` s WAL/NORMAL, oddělené od APRS Inboxu a APRS historie, s automatickou regulací kapacity; uživatel může číst své/veřejné zprávy, webový správce všechny a může je mazat.
- Nová karta **AX.25 BBS** ve sjednoceném webu; nastavení SSID, uvítání, idle timeoutu, TX/min, povolení příspěvků, aktuální spojení a správa pošty.
- Bezpečné RF TX: **výchozí vypnuto**; po výpadku TNC, restartu nebo změně konfigurace se oprávnění nepřenáší. Správce musí výslovně potvrdit zapnutí **a vhodný samostatný packet-radio kanál**. Nelze zapnout při současném DIGI/iGate/IS→RF na jednom primárním TNC. Primární KISS TX fronta a omezení se sdílí s ostatními funkcemi; BBS má samostatný limit.
- Už čekající PBBS pakety se při vypnutí nebo změně AX.25 spojení zablokují pomocí epochy. Nezapíná automaticky DIGI, zprávy ani IS→RF a **nepřeposílá** BBS poštu do internetu.

**Předpoklady:** skutečné rádio/TNC musí propouštět **libovolné AX.25 KISS rámce** (nikoliv jen APRS UI). Toto musí být prakticky ověřeno s UV-K1(8) F4HWN KISS firmware; úspěšný zápis do USB nezaručuje odvysílání/ACK. Pro první test použij samostatný packet-radio kmitočet vhodný pro dané pásmo a lokalitu, zkontroluj vysílací oprávnění a připoj druhé AX.25 klientské rádio. **Na standardní evropské APRS frekvenci 144,800 MHz klasickou spojovanou BBS neprovozuj.**

Webovou kartu otevři v `http://IP_RASPBERRY:8765/` → `AX.25 BBS`. Nejdříve **ulož SSID**, ponech DIGI a iGate vypnuté, teprve potom výslovně povol BBS. Na druhé stanici se připoj AX.25 terminálem na `OK5TVR-8`. Vzor interakce:

```
H
L
SP OK1ABC-7
Zdravim z packet radia
Kratka zprava pro protistanici.
/EX
Q
```

BBS používá amatérské veřejné radiové vysílání; volací značka RF protistanice není ověřená jako přihlášení. **Žádné heslo, soubory ani citlivé informace** se přes BBS neposílají. Nejde o plnohodnotnou síťovou FBB/BPQ BBS (žádné BBS forwardování, routing, extended modulo-128 nebo přílohy), pouze lehkou lokální PBBS vhodnou pro Raspberry Pi 2.

**Instalace z vývojové větve:**

```bash
git clone --depth 1 -b feature/ax25-pbbs-v24 \
  https://github.com/ok5tvr/OK5TVR-APRS-KISS-Monitor.git ~/OK5TVR-APRS-v24
cd ~/OK5TVR-APRS-v24
sh install_raspberry.sh --lan
```

Před instalací zastav službu a zálohuj celé `~/.config/ok5tvr-aprs`; pokud systém hlásí **Input/output error** z microSD, instalaci **nespouštěj**, nejdříve řeš poškozené úložiště. Automatické testy kontrolují typické řídicí rámce a administrátorskou autentizaci; provozní kompatibilitu konkrétního TNC s AX.25 spojením je nutné ověřit na RF.

## v2.3 – APRS TNC Command Center: šest rozšíření (vývojová větev)

Tato větev zahrnuje v2.2 (selektivní APRS-IS → RF) a přidává **šest nových oblastí**. Stále žádný DSP/AFSK modem; pouze externí sériová/USB nebo TCP KISS TNC. Kód je určen k automatickému i praktickému ověření na Windows a Raspberry Pi 2.

1. **Centrální RF TX Scheduler:** všechny požadavky `DIGI`, zprávy/ACK, manuální status/objekty, IS → RF a telemetrie sdílejí jednu prioritní frontu **primárního** KISS TNC (modul `aprs_rf_scheduler.py`). Mezera mezi zápisy do KISS (výchozí 2 s), společný limit 12 TX/min a max. 12 rámců ve frontě. Priorita ACK > zprávy > manuální TX > DIGI > IS → RF > telemetrie. Čekající rámce starší 90 s expirovat; režimy RF TX se tím nikdy samy neaktivují. Přenos do USB KISS **není důkaz VF odvysílání**.
2. **Heard Map / RF doslech:** samostatná záložka s přehledem DIRECT / VIA po jednotlivých TNC, vzdáleností od QTH, poslední cestou a počtem paketů; volba 60 min / 24 h / 7 d / 30 d, export CSV, APRS mapový iframe s předvoleným filtrem DIRECT. Databáze rozlišuje `receiver`; stará SQLite schémata se automaticky migrují. Vzdálenosti vycházejí z GPS udávané stanicemi, nejde o ověřenou TX mapu pokrytí.
3. **APRS Messaging 2.0:** seznam konverzací, nepřečtené zprávy a jejich označení přečtení, samostatné ukládání APRS `BLN` bulletinů, ignorování vybraných odesílatelů, zachované stávající RF zprávy a jejich ACK/REJ. Migrace `messages.sqlite3` doplňuje sloupec `read` a tabulku `bulletins`. Blokované zprávy **nevysílají automatická potvrzení**.
4. **Více KISS TNC:** vedle primárního RX/TX až **dvě nezávislá RX-only** zařízení přes TCP KISS nebo přes explicitní USB/COM port. Každé má vlastní připojení/reconnect/počítadla, jeho pakety se přiřazují ke správnému zdroji ve SQLite a Heard Map. **Bez DIGI, iGate a RF TX na sekundárních TNC** – to je bezpečnostní hranice této verze. Žádné automatické propojení LoRa ↔ VHF ani duplicitní otevření jednoho primárního portu.
5. **Upozornění a MQTT:** detekce odpojeného primárního TNC, nedostupné APRS-IS, dlouhé prodlevy bez RF, příjmu vybraných volacích značek a teplotního/tlakového limitu z APRS WX; omezená historie RAM, potlačení opakovaných upozornění, webová stránka a volitelné desktopové notifikace. Volitelný **MQTT QoS0** publish do LAN brokeru přes `paho-mqtt` (musí být nainstalován zvlášť); výchozí vypnuto, bez autentizace/TLS, používat jen důvěryhodnou lokální síť. Upozornění nikdy nevysílají APRS rámce.
6. **Pokročilé mapy a objekty:** lokální import GPX/KML/GeoJSON (do 2 MB a 5000 GPS bodů) jako nepersistentní grafická vrstva APRS mapy; tlačítko Smazat import. Importované mapové podklady zůstávají v prohlížeči, nikoli v SQLite/RF. Objekty se spravují jako až pět uložených definic v Nastavení → APRS objekty; ruční odeslání vyžaduje potvrzení, automatické plánování samostatné zapnutí.

### Aktualizace Raspberry Pi (vývojový build)

Zálohovat **po zastavení služby** celé `~/.config/ok5tvr-aprs/`; nové SQLite migrace nemusí být kompatibilní při návratu ke starému zdrojovému kódu. Nový instalační skript z této větve obsahuje `aprs_rf_scheduler.py`, `aprs_secondary_tnc.py`, `aprs_alerts.py` a ostatní moduly. Instalátor **nevytváří nové rádio TX oprávnění**:

```bash
sudo systemctl stop ok5tvr-aprs
cp -a ~/.config/ok5tvr-aprs ~/ok5tvr-aprs-backup-v23-$(date +%Y%m%d-%H%M%S)
cd ~
git clone --depth 1 -b feature/tnc-command-center-v23 https://github.com/ok5tvr/OK5TVR-APRS-KISS-Monitor.git OK5TVR-APRS-v23
cd OK5TVR-APRS-v23
sh install_raspberry.sh --lan
sudo systemctl status ok5tvr-aprs --no-pager
```

Při současném klonování již existující složky použij místo `git clone` `git -C ~/OK5TVR-APRS-v23 pull --ff-only`. Web: `http://IP_RASPBERRY:8765/`. Pro RF TX, DIGI a IS → RF jsou stále nutné původní individuální potvrzovací kroky.

### Technické omezení a nasazení

Nová funkčnost nepřidává DSP, interní APRS modem ani práci přímo s RF mimo TNC. Sekundární rozhraní jsou vědomě RX-only. MQTT bez TLS/hesla neprovozuj na internetu. Pokud je na Raspberry Pi OS Lite nainstalován pouze systém bez X serveru, volitelný HDMI panel stále vyžaduje grafickou relaci. GUI Windows má zatím společné webové nové funkce, nikoli nové nativní karty ve starém Tkinter monitoru.

## v2.2 – Selektivní APRS-IS → RF iGate / pokročilé filtry (vývojová větev)

Nový modul vychází z principů **Dire Wolf**, **YAAC** a [APRS-IS IGate Details](https://www.aprs-is.net/IGateDetails.aspx). Program stále používá výhradně existující **USB/COM nebo TCP KISS TNC**, nikoli softwarový DSP modem. Současná podpora RF → APRS-IS zůstává zachovaná.

### Nová záložka webu: IS → RF / Filtry

- **Povolené zdrojové značky APRS-IS:** až 24 přesných callsign/SSID, jedna značka na řádek. Nikdy nebereme `K*` ani wildcard.
- **Povolené APRS objekty:** až 16 přesných názvů, s vlastní povolenou kategorií `object`.
- **Druhy paketů:** `message`, `position`, `object`, `weather`. Ve výchozím stavu jsou vybrány zprávy a polohy, ale seznam zdrojových značek je prázdný.
- **Odeslání zprávy na RF:** jen pro platného RF adresáta slyšeného **přímo** na lokálním KISS TNC v posledních 30 minutách; pokud je adresát v poslední době dostupný přímo na APRS-IS, paket se zamítne.
- **RF wrapper:** správný třetí-stranou zapouzdřený AX.25 UI rámec `OURCALL>APRS[,WIDE1-1]:}FROM>DEST,TCPIP,OURCALL*:INFO`. Žádné APRS-IS q konstrukce se do RF cesty nepřepisují; původní path se odstraňuje.
- **Zákazy:** zdroje již slyšené na RF, opakované pakety, `NOGATE`, `RFONLY`, `TCPXX`, vnořené third-party pakety, příliš dlouhé/nevalidní rámce a pakety s vlastní značkou v cestě.
- **Ochrana kanálu:** volba `DIRECT` (doporučeno) / `WIDE1-1`, konfigurovatelné limity 1–6 TX/min a 1–60 TX/h, nejméně 10 s mezi TX, potlačení duplicit nejméně 60 s.
- **Serverový APRS-IS filter:** automaticky z předem schválených značek a objektů, např. `filter b/OK1ABC-7/OK2XYZ-9 o/EVENT1`; **serverový filtr není RF oprávnění** — každému paketu následně musí vyhovět místní filtry.
- **Náhled bez RF TX:** vlastní příklad TNC2 lze vyhodnotit bez vysílání; seznam posledních 60 rozhodnutí vysvětlí stav `preview_only`, `sender_not_selected`, `recipient_not_heard_direct`, `duplicate`, `rate_limit` apod.
- **Žádné automatické zapnutí:** IS → RF se po startu služby / restartu spojení / USB odpojení **vypne**. Vysílat začne až po samostatném výslovném kliknutí **Zapnout IS → RF**. Při zastavení se dodatečně zamítnou i ještě čekající IS → RF pakety ve frontě TNC, pokud fyzický zápis již nezačal.

### Aktivace krok za krokem

1. Otevři původní web `http://IP_ADRESA:8765/` a přihlas se.
2. Zkontroluj příjem přes KISS TNC, bez potřeby zapínat DIGI.
3. V **IS → RF / Filtry** zadej konkrétní zdroje (například `OK1ABC-7`) a případně názvy objektů. Pro první test vyber `DIRECT`, **2 TX/min**, **12 TX/h**, **15 s odstup**.
4. Klikni **Uložit filtry (bez TX)**. Aktualizace serverového `filter` vyžaduje znovu připojit APRS-IS iGate. V kartě **Nastavení / iGate / DIGI** aktivuj ověřenou APRS-IS iGate.
5. Nejprve na kartě IS → RF použij **Vyhodnotit pouze filtry** a sleduj seznam kandidátů. Skutečný RF TX začne **až** po kliknutí **Zapnout IS → RF** a potvrzení. Přehled `queued_usb_not_rf_proof` znamená pouze zařazení do USB KISS fronty, nikoli potvrzené odvysílání.
6. Po testu stiskni **Vypnout IS → RF**. Konfigurace výběru stanic zůstane uložená; samotné oprávnění vysílat se neukládá.

APRS-IS posílá pakety jen z odběru a ze svých výchozích mechanismů pro zprávy: **ne každý existující paket se musí zobrazit**. Konkrétní registrace a platnost APRS-IS hesla jsou nezbytné pro běžný provoz. Doporučujeme zvlášť ověřit smyčky, dostupnost RF adresáta a příliš dlouhé pakety. Nepřepojuj celou veřejnou APRS-IS na místní 1200baud RF kanál.

**Bezpečnostní upozornění:** automatický IS → RF přenos používej pouze tam, kde je to povoleno podle místních radioamatérských podmínek. Provoz na sdíleném APRS kanálu má přednost před maximálními počty paketů. Nastavení vždy kontroluj po změně TNC nebo antény. Pokud procesor iGate ztratí TNC nebo APRS-IS, IS → RF zůstane vypnutá až do dalšího výslovného zapnutí.

## Šetrné SQLite zápisy pro SD kartu (v2.1 optimalizace)

Příjem APRS a provozní deník již **neprovádějí SQLite COMMIT po každém paketu**. Obě používané databáze (`aprs_history.sqlite3`, `operations.sqlite3`) mají samostatnou omezenou RAM frontu a zapisovací vlákno:

- **Dávka:** 100 záznamů, nebo nejdéle 10 sekund od začátku aktuální fronty; zapisuje se jednou transakcí. Ruční otevření historie či deníku může frontu zapsat dříve, aby byla čerstvá data vidět.
- **Ochrana paměti:** každá fronta má nejvýše 1000 záznamů (včetně právě zpracovávaných). Pokud SD dlouhodobě neodpovídá a fronta se zaplní, nové logy se nezapisují; počítadla `dropped` a `write_errors` jsou vidět v TNC diagnostice. RF příjem, iGate a DIGI nesmějí blokovat kvůli ukládání historie.
- **SQLite:** režim `WAL` + `synchronous=NORMAL`, automatický checkpoint po ~1000 stránkách. Záznamy jsou uloženy společně, případné chyby transakce vedou k opakování dávky. Operace mazání starých záznamů jsou výrazně méně časté (přibližně po 1000 přijatých rámcích nebo po jedné hodině; při startu služby).
- **Korektní ukončení:** zbývající řádky se při zastavení služby dopíšou; při nefunkční/plné SD kartě se chyba zaznamená, nicméně zápis nelze garantovat.
- **Výpadek napájení:** může způsobit ztrátu dat dosud čekajících v RAM (a při `synchronous=NORMAL` i některých nedávno potvrzených transakcí). **Nejde o záložní napájení.** Pro ochranu posledních rámců lze používat UPS a korektní vypínání Pi.
- **Záloha databází:** nekopíruj za běhu samotný soubor `.sqlite3`, když může obsahovat aktivní WAL. Před archivací celé konfigurační složky zastav službu, nebo použij SQLite backup API.

Ve webu `TNC / Síť / Historie` najdeš přehled **čekajících paketů, počtu dávek, chyb a zahozených záznamů**. Většina manuálních dotazů na historii nebo deník si vyžádá okamžitou dávku; běžné třísekundové obnovování stavové stránky ji nevyvolává. Batching omezuje počet transakcí, nikoli zaručené fyzické opotřebení konkrétní SD karty.

## v2.1 – TNC Hub / TCP KISS / SQLite / APRS počasí (vývojová verze)

Program stále používá **externí KISS TNC bez DSP modemu**. Rozšíření je společné pro Raspberry Pi a Windows webovou konzoli:

1. **TNC Manager:** hlavní připojení přes USB / fyzický nebo virtuální COM, případně přes TCP KISS klienta (`host:port`). TCP/USB reconnect běží v hlavním servisním cyklu, jeden port se nikdy neotevírá dvakrát.
2. **TCP KISS server:** jeden přijatý AX.25 rámec z fyzického TNC lze číst v až osmi síťových aplikacích. Výchozí stav je vypnuto, po zapnutí naslouchá na `127.0.0.1:8001`, **RX-only**. Port může být změněn. Na nedůvěryhodnou LAN neotevírej `0.0.0.0`: KISS TCP není šifrované a nemá vlastní přihlašování. Pro lokální loopback server lze po výslovném potvrzení v aktuální relaci zapnout RF TX (3sekundové omezení), ale po reconnectu nebo restartu se automaticky vypne. RF vysílání může nastat, jakmile lokální aplikace pošle KISS rámec. Lokální uživatelské procesy musí být důvěryhodné.
3. **SQLite databáze:** samostatný `aprs_history.sqlite3` ve stávající konfigurační složce; přijaté pakety včetně GPS souřadnic a meteorologických dat, vyhledávání podle značky, GeoJSON export vybrané historické trasy. Ve výchozím nastavení 30 dní a maximálně 100000 rámců; staré záznamy se promazávají automaticky (po přibližně 1000 vloženích, nejméně jednou za hodinu při provozu s příjmem a při spuštění). Uchovávání je konfigurovatelné v rozsahu 1–365 dní, 1000–1000000 rámců. Databáze se nemaže při restartu.
4. **APRS WX:** zpracování běžných meteorologických polí z APRS rámců (`c/s/g/t/r/p/P/h/b`), převody na °C, km/h, mm a hPa, přehled stanic, historie a grafy jednotlivých veličin. Nejasná nebo chybějící data se nedopočítávají.
5. **Web:** nové záložky **TNC / Síť / Historie** a **APRS Počasí**, s diagnostikou klientů, reconnecty, databází a grafy. Stav je dostupný také přes autentizované read-only API `/api/tnc`, `/api/archive`, `/api/archive/positions` a `/api/weather`.

Instalace Raspberry Pi: zálohuj `~/.config/ok5tvr-aprs/`, potom v této větvi spusť `sh install_raspberry.sh --lan`. Windows: použij `spustit_web_windows.bat`, potřebuje Python 3 a pyserial. **Jeden KISS TNC port může být aktivní jen v jednom programu** – nespouštěj současně nativní Windows GUI a webový server nad stejným COM portem.

Příklad pro externí aplikaci: po zapnutí *TCP KISS server* s hostem `127.0.0.1`, portem `8001`, nastav druhou APRS aplikaci na TCP KISS host `127.0.0.1`, port `8001` a režim **RX**. Vzdálený TCP KISS klient může naslouchat jen při vědomém povolení síťové adresy serveru; port 8001 nevystavuj do internetu.

**Bezpečnost:** žádná nová služba sama nepovoluje RF TX, iGate ani DIGI. Ovládání je chráněné webovým přihlášením; nešifrované HTTP/TCP KISS používej jen na důvěryhodné síti či přes zabezpečenou VPN. Na Raspberry Pi 2 zůstává hlavní služba bez grafického prostředí a pouze volitelný lokální HDMI panel používá Tkinter.

## Nové sledování APRS provozu: Graywolf-inspired monitoring (v2 preview)

Rozšíření je připravené pro **Windows i Raspberry Pi** nad existujícím sériovým/virtuálním KISS TNC. Přidává:
- **Historii polohy (trails):** až 32 různých reálně přijatých souřadnic na stanici, bez fiktivních DEMO pozic a bez zakládání druhého připojení k TNC. Původní ikony a stanice zůstávají na mapě.
- **Filtry mapy:** zobrazit jen DIRECT, skrýt objekty, omezit poslední aktivitu na 15/60 minut/24 hodin. Volba zobrazit/skrýt trasy.
- **GeoJSON export:** aktuálně filtrované stanice a jejich lokálně zaznamenané trasy do standardního `FeatureCollection` (Point/LineString).
- **Filtry rámců:** v hlavní webové konzoli v Příjem/TX vyhledávání značek, výběr typu paketu a DIRECT-only.
- **Provozní metriky:** koncový bod `/metrics` ve formátu Prometheus (RX, TX USB, předané/odmítnuté iGate rámce, DIGI TX, počet stanic/GPS pozic). Přístup je omezen stejnou read-only autorizací jako `/api/state`; na lokálním počítači je dostupný přímo. Není určeno k otevření do internetu.

**Poznámka:** Trasy jsou v paměti běžící služby a restartem se vymažou; nejsou historickým archívem GPS a nepředstavují změřenou RF trasu. Neimplementujeme zatím vlastní softwarový AFSK modem, obousměrný iGate, AGWPE nebo AX.25 connected-mode terminál. To jsou větší samostatné moduly, které je nutné testovat na rádiu a z hlediska RF bezpečnosti.

## Jednotné webové rozhraní (vývojová větev)

Pro Windows i Raspberry Pi je nyní připravena **jedna přihlašovaná webová aplikace**. Otevři `http://IP_ADRESA:8765/` (na místním Windows počítači `http://127.0.0.1:8765/`), přihlas se jménem `ok5tvr` a vygenerovaným `admin_token`. Hlavní stránka ukazuje stav stanice a nabízí přehledné navigační karty: Příjem/TX, Mapa, Nastavení iGate/DIGI, Zprávy, Objekty, Telemetrie, Diagnostika. Bezpečná cookie relace brání posílání přihlašovacího tokenu v URL. Původní přímé odkazy ještě fungují pro kompatibilitu, ale nové přihlášení je doporučené. Server používá HTTP, proto port nevystavuj do internetu.

- **Windows:** `spustit_web_windows.bat` nebo `spustit_sluzbu_windows.bat` (samostatné nativní okno `spustit.bat` stále existuje). Jedna služba může mít připojený USB KISS COM port pouze jednou.
- **Raspberry Pi:** `sh install_raspberry.sh --lan`. HDMI monitor 800×480 je volitelný v Příjem/TX a potřebuje přihlášenou grafickou plochu.
- **Přihlašovací údaje:** `secrets.json` v uživatelské `.config/ok5tvr-aprs/`, případně lokálně `python3 aprs_service.py --links`.
- **Podrobný návod:** [README_RASPBERRY_WEB_CZ.md](README_RASPBERRY_WEB_CZ.md).

## New in 1.8.2 RC1: DIGI RF position beacon and confirmed RF telemetry

- The DIGI position beacon now supports an independent APRS-IS **or RF** transport, defaulting to the original APRS-IS behavior for existing installations. With **DIGI position beacon enabled**, **RF transport selected**, **a valid GPS position**, **KISS connected** and **DIGI ON**, one DIGI position packet is queued on start, then no more often than every 30/60/120 minutes. The RF path defaults to **DIRECT**.
- DIGI `T#` telemetry can separately use **RF** (15/30/60-minute report interval) with its standard PARM/UNIT/EQNS/BITS metadata and 12-second spacing. An RF beacon does not interleave with the telemetry metadata burst. The iGate continues to send its own beacons and telemetry only via APRS-IS.
- A **separate confirmation** is required to save automatic DIGI RF beacon settings. Both the beacon and RF telemetry require an enabled DIGI and are cancelled when DIGI is disabled; RF TX is OFF in new installations. Diagnostic journal entries distinguish `BEACON rf-queued` from `BEACON rf-usb-written`. **USB success does not prove RF transmission**.
- Both options are configured in the single Windows **iGate / DIGI** tab (beacon) and **Telemetry** tab (T#); the optional headless web panel offers the same options. [Czech instructions](README_v1.8_CZ.md).

## New in 1.8.1 RC1: Position decoding, distance, bearing, DIRECT/VIA

The native Windows **Map** tab now displays distance (km) and true bearing from the configured iGate/DIGI QTH. Packet rows heard **DIRECT** are highlighted light blue, including on the offline map. DIRECT uses the actual AX.25 digipeater H-bits, not a naïve check for a `WIDE` path. Position decoding includes Mic-E, compressed/uncompressed, objects, items, NMEA GPS and third-party payloads. Invalid or intentionally ambiguous positions are not plotted. See [Czech guide](README_v1.8_CZ.md) and [English guide](README_EN.md).

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

1. V radiostanici UV-K1(8) spusť KISS TNC a připoj USB-C.
2. Spusť **`spustit.bat`** nebo příkaz **`py -3 aprs_kiss_monitor.py`**.
3. Ve stejném okně vyber COM port, například COM17, klikni na **Připojit** a přejdi na záložku **Mapa**.
4. V **iGate / DIGI** zadej přesné GPS souřadnice stanice, abys viděl vzdálenost a azimut k přijatým stanicím.

Neotevírej současně samostatnou headless službu na stejném COM portu. Všech sedm desktopových modulů je v jednom okně; samostatná služba na Raspberry Pi může nadále běžet s webovou správou.

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
