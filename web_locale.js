/* OK5TVR APRS Monitor: Czech / English UI, no translation of packet contents. */
"use strict";
(() => {
const english = {
  "Poslední RF rámec": "Last RF frame",
  "Zatím žádný RF rámec": "No RF frame yet",
  "Další přijímané značky / SSID": "Additional receive callsigns / SSIDs",
  "Automaticky přijímáme značku iGate i základní značku bez SSID. Sem přidej pouze další vlastní SSID (oddělené čárkami). Změna zapíše příchozí zprávy do stejného Inboxu.": "The iGate callsign and its base callsign (without SSID) are always accepted. Enter other SSIDs you own, separated by commas. Messages arrive in the same Inbox.",
  "Diagnostika příjmu zpráv": "Message reception diagnostics",
  "Zobrazují se také APRS zprávy pro jiné adresáty, které TNC skutečně přijalo, ale Inbox je správně ignoruje. Pokud zde zprávy nejsou a v mapě přibývají pozice, otestuj zprávu cílenou na některou z přijímaných značek.": "Also shows APRS messages heard on RF for other recipients; these are intentionally excluded from Inbox. If this stays empty while the map receives positions, send a test message to one of your accepted callsigns.",
  "Přijímáme pro:": "Receiving for:",
  "Jiný adresát": "Other addressee",
  "Chybný formát": "Invalid format",
  "Vlastní rámec": "Self-originated frame",
  "Dosud nebyla přijata žádná APRS zpráva.": "No APRS message has been heard yet.",
  "Neplatný formát APRS zprávy / bulletin": "Invalid APRS message format / bulletin",
  "Zpráva jiné stanici": "Message addressed to another station",
  "Neplatná zdrojová značka": "Invalid source callsign",
  "Přijato do Inboxu": "Received in Inbox",
  "Přijato do Inboxu (duplicita)": "Received in Inbox (duplicate)",
  "ACK/REJ bez čekající zprávy": "ACK/REJ not matched to a pending message",
  "Potvrzeno v Outboxu": "Acknowledged in Outbox",

  "Mapa / Map": "Map / Mapa",
  "APRS objekty": "APRS objects",
  "Diagnostika": "Diagnostics",
  "Pro zprávy a objekty spusť plnou webovou službu; klasický monitor poskytuje jen mapu.": "Start the full web service for messages and objects; the classic monitor provides a read-only map.",
  "Toto je pouze mapa klasického monitoru. Pro zprávy a objekty ukonči monitor a spusť spustit_sluzbu_windows.bat.": "This is the classic monitor map only. Close the monitor and run spustit_sluzbu_windows.bat for messages and objects.",
  "Vlož administrátorský odkaz nebo klíč z příkazu zobrazit_odkazy_windows.bat:": "Paste the admin URL or key printed by zobrazit_odkazy_windows.bat:",
  "Administrátorský klíč nebyl zadán.": "No admin key provided.",
  "Neplatný formát administrátorského klíče.": "Invalid admin key format.",
  "Administrátorský klíč není platný.": "The admin key is invalid.",
  "Nepodařilo se ověřit stav webové služby.": "Could not check the web service status.",
  "Nelze otevřít administrátorskou stránku: ": "Cannot open admin page: ",

  "Statistiky za posledních 15 minut / Last 15 minutes": "Last 15 minutes / Statistiky za posledních 15 minut",
  "Vlastní APRS-IS majáky": "Own APRS-IS beacons",
  "APRS iGate – tabulka ikon / Symbol table": "APRS iGate – symbol table / Tabulka ikon",
  "Ikona iGate / iGate symbol": "iGate icon / Ikona iGate",
  "APRS DIGI – tabulka ikon / Symbol table": "APRS DIGI – symbol table / Tabulka ikon",
  "Ikona DIGI / DIGI symbol": "DIGI icon / Ikona DIGI",
  "Poziční maják DIGI / DIGI position beacon (only while DIGI is active)": "DIGI position beacon (only while DIGI is active)",
  "Kam vysílat maják DIGI / DIGI beacon destination": "DIGI beacon destination",
  "RF cesta majáku / DIGI beacon RF path": "DIGI beacon RF path",
  "POZOR: Automatický RF poziční maják DIGI po zapnutí DIGI. Povolit?": "WARNING: Enable automatic DIGI RF position beacon when DIGI starts?",
  "Interval majáku DIGI / DIGI beacon interval (min)": "DIGI beacon interval (min) / Interval majáku DIGI",
  "Komentář DIGI / DIGI comment (ASCII)": "DIGI comment (ASCII) / Komentář DIGI",
  "APRS-IS telemetrie iGate / iGate telemetry (T#)": "APRS-IS iGate telemetry (T#)",
  "Telemetrie DIGI / DIGI telemetry (only while DIGI active)": "DIGI telemetry (only while DIGI is active)",
  "Kam odeslat DIGI telemetrii / DIGI telemetry transport": "DIGI telemetry transport",
  "RF cesta pro telemetrii / RF telemetry path": "RF telemetry path",
  "POZOR: Automatické RF vysílání DIGI telemetrie po zapnutí DIGI. Pokračovat?": "WARNING: Enabling DIGI RF telemetry allows automatic RF transmissions while DIGI runs. Continue?",
  "APRS-IS nebo volitelně RF telemetrie DIGI (odstup 12 s/rámec). Standard T#, PARM, UNIT, EQNS, BITS. Kanály: RX/15 min, TX/15 min, průměr km, unikátní stanice, předané do APRS-IS (iGate) nebo opakované (DIGI). Hodnoty nad 255 jsou v APRS omezeny; přesná čísla zůstávají ve webu. Ve výchozím stavu vypnuto.": "APRS-IS or optional DIGI RF telemetry (12 s/frame pacing). Standard T#, PARM, UNIT, EQNS, BITS. Channels: RX/15 min, TX/15 min, average km, unique stations and forwarded (iGate) or repeated (DIGI) packets. Analog values are capped at 255; exact values remain available on the web. Telemetry defaults to OFF.",
  "Telemetrie iGate / DIGI": "iGate / DIGI telemetry",
  "Interval reportu / Report interval (minuty)": "Report interval (minutes)",
  "Všechny hodnoty jsou za POSLEDNÍCH 15 minut; délka okna zůstává stejná i při méně častém reportu.": "All values represent the LAST 15 minutes, even if reports are sent less frequently.",
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
