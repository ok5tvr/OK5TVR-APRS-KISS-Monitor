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