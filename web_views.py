"""One authenticated page shell and navigation for every station workspace."""
import re

SETTINGS_ROUTES = (
    ('/settings', 'CALL / SSID / TNC', 'CALL / SSID / TNC'),
    ('/settings/aprs', 'APRS · iGate / DIGI / GPS', 'APRS · iGate / DIGI / GPS'),
    ('/settings/objects', 'APRS objekty', 'APRS objects'),
    ('/settings/messages', 'APRS zprávy', 'APRS messages'),
    ('/settings/advanced?tab=rx', 'USB / displej', 'USB / display'),
    ('/settings/advanced?tab=tnc', 'TNC / síť / archiv', 'TNC / network / archive'),
    ('/settings/advanced?tab=telemetry', 'Telemetrie', 'Telemetry'),
    ('/settings/advanced?tab=isrf', 'IS → RF', 'IS → RF'),
    ('/settings/advanced?tab=alerts', 'Upozornění / MQTT', 'Alerts / MQTT'),
    ('/settings/advanced?tab=chat2', 'Blokované stanice', 'Blocked stations'),
    ('/settings/bbs', 'BBS server', 'BBS server'),
    ('/settings/operations', 'Záloha / obnova', 'Backup / restore'),
)
APRS_ROUTES = (
    ('/aprs#home', 'Přehled', 'Overview'),
    ('/aprs#rx', 'Příjem / TX', 'Receive / TX'),
    ('/map', 'Živá mapa', 'Live map'),
    ('/aprs#heard', 'Mapa doslechu', 'RF heard map'),
    ('/messages', 'Zprávy', 'Messages'),
    ('/aprs#chat2', 'Konverzace / bulletiny', 'Conversations / bulletins'),
    ('/objects', 'Objekty', 'Objects'),
    ('/aprs#telemetry', 'Telemetrie / statistiky', 'Telemetry / statistics'),
    ('/operations', 'Diagnostika / deník', 'Diagnostics / log'),
    ('/aprs#weather', 'Počasí', 'Weather'),
)
BBS_ROUTES = (
    ('/bbs#bbs-status', 'Stav serveru / spojení', 'Server / connection status'),
    ('/bbs#bbs-client', 'BBS klient', 'BBS client'),
    ('/bbs#bbs-mail', 'Poštovní schránka', 'Mailbox'),
    ('/bbs#compose-section', 'Nová zpráva', 'New message'),
)


def _link(route, cs, en):
    return f'<a data-route="{route}" href="{route}" data-cs="{cs}" data-en="{en}">{cs}</a>'


def full_page(source, role='aprs', settings=False):
    """Wrap existing forms without changing their IDs or their protocol handlers."""
    header='''<a href="#station-content" class="skip-link" data-cs="Přeskočit na obsah" data-en="Skip to content">Přeskočit na obsah</a>
<header id="global-navigation"><button id="navigation-toggle" type="button" aria-controls="station-sidebar" aria-expanded="false" data-cs="Menu" data-en="Menu">Menu</button>
<div class="global-brand"><b id="global-call">—</b> · Radio Station</div>
<div class="global-status"><span id="global-tnc">TNC: —</span><span id="global-mode">—</span><span id="global-clock">—</span><span id="global-ip">IP: —</span></div>
<nav class="global-links" aria-label="Station">'''
    for route,cs,en in (('/app','Úvod','Home'),('/aprs','APRS','APRS'),('/bbs','BBS','BBS'),('/settings','Nastavení','Settings')):
        header+=_link(route,cs,en)
    header+='</nav><button id="global-logout" type="button" data-cs="Odhlásit" data-en="Log out">Odhlásit</button></header>'
    sidebar='<aside id="station-sidebar"><nav aria-label="Station navigation">'+_link('/app','Úvod stanice','Station home')
    for group,cs,en,routes,opened in (
            ('aprs','APRS','APRS',APRS_ROUTES,role.startswith('aprs') or role=='home'),
            ('bbs','BBS','BBS',BBS_ROUTES,role=='bbs'),
            ('settings','Nastavení','Settings',SETTINGS_ROUTES,settings)):
        sidebar+=f'<details class="navigation-group" data-nav-group="{group}"'+(' open' if opened else '')+'>'
        sidebar+=f'<summary data-cs="{cs}" data-en="{en}">{cs}</summary>'
        sidebar+=''.join(_link(*entry) for entry in routes)+'</details>'
    sidebar+='</nav></aside>'
    mode=''
    if settings:
        mode='''<div id="settings-navigation"><div class="settings-mode"><b data-cs="Provozní režim:" data-en="Operating mode:">Provozní režim:</b><span id="settings-mode-state">—</span><button type="button" data-mode="aprs">APRS ON</button><button type="button" data-mode="bbs">BBS ON</button><button type="button" data-mode="off" data-cs="Vypnout" data-en="Stop">Vypnout</button><span id="mode-result" role="status"></span></div></div>'''
    if role=='aprs-map':
        source=source.replace('<main>','<main><h1 data-cs="Živá mapa" data-en="Live map">Živá mapa</h1>',1)
    if role=='settings-operations':
        source=re.sub(r'<h1\b[^>]*>.*?</h1>','<h1 data-cs="Záloha / obnova" data-en="Backup / restore">Záloha / obnova</h1>',source,count=1,flags=re.S)
    source=re.sub(r'<a\b[^>]*class="skip-link"[^>]*>.*?</a>','',source,flags=re.S)
    # Legacy BBS template has no main landmark; give it the same content container.
    if not re.search(r'<main\b',source,re.I):
        source=re.sub(r'(<body\b[^>]*>)',r'\1<main>',source,count=1,flags=re.I)
        source=source.replace('<script','</main><script',1)
    source=re.sub(r'<body\b([^>]*)>',lambda m:'<body'+m[1]+f' data-view-role="{role}" data-page-kind="'+('settings' if settings else 'operation')+'" data-shell="1">'+header+sidebar+'<div id="station-content" tabindex="-1">'+mode,source,count=1,flags=re.I)
    source=source.replace('</body>','</div><script src="/assets/web_shell.js?v=29"></script></body>')
    # Load the common theme after page-specific legacy styles, including the launcher.
    source=re.sub(r'<link\b[^>]*href="/assets/web_theme\.css[^\"]*"[^>]*>','',source,flags=re.I)
    source=source.replace('</head>','<link rel="stylesheet" href="/assets/web_theme.css?v=29"></head>')
    return source
