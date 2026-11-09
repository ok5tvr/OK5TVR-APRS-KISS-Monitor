# OK5TVR APRS KISS Monitor — Raspberry Pi Web v1.9 preview

Nové webové rozhraní má stejných sedm hlavních záložek jako Windows v1.8.2 RC1: Příjem/TX, Mapa, Zprávy, Objekty, iGate/DIGI, Telemetrie a Diagnostika/deník. Používá stejný APRSService backend; nevytváří další připojení k USB KISS TNC. Mapu, zprávy, objekty a správu přebírá ze stávajících webových stránek. Nové jsou společná navigace, panel RX/TX a samostatná telemetrie.

## Instalace na Raspberry Pi OS / Debian 13

Na Raspberry Pi otevři terminál a zadej:

    sudo apt-get update
    sudo apt-get install -y git
    git clone --branch feature/raspberry-unified-web-v1.9 https://github.com/ok5tvr/OK5TVR-APRS-KISS-Monitor.git
    cd OK5TVR-APRS-KISS-Monitor
    sh install_raspberry.sh --lan

Před reinstalací existující služby zazálohuj soubory ve složce ~/.config/ok5tvr-aprs/ (config.json, secrets.json a SQLite databáze). Instalační skript používá existující nastavení a spouští službu ok5tvr-aprs.

1. Připoj Quansheng UV-K1(8) datovým USB-C kabelem. Zapni aplikaci KISS TNC ve F4HWN Labs, nastav 144,800 MHz FM, KISS TX zapínej pouze pro vysílání. Při DIGI přes Raspberry vypni interní APRS DIGI na radiostanici.
2. Ověř port: ls -l /dev/ttyACM*
3. Ověř službu: sudo systemctl status ok5tvr-aprs --no-pager
4. Zobraz své soukromé odkazy:

    python3 /opt/ok5tvr-aprs/aprs_service.py --config "$HOME/.config/ok5tvr-aprs/config.json" --links

5. Ve vypsaném admin odkazu změň pouze část /control na /unified, administrátorský token ponech beze změny. Výsledná adresa bude ve formátu:

    http://IP_RASPBERRY:8765/unified?admin=TVUJ_SOUKROMY_TOKEN

6. V Příjem / TX obnov USB porty, vyber zařízení, připoj a zkontroluj tabulku přijatých rámců. Nastavení iGate/DIGI je v příslušné záložce.

## Online mapa bez API klíče

V záložce **Mapa** vyber **Mapa ulic (OpenStreetMap)** nebo **Tmavá mapa (OpenStreetMap)**. Oba režimy využívají dlaždice OpenStreetMap bez API klíče; tmavý režim je barevná úprava stejných dlaždic v prohlížeči. Offline mapa dál funguje i bez internetu.

Veřejný tile server OpenStreetMap je určen pro přiměřený provoz; respektuj jeho podmínky, atribuci a zákaz hromadného stahování. Pro větší počet uživatelů / komerční nasazení použij vlastní či smluvně provozovaný mapový podklad. Po aktualizaci vynuceně obnov stránku (Ctrl+F5), aby se nepoužil starý JavaScript.

## Grafické APRS symboly (PNG, offline)

Na mapě se podle dvouznakového APRS symbolového kódu automaticky zobrazují originální rastrové ikonky (například auto, digipeater, iGate, meteorologická stanice, dům, letadlo). Používají se místní PNG atlasové soubory v `assets/`, takže zobrazení ikon nepotřebuje internet. K dispozici je primární tabulka `/`, alternativní tabulka `\\` i překryvná písmena/číslice pro symboly alternativní tabulky. Pokud paket symbol neobsahuje, zobrazí se původní obecná značka. U nekomprimovaných, komprimovaných a Mic-E pozic i APRS objektů se zachová symbol z přijatého paketu; při příjmu statusu bez polohy se symbol nemaže.

Před aktualizací zkontroluj a případně zazálohuj nastavení: `cp -a ~/.config/ok5tvr-aprs ~/ok5tvr-aprs-backup-$(date +%Y%m%d)`. Instalace provádí aktualizaci bez vymazání existující konfigurace.

