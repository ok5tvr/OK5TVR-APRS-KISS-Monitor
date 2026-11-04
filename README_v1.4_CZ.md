# OK5TVR APRS KISS Monitor v1.4 – APRS zprávy na PC a Raspberry Pi

**Novinka:** samostatná webová stránka **APRS Zprávy** s Inboxem, Outboxem, výběrem cíle, RF cestou, ACK/REJ a trvalou historií v SQLite.

Vychází z fungující verze 1.3. Zachovává APRS RX/TX, offline mapu, GPS iGate, jednosměrnou RF→APRS-IS bránu, DIGI a statistiky.

## Důležité: jakou variantu programu spustit

- **Webová služba** `aprs_service.py` obsahuje **APRS Zprávy** a je určena pro Windows i Raspberry Pi. Používá stejný USB KISS jako dříve.
- **Původní Windows GUI** `aprs_kiss_monitor.py` zůstává zachované, ale nová stránka Zprávy je součástí **webové služby**, nikoliv tohoto staršího Tkinter okna.
- **Nespouštěj zároveň webovou službu a staré GUI**, pokud mají použít tentýž COM port; sériový port může obsluhovat jen jedna aplikace.

## Instalace na Raspberry Pi OS / Debian

Pokud už používáš v1.3, **znovu spusť instalační skript z nové rozbalené složky**. Nastavení a tokeny v `~/.config/ok5tvr-aprs/` zůstanou zachované.

```bash
sh install_raspberry.sh --lan
sudo systemctl status ok5tvr-aprs
python3 /opt/ok5tvr-aprs/aprs_service.py --links
```

Poslední příkaz zobrazí tři odkazy: `map`, `admin`, **`messages`**. Otevři `messages` na PC nebo telefonu ve stejné LAN. Použij síť pouze pro důvěryhodné klienty; přístupové klíče nejsou určené pro veřejný internet.

Služba se automaticky připojuje k UV-K1(8), pokud je spuštěna aplikace **KISS TNC**. Rádio nastav na **144,800 MHz FM**, vypni CTCSS/DCS, připoj datové USB-C a pro vysílání povol režim **TX**, nikoliv `RX ONLY`.

Pro trvalý provoz se služba spouští automaticky přes systemd. Současný firmware UV-K1(8) musí mít aplikaci KISS TNC ručně zapnutou, dokud v novém vydání nepřibude slibovaný automatický start.

### Diagnostika

```bash
sudo journalctl -u ok5tvr-aprs -f
ls -l /dev/serial/by-id/
ls /dev/ttyACM*
```

## Spuštění na Windows

1. Rozbal ZIP a nainstaluj Python 3, pokud chybí.
2. Připoj UV-K1(8) a spusť na radiostanici `KISS TNC` s povoleným TX.
3. Spusť `spustit_sluzbu_windows.bat` (nikoli `spustit.bat`, který spouští staré GUI).
4. V dalším okně spusť `zobrazit_odkazy_windows.bat` a otevři odkaz **messages**.
5. Pokud máš více COM portů, v **ADMIN** nastav správný port a ulož.

Výchozí web je dostupný jen na stejném počítači (localhost). Přístup z dalších zařízení lze povolit ve webové konfiguraci, ale změna vyžaduje restart služby. Nic nepřesměrovávej na veřejný internet.

## Stránka APRS Zprávy

### Odeslat zprávu

1. Zadej **cílovou značku**, včetně případného SSID, např. `OK1ABC-9`.
2. Vyber **cestu**: `DIRECT` (bez DIGI), `WIDE1-1`, `WIDE2-1`, `WIDE1-1,WIDE2-1`, nebo krátkou vlastní cestu (nejvýše dva hopy). Nepoužívej nadměrné cesty.
3. Napiš **1 až 67 tisknutelných znaků ASCII** bez diakritiky a `{}`. Zprávy nejsou soukromé.
4. Klikni **Odeslat přes RF** a potvrď skutečné vysílání. Program přidá třímístné ID, např. `{001`, a předá rámec do USB KISS.
5. **Outbox** ukazuje `Čeká na USB`, `Čeká na ACK`, `ACK přijato`, `REJ`, `Bez ACK`, `Zrušeno` nebo `Přerušeno`.

**Pozor:** „Předáno do USB“ není záruka, že UV-K1(8) skutečně vysílala! KISS TNC musí mít aktivní TX a anténa musí být připojena.

