"""CZ/EN presentation-only translations for the Tkinter desktop monitor.

Protocol text, callsigns, messages and raw packet bytes are NEVER translated.
"""
from __future__ import annotations

EN = {
    'Sériový port': 'Serial port', 'Připojit': 'Connect', 'Odpojit': 'Disconnect',
    'Ukázkový rámec': 'Demo frame', 'Export CSV': 'Export CSV',
    'APRS mapa / web': 'APRS map / web', 'APRS zprávy': 'APRS messages',
    'APRS objekty': 'APRS objects', 'Diagnostika': 'Diagnostics',
    'Otestovat TX...': 'Test TX...',
    'iGate APRS-IS...': 'APRS-IS iGate...', 'APRS DIGI...': 'APRS DIGI...',
    'Pozice iGate / GPS...': 'iGate / GPS position...', 'Web v LAN...': 'Web on LAN...',
    'PŘIJATÉ AX.25 / APRS RÁMCE': 'RECEIVED AX.25 / APRS FRAMES',
    'PODROBNOSTI VYBRANÉHO RÁMCE / HEX': 'SELECTED FRAME DETAILS / HEX',
    'DIGI / iGate po startu VYPNUTY · vlastní GPS pouze APRS-IS · web pouze čte':
        'DIGI / iGate DISABLED at startup · own GPS to APRS-IS only · read-only web',
    'Čas':'Time','Zdroj':'Source','Cíl':'Destination','Cesta':'Path','Typ':'Type',
    'Obsah / dekódovaná zpráva':'Contents / decoded message',
    'Chybné':'Invalid','Ovládací KISS':'KISS controls','Rámce':'Frames',
    'Nepřipojeno':'Disconnected','Odpojeno':'Disconnected','Připojeno':'Connected',
    'Otevírám ':'Opening ', 'Odpojuji':'Disconnecting',
    'Není nainstalován pyserial':'pyserial is not installed','Žádný COM port nenalezen':'No COM port found',
    'Web server nelze spustit: ':'Unable to start web server: ',
    'Odpojuji sériový port ...':'Closing serial port...',
    'DIGI: paket předán USB KISS TNC (RF ověř druhým přijímačem)':
        'DIGI: packet handed to USB KISS TNC (verify RF with a second receiver)',
    'TX: rámec předán USB KISS TNC (RF ověř druhým přijímačem)':
        'TX: frame handed to USB KISS TNC (verify RF with a second receiver)',
    'Přidán ukázkový rámec (nejedná se o skutečný příjem)':'Demo frame added (not received over RF)',
    'Zatím žádný rámec. Zapni v radiostanici KISS TNC a stiskni na ní 2 pro USB test.\nPro ověření programu bez stanice klikni na Ukázkový rámec.':
        'No frames yet. Start KISS TNC on the radio and press 2 for a USB test.\nTo check the program without a radio, click Demo frame.',
    'Nejprve vyber sériový port. Zkus tlačítko ⟳.':'Select a serial port first. Try the ⟳ button.',
    'Chybí knihovna pyserial.\nSpusť spustit.bat nebo:\npy -3 -m pip install pyserial':
        'pyserial is missing.\nRun spustit.bat or:\npy -3 -m pip install pyserial',
    'Zatím nejsou žádné rámce k exportu.':'There are no frames to export yet.',
    'Webové rozhraní neběží.':'The web interface is not running.',
    'Webové rozhraní není dostupné.':'The web interface is unavailable.',
    'KISS TNC – ruční TX test':'KISS TNC – manual TX test',
    'JEDNORÁZOVÝ TX TEST PŘES USB KISS':'SINGLE TX TEST OVER USB KISS',
    'Na UV-K1(8) přepni tlačítkem 3 z RX ONLY na TX.':'On UV-K1(8), press 3 to switch from RX ONLY to TX.',
    'Ověř 144,800 MHz FM, anténu, výkon a správnou značku.':
        'Check 144.800 MHz FM, antenna, RF power and callsign.',
    'Zdroj / SSID':'Source / SSID','Cesta (vol.)':'Path (optional)','Text statusu':'Status text',
    'Test je APRS status: ZDROJ>APRS[,CESTA]:>TEXT. Cesta je bez WIDE (DIRECT).':
        'This is an APRS status frame: SOURCE>APRS[,PATH]:>TEXT. No WIDE path means DIRECT.',
    'Odeslat 1 APRS TX rámec':'Send one APRS TX frame',
    'Nejprve vypni automatický digipeater, aby se nemísily TX rámce.':
        'Disable the automatic digipeater first to avoid competing TX frames.',
    'Nejprve připoj COM port radiostanice.':'Connect the radio COM port first.',
    'Mezi dvěma ručními testy vyčkej alespoň 20 sekund.':'Wait at least 20 seconds between manual tests.',
    'Potvrdit vysílání':'Confirm RF transmission',
    'Rámec nebyl přijat do fronty (obsazeno nebo odpojování).':'Frame not queued (busy or disconnecting).',
    'Odeslání do USB fronty potvrzeno. Sleduj TX počítadlo a displej rádia; fyzický přenos tím ještě není prokázán.':
        'Frame queued for USB. Check TX counter and radio display; this does not prove on-air transmission.',
    'APRS-IS iGate – pouze RF → internet':'APRS-IS iGate – RF → internet only',
    'APRS iGATE – RF → APRS-IS':'APRS iGATE – RF → APRS-IS',
    'Bez APRS-IS → RF. Program z internetu nikdy automaticky nevysílá.':
        'No APRS-IS → RF gateway. The program never transmits packets from the internet automatically.',
    'Volací značka':'Callsign','APRS-IS passcode':'APRS-IS passcode','Server':'Server','TCP port':'TCP port',
    'Passcode je potřeba pro ověřené přihlášení. Nikdy se neukládá do souboru.':
        'Passcode is required for verified login. It is never saved to a file.',
    'Nastavení vlastní GPS pozice / APRS-IS majáku...': 'Configure own GPS position / APRS-IS beacon...',
    'U přijatých RF paketů se přidá qAO,IGATECALL (receive-only iGate).':
        'Received RF packets are tagged with qAO,IGATECALL (receive-only iGate).',
    'Aktivní':'Active','Vypnuto':'Disabled','Zapnuto':'Enabled',
    'iGate už běží. Nejprve ji vypni.':'iGate is already running. Disable it first.',
    'Oprav značku, numerický passcode (0–32767), server a port.':
        'Correct the callsign, numeric passcode (0–32767), server and port.',
    'Povolit RF→APRS-IS':'Allow RF → APRS-IS',
    'Spustit iGate':'Start iGate','Vypnout iGate':'Stop iGate',
    'Poloha GPS iGate a APRS-IS maják':'iGate GPS location and APRS-IS beacon',
    'GPS POLOHA STANICE / APRS-IS':'STATION GPS LOCATION / APRS-IS',
    'Poloha se ukládá lokálně. Zveřejnění vyžaduje zapnutý APRS-IS maják.':
        'Position is stored locally. Publishing requires an enabled APRS-IS beacon.',
    'Zeměpisná šířka':'Latitude','Zeměpisná délka':'Longitude',
    'Desetinné stupně: N/E kladné, S/W záporné (např. 49.7384, 13.3736).':
        'Decimal degrees: N/E positive, S/W negative (e.g. 49.7384, 13.3736).',
    'Lokátor (přibližně)':'Maidenhead grid (approximate)',
    'Použít střed lokátoru':'Use grid square center',
    'Střed lokátoru není přesná GPS poloha. Pro skutečnou polohu zadej souřadnice.':
        'Grid square center is not an exact GPS position. Enter coordinates for a precise QTH.',
    'Interval majáku':'Beacon interval','min. · symbol R& (receive-only iGate)':'min · R& symbol (receive-only iGate)',
    'Zveřejnění GPS na APRS-IS':'Publish GPS position on APRS-IS',
    'Nastavení GPS':'GPS settings','Uložit polohu / nastavení':'Save position / settings',
    'APRS DIGI repeater přes USB KISS':'APRS DIGI repeater via USB KISS',
    'APRS DIGIPEATER – PC → USB KISS → RF':'APRS DIGIPEATER – PC → USB KISS → RF',
    'Na rádiu spusť KISS TNC s povoleným TX. Interní APRS DIGI musí být vypnuté.':
        'Start KISS TNC on the radio with TX enabled. Internal APRS DIGI must be disabled.',
    'Vlastní značka DIGI':'Own DIGI callsign','Režim':'Mode',
    'Regionální WIDE1 + WIDE2':'Regional WIDE1 + WIDE2',
    'V regionálním režimu navíc TRACE2-1 / TRACE2-2':
        'Also support TRACE2-1 / TRACE2-2 in regional mode',
    'Odklad / viscous (s)':'Retransmission delay / viscous (s)',
    'Maximum TX / min':'Maximum TX / min','Min. odstup TX (s)':'Minimum TX gap (s)',
    'Deduplikace 30 s · max. 8 AX.25 hops · první nevyužitý hop · bez preempce.':
        '30 s duplicate window · max. 8 AX.25 hops · first unused hop · no preemption.',
    'Ignoruje 3rd-party / TCPIP / TCPXX a obecné dotazy. NOGATE/RFONLY zůstává jen na RF.':
        'Ignores 3rd-party / TCPIP / TCPXX and general queries. NOGATE/RFONLY stays on RF.',
    'Povolit automatické RF vysílání':'Allow automatic RF transmission',
    'Nejprve vypni běžící DIGI.':'Stop the running DIGI first.',
    'Nejprve připoj USB KISS TNC.':'Connect USB KISS TNC first.',
    'Spustit DIGI':'Start DIGI','Vypnout DIGI':'Stop DIGI','Test pravidel (bez RF)':'Test rules (no RF)',
    'Webový přístup v LAN':'LAN web access','Mapa v telefonu':'Phone map','Web v LAN':'Web on LAN',
    'Uložit':'Save',
}

PREFIXES = {
    'Chyba spojení: ':'Connection error: ',
    'Chyba zápisu TX do USB: ':'USB TX write error: ',
    'Soubor se nepodařilo uložit:\n':'Could not save file:\n',
    'Opr av konfiguraci: ':'Correct configuration: ',
    'DIGI zapnuto · automatické retransmise povoleny':'DIGI enabled · automatic retransmissions allowed',
    'DIGI vypnuté. Rozpracované čekající rámce zrušeny.':'DIGI disabled. Pending frames cancelled.',
    'Web: startuje...':'Web: starting...',
    'Připojeno k ':'Connected to ',
    'Otevírám ':'Opening ',
}


def translate(value: str, language: str = 'cs') -> str:
    """Only translate known UI strings; never alter unknown packet information."""
    text = str(value)
    if language != 'en':
        return text
    if text in EN:
        return EN[text]
    for original, english in PREFIXES.items():
        if text.startswith(original):
            return english + text[len(original):]
    return text