Zdroj grafiky: [OH7LZB/aprs.fi APRS symbols](https://github.com/hessu/aprs-symbols), podrobnosti o autorství a licencích jednotlivých ikon jsou uvedeny v [COPYRIGHT.md](https://github.com/hessu/aprs-symbols/blob/master/COPYRIGHT.md). Nepoužívej tyto značky k domněnce o potvrzení RF příjmu; jde o data přenesená v APRS paketu.

## 5palcový HDMI displej 800 × 480: místní monitor příjmu

Na Raspberry Pi 2 Model B (v1.1) lze volitelně zobrazit přehled přímo na připojeném HDMI displeji, například s řadičem dotyku XPT2046. Program používá lehký `tkinter`, nikoliv Chromium. Lokální okno zobrazuje připojení USB KISS, nastavený a skutečný port, stav APRS-IS a DIGI, čítače RX/TX, počet stanic, čas posledního RF příjmu a sedm posledních dekódovaných rámců včetně DIRECT/VIA.

**Požadavky:** Raspberry Pi OS **Desktop** a přihlášená grafická relace (pro trvalý provoz doporučené automatické přihlášení). Raspberry Pi OS Lite samo o sobě nemá grafickou plochu; pouze připojení HDMI displeje nestačí. Pro XPT2046 dotykové ovládání je nutné případně samostatně nastavit SPI dotykový ovladač; **zobrazení obrazu po HDMI není na dotyku závislé**.

Po aktualizaci:
1. Spusť `sh install_raspberry.sh --lan` v nové složce projektu. Instalátor přidá `python3-tk` a soubor `~/.config/autostart/ok5tvr-aprs-hdmi.desktop` pro spuštění na grafické ploše.
2. Přihlas se do desktopu Raspberry znovu nebo restartuj Raspberry (`sudo reboot`).
3. Otevři webovou konzoli `/unified?admin=...`, na záložce **Příjem / TX** zaškrtni **Místní panel na HDMI displeji Raspberry Pi**.
4. Do přibližně dvou sekund se na připojeném HDMI displeji zobrazí informační okno. Zrušením zaškrtnutí se skryje; nastavení zůstane uloženo i po restartu.

Panel se spouští **nezávisle** na systému `ok5tvr-aprs.service`, který jako jediný používá USB KISS port. Pouze pro čtení dotazuje `http://127.0.0.1:8765/api/local-display` (port se bere z lokálního `config.json`); koncový bod je dostupný jen přes loopback a neobsahuje admin token ani hesla. Vypnutí či zavření grafického panelu nepřeruší příjem ani iGate/DIGI.

Režim celé obrazovky přepne klávesa **F11**, **Esc** zobrazuje okno. Pro první nastavení rozlišení HDMI připojený panel ověř pomocí `xrandr` (X11) nebo odpovídajících nástrojů Wayland/compositoru. Displej označený 5inch HDMI Display 800 × 480 / XPT2046 se pro zobrazení připojuje HDMI a samostatné SPI piny jsou určeny pro dotyk.

## Důležité

- Port 8765 a administrátorský odkaz nevystavuj přímo do internetu. Používej důvěryhodnou LAN nebo VPN s vhodně zabezpečeným přístupem.
- Viewer token nepovoluje administrátorské API ani nové rozhraní.
- DIGI a automatické RF vysílání zůstávají chráněné potvrzením. Zápis do USB KISS neprokazuje skutečné odvysílání.
- Stejnou radiostanici nesmí současně obsluhovat dvě instance programu.
- Změna portu nebo telemetrie může vypnout běžící iGate/DIGI; poté je zapni ručně.
- Desktop pro Windows nebyl v této větvi změněn.
- Hardware RX/TX vyžaduje test na skutečné UV-K1(8), ideálně s druhým přijímačem.

## Testy

    python3 -m unittest discover -p 'test*.py' -q

Jde o vývojovou větev, nikoliv finální vydání.