### Přijmout zprávu

- **Inbox** ukládá zprávy s adresátem **shodným s vlastní značkou iGate**, např. `OK5TVR-10`. Ostatní APRS pakety zůstávají ve standardním monitoru.
- Opakované přijetí stejné zprávy (stejný odesílatel, ID a obsah) do 15 minut nezaloží nový řádek; zvýší se počitadlo opakování.
- Pokud zpráva obsahuje ID, lze ji **ručně potvrdit ACK** nebo **odmítnout REJ**. Obě funkce mohou vysílat RF a vyžadují potvrzení.
- V nastavení lze **výslovně povolit automatický ACK**. Tento režim je při první instalaci vypnutý. Zapnutí se uloží i pro restart služby.
- Příchozí ACK nebo REJ se přiřadí pouze k čekající zprávě **se správnou značkou odesílatele a odpovídajícím ID**.

### Opakování

- Standardně nejvýše **3 vysílání** s prodlužujícími se intervaly 45 a 90 sekund; v nastavení lze zvolit interval 30–180 s a 1–5 odeslání.
- Při přijetí odpovídajícího ACK nebo REJ se opakování zastaví.
- **Zrušit opakování** zruší další pokusy, ale rámec již předaný USB nelze vzít zpět.
- Při restartu služby či přerušení USB se čekající zprávy označí `Přerušeno` a **nezačnou se samy znovu vysílat**. Můžeš je znovu napsat ručně.

### Výchozí cíl a cesta

Na stránce lze uložit výchozí cílovou značku, RF cestu, interval opakování, maximální počet TX a automatické ACK. Vlastní odesílací značka je sdílená s konfigurací iGate a mění se v hlavní správě na stránce **ADMIN**. Změna konfigurace zpráv přeruší rozpracované odchozí pokusy z bezpečnostních důvodů.

## Co znamená iGate vs. APRS zprávy

- Zprávy se **odesílají a přijímají na místním RF kanálu přes USB KISS**.
- Pokud je zapnutá iGate, platné přijaté RF zprávy se mohou standardně předávat do APRS-IS.
- **Příchozí APRS-IS → RF není implementováno.** Tato verze nemění jednosměrný režim iGate a nezajišťuje doručení internetové odpovědi na RF.
- Automatické ACK nebo ruční odpověď používají nastavenou RF cestu. Používej krátkou cestu a dodržuj místní APRS plán.
- Pro přijetí ACK musí být skutečné obousměrné RF pokrytí. I přijaté ACK je jen protokolové potvrzení, nikoli potvrzení přečtení osobou.

## Ukládání historie a bezpečnost

Konfigurace a klíče jsou v `~/.config/ok5tvr-aprs/`:

- `config.json` – veřejně nebezpečné nastavení, bez tajných údajů.
- `secrets.json` – administrátorský/viewer token a APRS-IS passcode.
- `messages.sqlite3` – **Inbox/Outbox** a ID zpráv (na Linuxu soubor s právy 0600). Historie je omezená na 500 příchozích a 500 dokončených odchozích záznamů.

Zprávy vidí jen uživatel se soukromým **ADMIN odkazem**, nikoli běžný návštěvník mapy. Web používá **nešifrované HTTP**; používej pouze důvěryhodnou LAN nebo vlastní VPN, ne veřejný port. APRS zprávy jsou samy o sobě veřejné a mohou být zobrazeny na APRS-IS.

## Ověření a omezení

Aplikace byla testována automatickými testy protokolu, databáze, webové autorizace, sériové komunikace s **virtuálním KISS TNC** a falešným APRS-IS serverem. Skutečné RF odesílání zpráv a přijímání ACK s UV-K1(8) zatím musíš ověřit na svém zařízení.

APRS-IS stránka pro zprávy zatím neposkytuje samostatnou internetovou textovou konverzaci. Není podporováno automatické předávání zpráv z internetu do RF (dvousměrný IGate), SMS, šifrování ani přenos přes více rádiových portů.

## Standardy

- [APRS Protocol Reference v1.0.1, kapitola 14](https://www.aprs.org/doc/APRS101.PDF)
- [WB2OSZ – Understanding APRS Packets](https://github.com/wb2osz/aprsspec)
- [APRS-IS IGate Details](https://www.aprs-is.net/IGateDetails.aspx)
