# OK5TVR APRS KISS Monitor 1.6.0-rc1 – CZ

**Vývojová verze** pro Windows, Raspberry Pi OS a Debian. Vychází z odzkoušeného příjmu/vysílání pomocí Quansheng UV-K1(8) + F4HWN Labs KISS TNC. Nové objekty, dlouhodobá služba, iGate a DIGI jsou zatím ověřeny **simulovanou komunikací**, nikoli kompletním trvalým provozem na skutečném RF.

## Rychlá instalace

Raspberry Pi / Debian:

```sh
git clone https://github.com/ok5tvr/OK5TVR-APRS-KISS-Monitor.git
cd OK5TVR-APRS-KISS-Monitor
sh install_raspberry.sh --lan
python3 /opt/ok5tvr-aprs/aprs_service.py --links
sudo systemctl status ok5tvr-aprs
```

Při aktualizaci z existující verze stačí v aktualizované složce znovu spustit instalátor. `--lan` používej pouze v důvěryhodné místní síti. Službu ovládá systemd. Konfigurace je v `~/.config/ok5tvr-aprs/config.json`, citlivé údaje samostatně v `secrets.json` (práva 0600).

Windows: spusť `spustit_sluzbu_windows.bat`, poté `zobrazit_odkazy_windows.bat`. Původní grafický monitor (`spustit.bat`) a webová služba nesmí používat stejný COM port současně.

## Nové stránky

Odkazy získáš příkazem `python3 /opt/ok5tvr-aprs/aprs_service.py --links`:

| Stránka | Funkce |
| --- | --- |
| `map` | Příjem, offline mapa, statistiky, upozornění na USB/ticho |
| `admin` | Nastavení KISS, iGate, GPS a DIGI |
| `messages` | Inbox, Outbox, RF zprávy, ACK/REJ |
| `objects` | APRS objekty, items, jednorázový status a vlastní pozice |
| `diagnostics` | Stav KISS/APRS-IS/DIGI, deník, CSV export, zálohy |

Přepínač **CZ / EN** je dostupný na všech webových stránkách. Volba jazyka se ukládá v prohlížeči, ne do APRS paketů.

## 1. APRS objekty a položky (RF)

Otevři **Objekty a RF** → zadej název (1–9 znaků, rozlišují se velká/malá písmena), typ **Object** nebo **Item**, zeměpisnou šířku/délku, APRS symbol, ASCII komentář, cestu (např. `WIDE1-1`) a případný interval opakování. Klikni na **Uložit objekt bez TX**.

- **Vyslat LIVE:** do USB KISS vloží jeden AX.25 UI rámec. Během testu musí být v radiostanici aktivní `KISS TNC` s povoleným TX, nikoliv `RX ONLY`.
- **KILL:** odešle ukončovací objekt (`_`) nebo item (`_`). Po odeslání se pro daný objekt vypne opakování, aby nebyl znovu oživen.
- **Start opakování:** po výslovném potvrzení periodicky vysílá pouze označené objekty, v intervalu nejméně 10 min. Vysílání je navíc omezené společnou 45sekundovou prodlevou.
- **Stop opakování:** zruší budoucí plánované rámce. **Opakování se po restartu ani odpojení USB nezapne samo.**
- **Odeslat status / pozici:** jednorázový RF status (`>`) nebo polohový paket (`!`) z uložené GPS iGate, s potvrzením.

APRS objekt obsahuje 9znakové jméno, příznak LIVE/KILL, UTC čas (`DDHHMMz`), souřadnice a symbol. APRS item UTC čas nemá. **Zdrojová značka rámce je značka iGate v nastavení.** Nepoužívej neplatnou nebo cizí značku; vytvářej jen objekty, které smíš zveřejnit.

**Pozor:** „odesláno do USB“ neznamená „úspěšně odvysíláno do éteru“. F4HWN KISS nepotvrzuje skutečný RF výstup ani přijetí protistanicí. Ověř druhým přijímačem/APRS-IS.

## 2. Diagnostika a provozní deník

Stránka **Diagnostika a deník** nabízí:

- stav USB, poslední validní APRS rámec, počet opětovných připojení, APRS-IS přihlášení, statistiky DIGI a aktivitu plánovaných objektů,
- záznamy **RX / TX / IS / DROP / SYSTEM** v SQLite `events.sqlite3`, včetně zamítnutých rámců a zdůvodnění,
- filtry, export posledních 2 000 záznamů do CSV a ruční vymazání deníku,
- konfigurovatelné varování při odpojení USB (výchozí 15 s) a dlouhém tichu APRS (výchozí 30 min).

USB CDC port ve stavu *Connected* potvrzuje jen otevřené sériové spojení. **Bez příjmu paketů nelze bezpečně rozlišit neaktivní rádio od tichého kanálu.** Program proto tento stav označuje jako varování, nikoliv dokázanou poruchu. Upozornění je viditelné na webu a v deníku; nejde o push notifikaci nebo e-mail.

## 3. Záloha a obnova konfigurace

Na stránce diagnostiky klikni na **Stáhnout zálohu JSON**. Soubor zahrnuje GPS, volací značky, APRS cesty, nastavení a uložené objekty. **Neobsahuje** APRS-IS passcode, administrátorský ani prohlížecí token, historii zpráv, deník ani žádné jiné klíče.

Při obnově vyber JSON a potvrď import. Program provede validaci, nastaví **iGate autostart OFF, DIGI autostart OFF, auto ACK OFF**, zastaví případné automatické objektové vysílání a ponechá místní tajné klíče. Při přesunu na jiné Raspberry Pi je nutné znovu zadat APRS-IS passcode. Změna webového portu nebo LAN nastavení vyžaduje restart služby.

## 4. Bezpečnost a doporučený postup testu

1. Připoj UV-K1(8) přes USB a spusť `KISS TNC` na `144.800 MHz FM` s anténou. Nejdříve ověř příjem.
2. V `admin` zadej skutečnou značku a GPS; zkontroluj stav diagnostiky.
3. V `objects` ulož zkušební objekt a proveď **jeden ručně potvrzený RF TX**.
4. Zkontroluj příjem druhým rádiem nebo na APRS-IS (pokud byl rámec zachycen aktivní iGate).
5. Před spuštěním DIGI vypni samostatnou aplikaci APRS DIGI na UV-K1; opakování smí řídit pouze jedno zařízení.
6. Pravidelné RF vysílání a automatické iGate/DIGI povol až po ověření provozu a místní APRS koordinace.

Přístup ke správě je chráněn tajným tokenem v URL. Používá se HTTP, **nepřesměrovávej port do veřejného internetu**. Pro přístup mimo LAN použij VPN. Do veřejného GitHubu nikdy neodesílej `config.json`, `secrets.json`, databáze, logy ani exporty s osobní GPS polohou.

### Co zatím není hotové

Nejsou implementovány bidirectional APRS-IS → RF message gating, přímá senzorová meteorologická telemetrie ani skutečné sledování GPS pohybu stanice. Nejde o zcela úplnou implementaci všech variant APRS 1.0.1. Další etapou je dlouhodobé ověření 24/7, zkouška KISS TX objektů, DIGI a zpráv na skutečném RF, a pak stabilní release.

Dokumentace protokolu: [APRS Protocol Reference](https://www.aprs.org/doc/APRS101.PDF), [APRS-IS IGate Details](https://www.aprs-is.net/IGateDetails.aspx).

**73, OK5TVR**
