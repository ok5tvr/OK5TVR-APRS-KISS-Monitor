# OK5TVR APRS KISS Monitor 1.8.1 RC1 — jednotné okno Windows

## Nově ve v1.8.1 RC1: dekódování GPS, DIRECT/VIA, vzdálenost a azimut

- Přímo v záložce **Mapa** jsou pro stanice sloupce **Značka · Cesta · km · Azimut** a jsou dostupné i v angličtině. GPS se bere z dekódovaných APRS rámců; pro výpočet je nutné v **iGate / DIGI** zadat vlastní souřadnice QTH.
- Po výběru stanice se vykreslí směr od QTH ke stanici a zobrazí vypočtená **vzdálenost po zemském povrchu v kilometrech a počáteční azimut** ve stupních (0° = sever, 90° = východ).
- Stanice s posledním rámcem **DIRECT** mají **světle modrý podklad** v seznamu stanic a přijatých paketů. Pozice přijaté přímo mají světle modrý bod na mapě. **VIA** znamená, že některá DIGI adresa v AX.25 měla nastavený H-bit (v monitor formátu symbol `*`).
- **DIRECT je odvozeno z AX.25 hlavičky, nikoli z toho, zda cesta obsahuje WIDE1-1.** Trasa WIDE1-1 bez H-bitu je přímý příjem. U objektů a zapouzdřených APRS zpráv není „přímý příjem objektu“ považován za přímý příjem vysílací stanice objektu.
- Rozšířená podpora poloh v paketech: **Mic-E**, běžná nekomprimovaná a Base91 komprimovaná pozice, pozice s časem, **APRS objekt/položka**, **NMEA GPS RMC/GGA/GLL** a poloha uvnitř **third-party** rámce. Nesprávné, neplatné nebo příliš nepřesné pozice nejsou vykresleny jako přesné GPS.
- Vzdálenost/azimut popisuje geometrii mezi ohlášenými souřadnicemi, **nikoli skutečnou délku RF cesty ani směr příchodu signálu**. U retransmisí jde o polohu původní stanice, ne opakovače.
- Výchozí ochrany RF TX se nemění a po aktualizaci se žádné nové automatické vysílání nespouští.

## Co se změnilo

Windows aplikace má nyní **jedno hlavní okno a sedm záložek**. Není potřeba Google Chrome, adresa localhost, administrátorský klíč ani druhý proces obsluhující stejný COM port. Nové nativní rozhraní používá **stejný APRSService backend** jako služba na Raspberry Pi a **stejnou databázi Inbox/Outbox** a provozního deníku.

1. **Příjem / TX** – seznam dekódovaných rámců KISS/AX.25, obsah, HEX, výběr COM portu, ruční RF test a export CSV.
2. **Mapa** – nativní offline mapa z dodaného geografického podkladu, stanice, APRS objekty, vlastní iGate/DIGI, přiblížení a posun. Žádná stránka v prohlížeči.
3. **Zprávy** – příjem z RF do Inboxu (včetně základní značky a dalších nakonfigurovaných SSID), odeslání na RF, ACK/REJ, odpověď, Outbox, opakování a diagnostika přijatých zpráv.
4. **Objekty** – jednorázové APRS LIVE / KILL přes KISS, vlastní GPS poziční maják a stavový text, historie odeslaných objektů.
5. **iGate / DIGI** – APRS-IS připojení, heslo, symboly, overlay, pravidla DIGI, GPS a volitelné majáky.
6. **Telemetrie** – přehled za posledních 15 minut, volitelné APRS-IS / DIGI RF T# a ruční report.
7. **Diagnostika / deník** – stav USB a APRS-IS, SQLite provozní deník, export CSV, záloha a obnova konfigurace.

Jazyk lze přepnout **CZ / EN** nahoře v okně bez restartu. Vlastní APRS rámce a zprávy se nepřekládají.

## Spuštění ve Windows

Vyžaduje Python 3.10 nebo novější. **Nejprve ukonči starou webovou službu i klasický monitor**, aby COM port nebyl obsazený.

1. Připoj Quansheng UV-K1(8) USB-C kabelem a spusť v něm **KISS TNC**; rádio nastav na **144,800 MHz FM**.
2. Rozbal celý archiv do jedné složky a dvakrát klikni na **`spustit.bat`**. Alternativně v CMD spusť:

   ```bat
   py -3 -m pip install -r requirements.txt
   py -3 aprs_kiss_monitor.py
   ```
3. V záložce **Příjem / TX** vyber správný COM port (například COM17) a klikni **Připojit**. Automatická detekce funguje pouze, když je port jednoznačný.
4. Potom můžeš otevřít všechny ostatní záložky. **Žádná funkce tě nepřesměruje na web.**
5. V záložce **iGate / DIGI** nastav vlastní značky, APRS-IS passcode, GPS a další volby, ulož nastavení a podle potřeby ručně spusť iGate nebo DIGI.

> `spustit_sluzbu_windows.bat` nyní z důvodu kompatibility spouští **stejné záložkové okno** jako `spustit.bat`. Původní režim bez okna lze samostatně spustit pomocí `spustit_headless_server_windows.bat`, například pro serverový provoz. Nikdy nespouštěj oba režimy současně.

## Bezpečnost a známá omezení

- Ve výchozím stavu jsou automatický DIGI TX, iGate a automatické ACK vypnuté. Potvrzení je nutné před ručním TX, APRS objekty a povolením retransmisí.
- Pouhé úspěšné zapsání rámce do USB KISS TNC **neprokazuje RF odvysílání**. Ověř ho druhým přijímačem.
- Nativní Windows aplikace **nespouští HTTP server**. Headless služba pro Raspberry Pi nadále obsahuje webový panel jako alternativní uživatelské rozhraní pro zařízení bez monitoru.
- Inbox přijímá **APRS RF zprávy** z USB KISS TNC, nikoliv automatické IS→RF. Příjem pro `OK5TVR`, `OK5TVR-10` a další vlastní SSID nastav v záložce **Zprávy**.
- GPS vzdálenost v telemetrii je odvozena z pozic hlášených stanic, nikoli z měření přímého rádiového dosahu.
- Historie přijatých rámců je omezená; pro dlouhodobou diagnostiku používej SQLite deník (výchozí limit 20 000 událostí).
- Databáze a zabezpečené nastavení se sdílejí s headless verzí, ale **nesmí být současně otevřené dvě aktivní aplikace** se stejným rádiem.

## Kontrola bez fyzické radiostanice

```bat
py -3 -m unittest discover -p "test*.py" -q
```

Nativní GUI prošlo vykreslením všech záložek a simulovaným RX rámcem. Fyzický RX/TX, DIGI a telemetrie ve verzi 1.8 ještě potřebují provozní zkoušku s UV-K1(8).

## Přenos na Raspberry Pi

Nativní desktop je určen pro Windows. Raspberry Pi nadále používá `aprs_service.py` s webovou správou v LAN, protože při bezobslužném provozu není třeba grafické prostředí. Backend RF zpráv, objektů, telemetrie a nastavení je společný.

73, OK5TVR.
