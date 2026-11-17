"""Compose full-page navigation without copying controls into nested windows."""
import re

SETTINGS_ROUTES = (
    ('/settings', 'CALL / SSID / TNC', 'CALL / SSID / TNC'),
    ('/settings/aprs', 'APRS · iGate / DIGI / GPS', 'APRS · iGate / DIGI / GPS'),
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


def full_page(source, role='aprs', settings=False):
    """Add a common shell; existing page scripts keep their own form handlers."""
    nav='''<div id="global-navigation"><div class="global-brand"><b id="global-call">—</b> · Radio Station</div>
<div class="global-status"><span id="global-tnc">TNC: —</span><span id="global-clock">—</span><span id="global-ip">IP: —</span></div>
<nav class="global-links" aria-label="Station"><a data-route="/app" href="/app" data-cs="Úvod" data-en="Home">Úvod</a><a data-route="/aprs" href="/aprs">APRS</a><a data-route="/bbs" href="/bbs">BBS</a><a data-route="/settings" href="/settings" data-cs="Nastavení" data-en="Settings">Nastavení</a></nav></div>'''
    if settings:
        nav+='''<div id="settings-navigation"><div class="settings-mode"><b data-cs="Provozní režim:" data-en="Operating mode:">Provozní režim:</b><span id="settings-mode-state">—</span><button type="button" data-mode="aprs">APRS ON</button><button type="button" data-mode="bbs">BBS ON</button><button type="button" data-mode="off" data-cs="Vypnout" data-en="Stop">Vypnout</button><span id="mode-result" role="status"></span></div><nav aria-label="Settings">'''
        for route,cs,en in SETTINGS_ROUTES:
            nav+=f'<a data-route="{route}" href="{route}" data-cs="{cs}" data-en="{en}">{cs}</a>'
        nav+='</nav></div>'
    source=re.sub(r'<body\b([^>]*)>',lambda m:'<body'+m[1]+f' data-view-role="{role}" data-page-kind="'+('settings' if settings else 'operation')+'" data-shell="1">'+nav,source,count=1,flags=re.I)
    source=source.replace('</body>', '<script src="/assets/web_shell.js?v=27"></script></body>')
    return source
