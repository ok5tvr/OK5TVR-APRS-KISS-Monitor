/* OK5TVR APRS Monitor: Czech / English UI, no translation of packet contents. */
"use strict";
(() => {
const english = {
  "Jazyk / Language": "Language / Jazyk",
  "Nastavení": "Settings",
  "Mapa a statistiky": "Map & statistics",
  "Obnovit": "Refresh",
  "Připojeno": "Connected",
  "Odpojeno": "Disconnected",
  "Zapnuto": "Enabled",
  "Vypnuto": "Disabled",
  "Chyba": "Error",
  "Nedostupné": "Unavailable",
  "Načítám…": "Loading…",
  "Inicializuji…": "Initializing…",
  "Chybí": "Missing",
  "Uloženo bezpečně": "Saved securely",
  "OK5TVR APRS KISS – živá mapa": "OK5TVR APRS KISS – live map",
  "· živá mapa": "· live map",
  "Rádio: odpojeno": "Radio: disconnected",
  "iGate: vypnuto": "iGate: disabled",
  "DIGI: vypnuto": "DIGI: disabled",
  "Přijaté RF rámce": "Received RF frames",
  "Slyšené stanice": "Heard stations",
  "Polohy na mapě": "Positions on map",
  "TX předané do USB": "TX frames submitted to USB",
  "Vlastní APRS-IS majáky": "Own APRS-IS beacons",
  "Mapa přijatých APRS pozic": "Map of received APRS positions",
  "Mapa ulic (CARTO)": "Street map (CARTO)",
  "Tmavá (CARTO)": "Dark (CARTO)",
  "Offline mapa – bez internetu": "Offline map – no internet",
  "Zobrazit všechny": "Show all",
  "Načítám lokální geografická data…": "Loading local geographic data…",
  "Žlutá značka označuje vlastní nastavenou GPS polohu iGate (není započtena mezi přijaté stanice). Pohyb: tažení myší nebo prstem · Přiblížení: kolečko myši, tlačítka +/− · Kliknutí na stanici zobrazí souřadnice": "The yellow marker shows the configured iGate location (not counted among RF stations). Drag to pan · Mouse wheel or +/− to zoom · Select a station to view coordinates",
  "Poslední slyšené stanice": "Recently heard stations",
  "Stanice": "Station",
  "Pakety": "Packets",
  "Poslední příjem": "Last heard",
  "Poslední přijaté rámce": "Recently received frames",
  "(DEMO se neodesílají do APRS-IS)": "(DEMO frames are not sent to APRS-IS)",
  "Čas": "Time",
  "Zdroj": "Source",
  "Typ": "Type",
  "APRS cesta": "APRS path",
  "Dekódováno": "Decoded",
  "Web pouze pro čtení · nedovoluje vysílat ani měnit nastavení iGate.": "Read-only web dashboard · cannot transmit or change iGate settings.",
  "Filtrovat podle značky…": "Filter by callsign…",
  "Mapový podklad": "Map layer",
  "Interaktivní mapa APRS stanic": "Interactive APRS station map",
  "Přiblížit": "Zoom in",
  "Oddálit": "Zoom out",
  "Načítám online mapu CARTO… mezitím je vidět offline geografie.": "Loading online CARTO tiles… offline geography remains visible.",
  "Offline mapa · hranice států, pobřeží a řeky · bez internetu": "Offline map · borders, coasts and rivers · no internet",
  "Online mapa CARTO · podklad načten": "CARTO online map · tiles loaded",
  "Offline geografická data se načítají…": "Loading offline geography…",
  "Offline mapa připravena · bez připojení k mapovým serverům": "Offline map ready · no external map servers required",
  "Neplatný soubor geografických dat": "Invalid geography data file",
  "Nouzové zobrazení souřadnic · pozice stanic jsou dostupné i bez geografického podkladu": "Fallback coordinate view · station positions remain available",
  "Podrobný online podklad se nepodařilo načíst. Zobrazení geografických hranic a poloh stanic funguje bez internetu.": "The detailed online map could not be loaded. Geographic borders and station locations remain available offline.",
  "online dlaždice byly odmítnuty nebo nejsou dostupné": "online map tiles were blocked or unavailable",
  "online mapový server neodpověděl do 8 sekund": "online map server did not respond within 8 seconds",
  "Připojení s monitorem není dostupné": "Monitor connection unavailable",
  "Zobrazit stanici na mapě": "Show station on map",
  "Zavřít": "Close",
  "Poslední": "Last",
  "vlastní": "own",
  "nastavená poloha": "configured position",
  "Rádio: ": "Radio: ",
  "Rádio": "Radio",
  "Aktualizováno ": "Updated ",
  "Spojení s monitorem není dostupné: ": "Monitor connection unavailable: ",
  "Neznámá cesta.": "Unknown route.",
  "OK5TVR – správa APRS služby": "OK5TVR – APRS service management",
  "OK5TVR · APRS KISS služba": "OK5TVR · APRS KISS service",
  "Správa Raspberry Pi / PC bez monitoru. Přenos je HTTP: používej pouze v důvěryhodné LAN, bez přesměrování portu do internetu.": "Headless Raspberry Pi / PC management. HTTP is unencrypted: use only on a trusted LAN; never forward the port to the internet.",
  "Otevřít mapu": "Open map",
  "APRS Zprávy · Inbox / Outbox": "APRS messages · Inbox / Outbox",
  "USB KISS / web": "USB KISS / web",
  "Port (auto, /dev/ttyACM0, COM3)": "Port (auto, /dev/ttyACM0, COM3)",
  "Rychlost USB CDC": "USB CDC baud rate",
  "Interval opakování USB (s)": "USB retry interval (s)",
  "Změna USB portu se projeví po restartu služby. Výchozí režim nevyžaduje displej.": "USB port changes take effect after restarting the service. Headless operation requires no display.",
  "APRS-IS iGate · RF → internet": "APRS-IS iGate · RF → internet",
  "Značka iGate": "iGate callsign",
  "APRS-IS passcode (ponech prázdný pro zachování)": "APRS-IS passcode (leave blank to keep current)",
  "Server": "Server",
  "TCP port": "TCP port",
  "Spustit iGate automaticky po restartu": "Automatically start iGate after reboot",
  "Zapnout iGate": "Enable iGate",
  "Vypnout iGate": "Disable iGate",
  "Vlastní GPS poloha": "Own GPS position",
  "Latitude (desetinné °)": "Latitude (decimal degrees)",
  "Longitude (desetinné °)": "Longitude (decimal degrees)",
  "ASCII komentář": "ASCII comment",
  "Interval majáku (minuty)": "Beacon interval (minutes)",
  "Veřejný APRS-IS poziční maják (ne na RF)": "Public APRS-IS position beacon (not transmitted on RF)",
  "APRS DIGI · opakování na RF": "APRS DIGI · RF digipeating",
  "Značka DIGI": "DIGI callsign",
  "Režim": "Mode",
  "Regionální WIDE1/WIDE2": "Regional WIDE1/WIDE2",
  "Volitelné TRACE2-N": "Optional TRACE2-N",
  "Zpoždění před retransmisí (s)": "Delay before retransmission (s)",
  "Max TX za minutu (1–12)": "Max TX per minute (1–12)",
  "Minimální rozestup TX (s)": "Minimum TX spacing (s)",
  "Po restartu automaticky obnovit DIGI": "Automatically resume DIGI after reboot",
  "Zapnout DIGI": "Enable DIGI",
  "Vypnout DIGI": "Disable DIGI",
  "Na UV-K1 musí být KISS TNC s TX povoleným a interní APRS DIGI vypnutá. PC nemůže potvrdit skutečnou VF retransmisi.": "UV-K1 must run KISS TNC with TX enabled and its internal APRS DIGI disabled. The PC cannot verify actual on-air transmission.",
  "Uložit konfiguraci": "Save configuration",
  "Uložení běžných parametrů nic nevysílá. Změna automatického DIGI se potvrzuje zvlášť. Aktuální běžící iGate/DIGI případně vypni a znovu zapni pro nové parametry.": "Saving ordinary settings does not transmit. Automatic DIGI must be confirmed separately. Restart a running iGate/DIGI to apply changed operational settings.",
  "Uložit nastavení": "Save settings",
  "Jeden testovací APRS status přes RF": "Send one APRS status test over RF",
  "Test vysílání je dostupný pouze po potvrzení; opakované stisky jsou omezené. Nepovoluj TX bez antény a dodržuj pravidla místní APRS sítě.": "TX tests require confirmation and are rate limited. Never enable TX without an antenna; follow local APRS operating rules.",
  "Nastavení načteno. APRS-IS passcode se nezobrazuje.": "Settings loaded. APRS-IS passcode is hidden.",
  "Nelze načíst konfiguraci: ": "Unable to load configuration: ",
  "POZOR: Automatické vysílání DIGI po restartu. Opravdu to povolit?": "WARNING: Automatically start RF DIGI transmission after reboot. Are you sure?",
  "Povolit odesílání skutečně přijatých APRS paketů do veřejné APRS-IS?": "Forward received APRS RF packets to the public APRS-IS network?",
  "POZOR: Povolit automatické retransmise APRS paketů na RF? Interní DIGI je vypnutá a KISS TX povolen?": "WARNING: Enable automatic APRS RF retransmission? Is internal DIGI disabled and KISS TX enabled?",
  "Odeslat JEDEN testovací APRS status přes RF?": "Send ONE APRS status test over RF?",
  "CHYBA: ": "ERROR: ",
  "OK5TVR · APRS zprávy": "OK5TVR · APRS messages",
  "APRS zprávy": "APRS messages",
  "Adresované zprávy přes": "Addressed messages via",
  ". Přenos probíhá přes rádio, nikoli přes APRS-IS → RF. Zprávy jsou veřejné a mohou je číst ostatní radioamatéři.": ". Messages travel over RF, not APRS-IS → RF. APRS messages are public and can be received by other radio amateurs.",
  "Moje značka": "My callsign",
  "Čeká na ACK": "Awaiting ACK",
  "Nová APRS zpráva": "New APRS message",
  "Cílová značka / SSID": "Destination callsign / SSID",
  "RF cesta": "RF path",
  "DIRECT – bez digipeateru": "DIRECT – no digipeater",
  "WIDE1-1 – místní fill-in DIGI": "WIDE1-1 – local fill-in digi",
  "WIDE2-1 – jeden regionální hop": "WIDE2-1 – one regional hop",
  "WIDE1-1,WIDE2-1 – dva hopy": "WIDE1-1,WIDE2-1 – two hops",
  "Vlastní cesta…": "Custom path…",
  "Vlastní RF cesta (max. 2 hopy)": "Custom RF path (max. 2 hops)",
  "Text zprávy": "Message text",
  "0 / 67 ASCII znaků": "0 / 67 ASCII characters",
  "Bez české diakritiky. Zpráva dostane identifikátor `{NNN}` a bude odeslána maximálně podle nastavení níže, dokud nepřijde ACK/REJ.": "Use ASCII without accented characters. The message gets an ID `{NNN}` and will be retried according to the settings until an ACK/REJ arrives.",
  "Odeslat přes RF": "Send over RF",
  "Nastavení APRS zpráv": "APRS message settings",
  "Výchozí cílová značka": "Default destination callsign",
  "Výchozí RF cesta": "Default RF path",
  "Čas prvního opakování (s)": "First retry delay (s)",
  "Maximální počet TX": "Maximum TX attempts",
  "Automaticky odesílat ACK pro zprávy přijaté na vlastní značku": "Automatically send ACK for messages addressed to my callsign",
  "Bez automatického ACK můžeš každou přijatou zprávu potvrdit ručně. Změna výchozí cesty nebo značky přeruší čekající zprávy.": "Without automatic ACK, each received message can be acknowledged manually. Changing the default path or callsign interrupts pending messages.",
  "Uložit nastavení zpráv": "Save message settings",
  "Historie zpráv": "Message history",
  "Načítám zprávy…": "Loading messages…",
  "Stav „Čeká ACK“ znamená, že byl rámec zapsán do USB TNC; skutečný RF přenos je nutné ověřit rádiem. „ACK přijato“ znamená protokolové potvrzení, nikoli přečtení člověkem.": "“Awaiting ACK” means the frame was passed to USB TNC; verify actual RF transmission separately. “ACK received” confirms protocol delivery, not that a person read the message.",
  "Ahoj, test APRS zpravy...": "Hello, APRS message test...",
  "např. OK1ABC-9": "e.g. OK1ABC-9",
  "WIDE1-1 (DIRECT = bez cesty)": "WIDE1-1 (DIRECT = no path)",
  "Čeká na USB": "Waiting for USB",
  "V USB frontě": "Queued for USB",
  "ACK přijato": "ACK received",
  "REJ – odmítnuto": "REJ – rejected",
  "Bez ACK": "No ACK",
  "Přerušeno": "Interrupted",
  "Zrušeno": "Cancelled",
  "Zatím nebyla přijata žádná adresovaná zpráva.": "No addressed messages received yet.",
  "Outbox je zatím prázdný.": "Outbox is empty.",
  "Od": "From",
  "Komu": "To",
  "Přijato": "Received",
  "ACK odesláno do TNC ×": "ACK sent to TNC ×",
  "Ruční ACK": "Manual ACK",
  "Odmítnout (REJ)": "Reject (REJ)",
  "Odpovědět": "Reply",
  "Zrušit opakování": "Cancel retries",
  "Znovu napsat": "Write again",
  "ID": "ID",
  "bez ID": "no ID",
  "cesta": "path",
  "opakování": "duplicates",
  "Připraveno. Odeslání přes RF vyžaduje potvrzení.": "Ready. RF transmission requires confirmation.",
  "Nelze načíst zprávy: ": "Unable to load messages: ",
  "Vyplň cílovou značku a text.": "Enter the destination callsign and message.",
  "Použij 1–67 znaků ASCII bez diakritiky a { nebo }.": "Use 1–67 printable ASCII characters without { or }.",
  "Odeslat JEDNO protokolové ACK na RF stanici ": "Send ONE protocol ACK over RF to station ",
  "Odeslat REJ přes RF? Protokolové odmítnutí zprávy.": "Send REJ over RF? This rejects the message at the protocol level.",
  "Zrušit budoucí opakování? Již zadaný USB paket nelze odvolat.": "Cancel future retries? A packet already queued to USB cannot be recalled.",
  "Zpráva #": "Message #",
  " zařazena do Outboxu pro ": " queued in Outbox for ",
  "Odeslat APRS zprávu z ": "Send APRS message from ",
  " na ": " to ",
  " přes ": " via ",
  "Opakování do ACK: max. ": "Retry until ACK: max. ",
  "Vysílání je veřejné.": "RF transmissions are public.",
  "vlastní značky": "own callsign",
  "Povol it": "Enable",
  "znaků": "characters",
  "Offline mapa: ": "Offline map: ",
  "TX zpráva: ": "TX message: ",
  "Povolit automatické RF vysílání ACK při každé příchozí zprávě s ID? Bude pokračovat i po restartu.": "Allow automatic RF ACK for every addressed message with an ID? It will continue after restart.",
  " TX zpráva: ": "TX message: "
};
Object.assign(english, {
  "OK5TVR · APRS objekty a RF majáky": "OK5TVR · APRS objects and RF beacons",
  "OK5TVR · diagnostika a provozní deník": "OK5TVR · diagnostics and operations journal",
  "Objekt uložen bez vysílání. Automatické opakování zastaveno.": "Object saved without transmission. Scheduled repetitions stopped.",
  "Objekt odebrán z konfigurace. Pro ukončení veřejného objektu je nutné nejprve odeslat KILL.": "Object removed from local settings. Send KILL first to remove a public object.",
  "Automatické opakování objektů spuštěno. Po restartu služby se samo nezapne.": "Scheduled object transmissions started. They will not restart automatically.",
  "Automatické vysílání APRS objektů zastaveno.": "Scheduled APRS object transmissions stopped.",
  "RF cesta uložena. Automatické opakování objektů zastaveno.": "RF path saved. Scheduled objects stopped.",
  "APRS rámec zařazen do USB KISS fronty. Skutečný RF přenos nelze z PC potvrdit.": "APRS frame queued for USB KISS. Actual RF transmission cannot be verified from the PC.",
  "Provozní deník vymazán.": "Operations journal cleared.",
  "Prahy diagnostiky uloženy; ostatní provozní funkce zůstávají beze změny.": "Monitoring thresholds saved; other operations remain unchanged.",
  "Záloha načtena; iGate, DIGI, ACK a plánované objekty jsou vypnuté. APRS-IS heslo a webové klíče se neimportují.": "Backup imported; iGate, DIGI, auto ACK and object scheduling are off. APRS-IS password and web keys are not imported.",
  "RF vysílání vyžaduje potvrzení.": "RF transmission requires confirmation.",
  "Nejdřív nastav vlastní GPS polohu.": "Configure your GPS position first.",
  "USB KISS TNC není připojeno.": "USB KISS TNC is not connected.",
  "Objekt/položka nebyla nalezena.": "Object/item not found.",
  "Objekt uložen bez vysílání": "Object saved without transmitting",
  "Nepodporovaný příkaz.": "Unsupported command.",
  "Zadej objekt": "Enter an object",
  "Zprávy": "Messages",
  "Mapa": "Map",

  "Zprávy": "Messages",
  "Mapa": "Map",

  "USB KISS odpojeno; probíhá opakované připojování.": "USB KISS disconnected; attempting to reconnect.",
  "Dlouho nebyl přijat žádný platný APRS rámec. Neznamená to jistou poruchu TNC.": "No valid APRS frame received for a long time. This does not prove TNC failure.",

  "OK5TVR · APRS objekty a vysílání": "OK5TVR · APRS objects and RF",
  "Vysílání objektů, položek, vlastní pozice a APRS statusu přes USB KISS. Každé ruční RF vysílání vyžaduje potvrzení.": "Transmit objects, items, your position and APRS status via USB KISS. Every manual RF TX needs confirmation.",
  "Objekty a RF": "Objects & RF",
  "Diagnostika a deník": "Diagnostics & journal",
  "Nový objekt / položka": "New object / item",
  "Název (1–9 znaků, velikost písmen se rozlišuje)": "Name (1–9 chars, case sensitive)",
  "Typ": "Type",
  "APRS objekt (s UTC časem)": "APRS object (UTC timestamp)",
  "APRS položka (bez času)": "APRS item (no timestamp)",
  "GPS zeměpisná šířka": "GPS latitude",
  "GPS zeměpisná délka": "GPS longitude",
  "Tabulka symbolu": "Symbol table",
  "/ – primární": "/ – primary",
  "\\ – alternativní": "\\ – alternate",
  "Symbol APRS (jeden ASCII znak)": "APRS symbol (one ASCII character)",
  "ASCII komentář (max. 43 znaků)": "ASCII comment (up to 43 chars)",
  "Interval při ručně zapnutém opakování (min)": "Interval when manually enabling repeats (min)",
  "Povolit plánované opakování tohoto objektu (nezapne se automaticky)": "Allow scheduled repeat for this object (never auto-starts)",
  "Uložit objekt bez TX": "Save object without TX",
  "Vyčistit formulář": "Clear form",
  "Uložené objekty": "Saved objects",
  "Výchozí RF cesta": "Default RF path",
  "Uložit RF cestu": "Save RF path",
  "Spustit opakování RF": "Start RF repeat",
  "Zastavit opakování": "Stop repeating",
  "DIRECT, WIDE1-1, WIDE2-1 nebo WIDE1-1,WIDE2-1. Automatické vysílání se po restartu služby ani výpadku USB samo neobnoví. KILL ukončí objekt v síti, ale ztrátu paketu nelze vyloučit.": "DIRECT, WIDE1-1, WIDE2-1 or WIDE1-1,WIDE2-1. Automatic TX never resumes after restart or USB loss. KILL marks the object as dead, but the packet may be lost.",
  "Název": "Name",
  "Symbol": "Symbol",
  "Opakování": "Repeat",
  "Akce": "Actions",
  "Další APRS RF funkce": "Other APRS RF features",
  "Text APRS statusu (max. 67 ASCII)": "APRS status text (max. 67 ASCII)",
  "Odeslat status (RF)": "Send status (RF)",
  "Vlastní GPS poloha se použije z nastavení iGate. Při vysílání se odešle jeden pozicový rámec, nikoliv objekt.": "Your GPS position comes from iGate settings. Transmits one position frame, not an object.",
  "Odeslat moji pozici (RF)": "Send my position (RF)",
  "Připraveno. Uložení objektu nic nevysílá.": "Ready. Saving an object does not transmit.",
  "Zápis do USB KISS není potvrzením skutečného odvysílání. Před automatickým provozem ověř připojenou anténu, obsazení kanálu a místní APRS pravidla.": "Writing to USB KISS is not proof of an on-air transmission. Check the antenna, channel and local APRS rules before automatic TX.",
  "Upravit": "Edit",
  "Vyslat LIVE": "Transmit LIVE",
  "Smazat": "Delete",
  "Zatím žádné uložené objekty.": "No saved objects yet.",
  "Připojeno": "Connected",
  "Odpojeno": "Disconnected",
  "Opakování zapnuto": "Repeat enabled",
  "Vyslat jediný APRS LIVE objekt přes RF?": "Transmit ONE live APRS object over RF?",
  "Vyslat ukončení APRS objektu na RF?": "Transmit APRS object KILL over RF?",
  "Odstranit jen místní konfiguraci? To nevysílá KILL.": "Delete only local settings? This does NOT send KILL.",
  "POZOR: Automatické periodické vysílání APRS objektů na RF. Máš povolený KISS TX a anténu?": "WARNING: periodic APRS object RF TX. Are KISS TX and the antenna ready?",
  "Vyslat jeden APRS status přes RF?": "Transmit one APRS status over RF?",
  "Vyslat jednu vlastní polohu přes RF?": "Transmit your position once over RF?",
  "OK5TVR · diagnostika a deník": "OK5TVR · diagnostics & journal",
  "Kontrola komunikace USB KISS, APRS-IS a DIGI; přehled RX, TX a odmítnutých rámců. Podrobné záznamy jsou dostupné pouze administrátorovi.": "USB KISS, APRS-IS and DIGI checks; RX, TX and rejected frames. Detailed journal requires admin access.",
  "Stav služby a hlášení": "Service status & alerts",
  "Poslední RF rámec UTC": "Last RF frame UTC",
  "Opětovná připojení USB": "USB reconnects",
  "Záznamů": "Log entries",
  "Bez příjmu": "No reception",
  "Připojený USB port potvrzuje pouze sériové spojení. Dlouhá pauza bez APRS paketů sama nedokazuje poruchu TNC ani radiostanice.": "An open USB port confirms only serial connectivity. No APRS traffic does not prove TNC or radio failure.",
  "Varování při tichu kanálu po": "Silence warning after",
  "minutách": "minutes",
  "Varování při výpadku USB po": "USB disconnect warning after",
  "sekundách": "seconds",
  "Uložit prahy hlídání": "Save alert thresholds",
  "Podrobný provozní deník": "Detailed operations journal",
  "Filtr": "Filter",
  "Všechny události": "All events",
  "Odmítnuté": "Rejected",
  "Systém": "System",
  "Aktualizovat": "Refresh",
  "Export deníku CSV": "Export journal CSV",
  "Vymazat deník": "Clear journal",
  "Směr": "Direction",
  "Subsystém": "Subsystem",
  "Zdroj": "Source",
  "Cíl": "Destination",
  "Cesta": "Path",
  "Popis": "Details",
  "Výsledek / důvod": "Outcome / reason",
  "Zatím žádné události.": "No events yet.",
  "Záloha a obnova konfigurace": "Configuration backup & restore",
  "Záloha obsahuje volací značky, GPS, cesty, uložené objekty a konfiguraci. Neobsahuje APRS-IS passcode, přístupové klíče ani historii zpráv. Po importu jsou automatické TX a iGate vypnuté.": "Backup includes callsigns, GPS, paths, stored objects and settings. It excludes APRS-IS passcode, access keys and message history. Automatic TX and iGate will be off after import.",
  "Stáhnout zálohu JSON": "Download JSON backup",
  "Importovat soubor JSON": "Import JSON file",
  "Obnovit konfiguraci": "Restore configuration",
  "„USB written“ znamená předání dat modemu, nikoliv potvrzení odvysílání VF signálu. Upozornění nejsou vzdálené push notifikace.": "“USB written” means bytes reached the modem, not confirmed RF transmission. Alerts are visible locally, not remote push notifications.",
  "Připraveno.": "Ready.",
  "Trvale vymazat provozní deník?": "Permanently clear the operations journal?",
  "Vyber soubor zálohy JSON.": "Select JSON backup file.",
  "Záloha je příliš velká.": "Backup is too large.",
  "POZOR: Obnovit nastavení? iGate, DIGI a automatické RF vysílání budou vypnuty.": "WARNING: Restore settings? iGate, DIGI and automatic RF TX will be disabled.",
  "USB KISS disconnected; retrying.": "USB KISS disconnected; retrying.",
  "No valid APRS packet for a long time; this does not prove TNC failure.": "No valid APRS packet for a long time; this does not prove TNC failure."
});

const own = Object.prototype.hasOwnProperty;
const STORAGE_KEY = "ok5tvr.aprs.ui.language";
let language = "cs";
try { const saved = localStorage.getItem(STORAGE_KEY); if (saved === "cs" || saved === "en") language = saved; } catch (_) {}
const watched = [];
function tr(value) {
  if (language !== "en") return value;
  const text = String(value);
  if (own.call(english, text)) return english[text];
  // Status prefixes only; never run on APRS message bodies or decoded packet data.
  for (const [cs, en] of [["Připojeno ", "Connected "], ["Odpojeno ", "Disconnected "],
                           ["Připojuji ", "Connecting "], ["Chyba: ", "Error: "]]) {
    if (text.startsWith(cs)) return en + text.slice(cs.length);
  }
  return text;
}
function capture() {
  const walker = document.createTreeWalker(document, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    if (!n.parentElement || n.parentElement.closest("script, style, [data-untranslated]")) continue;
    const raw = n.nodeValue, cs = raw.trim();
    if (!cs || !own.call(english, cs)) continue;
    watched.push({node:n, cs, before:raw.slice(0, raw.indexOf(cs)), after:raw.slice(raw.indexOf(cs) + cs.length)});
  }
  document.querySelectorAll("[placeholder], [title], [aria-label]").forEach(node => {
    if (node.closest("[data-untranslated]")) return;
    for (const name of ["placeholder", "title", "aria-label"]) {
      const cs = node.getAttribute(name);
      if (cs && own.call(english, cs)) watched.push({node, name, cs});
    }
  });
}
function apply(lang) {
  language = lang === "en" ? "en" : "cs";
  try { localStorage.setItem(STORAGE_KEY, language); } catch (_) {}
  document.documentElement.lang = language;
  for (const v of watched) {
    const value = language === "en" ? english[v.cs] : v.cs;
    if (v.name) v.node.setAttribute(v.name, value);
    else if (v.node.isConnected) v.node.nodeValue = v.before + value + v.after;
  }
  const choice = document.getElementById("ui-language-choice");
  if (choice) choice.value = language;
  window.dispatchEvent(new Event("ok5tvr:language"));
}
function install() {
  const container = document.querySelector("header") || document.querySelector("nav") || document.querySelector("main");
  if (!container || document.getElementById("ui-language-choice")) return;
  const label = document.createElement("label");
  label.className = "ui-language-selector";
  label.htmlFor = "ui-language-choice";
  label.style.cssText = "display:inline-flex;align-items:center;gap:7px;font:600 13px system-ui,sans-serif;white-space:nowrap;margin-left:auto;color:inherit";
  const caption = document.createElement("span");
  caption.textContent = "CZ / EN";
  const select = document.createElement("select");
  select.id = "ui-language-choice";
  select.setAttribute("aria-label", "Language / Jazyk");
  select.style.cssText = "width:auto;min-width:68px;margin:0;padding:6px;background:#24384f;color:#fff;border:1px solid #5c758e;border-radius:7px";
  [["cs", "CZ"], ["en", "EN"]].forEach(pair => {
    const opt = document.createElement("option");opt.value = pair[0];opt.textContent = pair[1];select.append(opt);
  });
  label.append(caption, select);
  if (container.tagName === 'MAIN') {
    const heading = container.querySelector('h1');
    if (heading) heading.insertAdjacentElement('afterend', label);
    else container.prepend(label);
  } else container.append(label);
  capture();
  select.addEventListener("change", () => apply(select.value));
  apply(language);
}
window.OK5TVRLocale = {tr, get language(){return language}, setLanguage:apply};
// Loaded just before each page's app script, after the static markup.
// Capture only its initial UI, never later user-supplied APRS message content.
if (document.body) install();
else document.addEventListener("DOMContentLoaded", install, {once:true});
})();
