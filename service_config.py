"""Validated configuration and private credentials for headless APRS service.

No network, RF, or state-changing action is enabled on a fresh installation.
Sensitive credentials are stored in a separate 0600 file (never in web API output).
"""
from __future__ import annotations
import copy
import json
import logging
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import secrets
import tempfile

from aprs_features import CALL_RE
from aprs_is_to_rf import validate_filter_config
from aprs_messages import normalize_call, normalize_path
from aprs_digi import DigiConfig
from aprs_station import decimal_coordinate, aprsis_position
from aprs_telemetry import symbol_code

DEFAULT_PATH = Path.home() / '.config' / 'ok5tvr-aprs' / 'config.json'
DEFAULT_CONFIG = {
    'serial': {'port': 'auto', 'baud': 115200, 'retry_seconds': 4},
    'tnc': {'transport':'serial', 'tcp_host':'127.0.0.1', 'tcp_port':8001,
            'kiss_server_enabled':False, 'kiss_server_host':'127.0.0.1',
            'kiss_server_port':8001, 'kiss_server_tx':False},
    'tx_scheduler': {'min_gap_s':2.0, 'max_per_minute':12, 'max_pending':12},
    'secondary_tncs': {'devices': []},  # up to 2 independent read-only KISS receivers
    'alerts': {'enabled':True, 'offline_seconds':300, 'no_rf_minutes':30,
               'watch_calls':[], 'weather_temp_high':None,
               'weather_pressure_low':None,
               'mqtt_enabled':False, 'mqtt_host':'127.0.0.1',
               'mqtt_port':1883, 'mqtt_topic':'ok5tvr/aprs/alerts'},
    'archive': {'retention_days':30, 'max_rows':100000},
    'is_to_rf': {'calls': [], 'objects': [], 'types': ['message','position'],
                 'rf_path': '', 'heard_minutes': 30, 'max_per_minute': 2,
                 'max_per_hour': 12, 'min_gap_seconds': 15,
                 'duplicate_seconds': 120},
    'web': {'port': 8765, 'lan': False},
    'display': {'enabled': False},  # optional HDMI desktop panel; no RF side effects
    'igate': {'call': 'OK5TVR-10', 'host': 'rotate.aprs2.net', 'port': 14580,
              'autostart': False, 'symbol_table': '\\', 'symbol': '&',
              'overlay': 'R', 'telemetry_enabled': False},
    'digi': {'call': 'OK5TVR-3', 'mode': 'fill', 'trace': False,
             'delay_s': 4.0, 'max_per_min': 6, 'min_gap_s': 3.0,
             'autostart': False, 'symbol_table': '\\', 'symbol': '#',
             'overlay': '1', 'beacon_enabled': False, 'beacon_interval': 30,
             'beacon_comment': 'OK5TVR APRS DIGI',
             'beacon_transport': 'is', 'beacon_rf_path': '', 'telemetry_enabled': False,
             'telemetry_transport': 'is', 'telemetry_rf_path': ''},
    'messages': {'target': '', 'path': 'WIDE1-1', 'receive_aliases': [], 'auto_ack': False,
                 'retry_seconds': 45, 'max_attempts': 3,
                 'blocked_senders':[]},
    'telemetry': {'interval_minutes': 15},
    'position': {'latitude': None, 'longitude': None,
                 'comment': 'OK5TVR RX iGate', 'beacon_enabled': False,
                 'beacon_interval': 30},
}


def _atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix='.ok5tvr-', suffix='.tmp')
    try:
        if os.name != 'nt':
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        if os.name != 'nt':
            os.chmod(path, 0o600)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _merge_known(base, update):
    if not isinstance(update, dict):
        raise ValueError('Konfigurace musí být objekt JSON.')
    for section, fields in update.items():
        if section not in base or not isinstance(fields, dict):
            raise ValueError(f'Nepodporovaná sekce: {section}')
        for field, value in fields.items():
            if field not in base[section]:
                raise ValueError(f'Nepodporované nastavení: {section}.{field}')
            base[section][field] = value
    return base


def _bool(value, name):
    if type(value) is not bool:
        raise ValueError(f'{name}: očekávám true/false.')
    return value


def _int(value, name, lo, hi):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{name}: celé číslo {lo}–{hi}.')
    return value


def validate_config(candidate):
    """Return normalized copy; rejects risky or invalid values and booleans-as-int."""
    v = _merge_known(copy.deepcopy(DEFAULT_CONFIG), candidate)
    s = v['serial']
    if not isinstance(s['port'], str) or not 1 <= len(s['port']) <= 128 or any(c in s['port'] for c in '\n\r\x00'):
        raise ValueError('Neplatný název sériového portu.')
    s['baud'] = _int(s['baud'], 'Rychlost USB', 1200, 2000000)
    s['retry_seconds'] = _int(s['retry_seconds'], 'Opakování USB', 2, 60)
    t = v['tnc']
    if t['transport'] not in ('serial','tcp'):
        raise ValueError('TNC transport must be serial or tcp')
    for key in ('tcp_host','kiss_server_host'):
        if not isinstance(t[key],str) or len(t[key]) > 253 or not re.fullmatch(r'[A-Za-z0-9.:-]+', t[key]):
            raise ValueError('Invalid TCP KISS hostname/address')
    if t['kiss_server_host'] not in ('127.0.0.1','0.0.0.0'):
        raise ValueError('TCP KISS server bind address must be loopback or all interfaces')
    t['tcp_port'] = _int(t['tcp_port'], 'TCP KISS client port', 1,65535)
    t['kiss_server_port'] = _int(t['kiss_server_port'], 'TCP KISS server port', 1024,65535)
    t['kiss_server_enabled'] = _bool(t['kiss_server_enabled'], 'TCP KISS server')
    t['kiss_server_tx'] = _bool(t['kiss_server_tx'], 'TCP KISS server TX')
    if t['kiss_server_tx'] and (t['kiss_server_host'] != '127.0.0.1' or
                               not t['kiss_server_enabled']):
        raise ValueError('TCP KISS TX requires enabled loopback-only server')
    if t['transport']=='tcp' and t['kiss_server_enabled'] and t['tcp_host'] in ('127.0.0.1','localhost') and t['tcp_port']==t['kiss_server_port']:
        raise ValueError('TCP KISS client cannot connect to its own server')
    sched = v['tx_scheduler']
    if type(sched['min_gap_s']) not in (int,float) or not 0 <= sched['min_gap_s'] <= 15:
        raise ValueError('TX scheduler interval must be 0-15 seconds')
    sched['min_gap_s'] = float(sched['min_gap_s'])
    sched['max_per_minute'] = _int(sched['max_per_minute'],'TX scheduler max/min',1,60)
    sched['max_pending'] = _int(sched['max_pending'],'TX scheduler RAM queue',1,32)
    other = v['secondary_tncs']['devices']
    if not isinstance(other,list) or len(other)>2:
        raise ValueError('Secondary KISS: maximum 2 independent receivers')
    used_ids=set()
    used_endpoints=set()
    normalized=[]
    for raw in other:
        if not isinstance(raw,dict) or set(raw)-{'id','enabled','transport','host','port','serial_port','baud'}:
            raise ValueError('Invalid secondary TNC structure')
        item=dict(id=raw.get('id'),enabled=raw.get('enabled',False),
                  transport=raw.get('transport','tcp'),host=raw.get('host','127.0.0.1'),
                  port=raw.get('port',8002),serial_port=raw.get('serial_port',''),
                  baud=raw.get('baud',115200))
        if type(item['id']) is not str or not re.fullmatch(r'[a-z][a-z0-9_-]{1,15}',item['id']):
            raise ValueError('Secondary TNC id: 2-16 lowercase letters/digits')
        if item['id'] in used_ids:
            raise ValueError('Duplicate secondary TNC id')
        used_ids.add(item['id'])
        item['enabled'] = _bool(item['enabled'],'Secondary TNC enabled')
        if item['transport'] not in ('serial','tcp'):
            raise ValueError('Secondary TNC must be serial or tcp')
        if not isinstance(item['host'],str) or not re.fullmatch(r'[A-Za-z0-9.:-]{1,253}',item['host']):
            raise ValueError('Invalid secondary TCP host')
        item['port'] = _int(item['port'],'Secondary TCP port',1,65535)
        if not isinstance(item['serial_port'],str) or not 0 <= len(item['serial_port']) <= 128 or any(c in item['serial_port'] for c in '\r\n\x00'):
            raise ValueError('Invalid secondary serial port')
        item['baud'] = _int(item['baud'],'Secondary serial baud',1200,2000000)
        if item['enabled']:
            if item['transport']=='serial' and not item['serial_port']:
                raise ValueError('Secondary serial KISS requires an exact port')
            endpoint=(item['transport'],item['serial_port'] if item['transport']=='serial' else (item['host'],item['port']))
            if endpoint in used_endpoints:
                raise ValueError('Duplicate secondary TNC endpoint')
            if item['transport']=='serial' and item['serial_port']==s['port']:
                raise ValueError('Secondary cannot open primary COM/USB port')
            if item['transport']=='tcp' and t['transport']=='tcp' and item['host']==t['tcp_host'] and item['port']==t['tcp_port']:
                raise ValueError('Secondary cannot open primary TCP KISS port')
            if item['transport']=='tcp' and t['kiss_server_enabled'] and item['host'] in ('127.0.0.1','localhost') and item['port']==t['kiss_server_port']:
                raise ValueError('Secondary TCP KISS cannot connect to own server')
            used_endpoints.add(endpoint)
        normalized.append(item)
    v['secondary_tncs']['devices']=normalized
    alerts=v['alerts']
    alerts['enabled']=_bool(alerts['enabled'],'Monitoring alerts')
    alerts['mqtt_enabled']=_bool(alerts['mqtt_enabled'],'MQTT alerts')
    if not isinstance(alerts['mqtt_host'],str) or not re.fullmatch(r'[A-Za-z0-9.:-]{1,253}',alerts['mqtt_host']):
        raise ValueError('MQTT hostname invalid')
    alerts['mqtt_port']=_int(alerts['mqtt_port'],'MQTT port',1,65535)
    if not isinstance(alerts['mqtt_topic'],str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+){0,7}',alerts['mqtt_topic']) or len(alerts['mqtt_topic'])>80:
        raise ValueError('MQTT topic invalid')
    alerts['offline_seconds']=_int(alerts['offline_seconds'],'TNC offline seconds',30,3600)
    alerts['no_rf_minutes']=_int(alerts['no_rf_minutes'],'No RF minutes',5,240)
    watchers=alerts['watch_calls']
    if not isinstance(watchers,list) or len(watchers)>25:
        raise ValueError('Watch list: maximum 25 calls')
    alerts['watch_calls']=sorted(set(normalize_call(x) for x in watchers))
    for name,low,high in (('weather_temp_high',-50,70),
                          ('weather_pressure_low',800,1100)):
        value=alerts[name]
        if value is not None:
            if type(value) not in (int,float) or not low<=value<=high:
                raise ValueError('Weather alert threshold outside range')
            alerts[name]=float(value)
    archive = v['archive']
    archive['retention_days'] = _int(archive['retention_days'], 'Archive retention days',1,365)
    archive['max_rows'] = _int(archive['max_rows'], 'Archive maximum rows',1000,1000000)
    w = v['web']
    w['port'] = _int(w['port'], 'Web port', 1024, 65535)
    w['lan'] = _bool(w['lan'], 'Přístup z LAN')
    v['display']['enabled'] = _bool(v['display']['enabled'], 'HDMI panel')
    i = v['igate']
    if not isinstance(i['call'], str) or not CALL_RE.fullmatch(i['call'].upper()):
        raise ValueError('Zadej platnou AX.25 značku iGate, např. OK5TVR-10.')
    i['call'] = i['call'].upper()
    if not isinstance(i['host'], str) or not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', i['host']) or i['host'].startswith(('-', '.')):
        raise ValueError('Neplatný APRS-IS server.')
    i['port'] = _int(i['port'], 'APRS-IS port', 1, 65535)
    i['autostart'] = _bool(i['autostart'], 'Automatický iGate')
    i['telemetry_enabled'] = _bool(i['telemetry_enabled'], 'iGate APRS-IS telemetry')
    v['is_to_rf'] = validate_filter_config(v['is_to_rf'])
    symbol_code(i['symbol_table'], i['symbol'], i['overlay'])
    d = v['digi']
    if not isinstance(d['call'], str):
        raise ValueError('DIGI značka musí být text.')
    d['call'] = d['call'].upper()
    d['trace'] = _bool(d['trace'], 'TRACE')
    d['telemetry_enabled'] = _bool(d['telemetry_enabled'], 'DIGI telemetry')
    if d['telemetry_transport'] not in ('is','rf'):
        raise ValueError('DIGI telemetry transport must be APRS-IS or RF.')
    d['telemetry_rf_path'] = normalize_path(d['telemetry_rf_path'])
    d['beacon_enabled'] = _bool(d['beacon_enabled'], 'DIGI position beacon')
    if d['beacon_transport'] not in ('is', 'rf'):
        raise ValueError('DIGI beacon transport must be APRS-IS or RF.')
    d['beacon_rf_path'] = normalize_path(d['beacon_rf_path'])
    d['beacon_interval'] = _int(d['beacon_interval'], 'DIGI beacon interval', 30, 120)
    if (not isinstance(d['beacon_comment'], str) or len(d['beacon_comment']) > 43
            or any(ord(c) < 32 or ord(c) > 126 for c in d['beacon_comment'])):
        raise ValueError('DIGI beacon comment: up to 43 printable ASCII chars.')
    symbol_code(d['symbol_table'], d['symbol'], d['overlay'])
    d['autostart'] = _bool(d['autostart'], 'Automatický DIGI')
    d['delay_s'] = float(d['delay_s']) if type(d['delay_s']) in (int, float) else d['delay_s']
    d['min_gap_s'] = float(d['min_gap_s']) if type(d['min_gap_s']) in (int, float) else d['min_gap_s']
    d['max_per_min'] = _int(d['max_per_min'], 'DIGI TX/min', 1, 12)
    DigiConfig(d['call'], d['mode'], d['trace'], d['delay_s'],
               d['max_per_min'], d['min_gap_s']).validate()
    if ((d['telemetry_enabled'] and d['telemetry_transport'] == 'is') or
            (d['beacon_enabled'] and d['beacon_transport'] == 'is')) and i['call'].split('-')[0] != d['call'].split('-')[0]:
        raise ValueError('DIGI APRS-IS beacon/telemetry requires same base callsign as the APRS-IS login.')
    if d['telemetry_enabled'] and d['telemetry_transport'] == 'is' and i['telemetry_enabled'] and d['call'] == i['call']:
        raise ValueError('iGate and DIGI telemetry cannot share the same source callsign.')
    v['telemetry']['interval_minutes'] = _int(v['telemetry']['interval_minutes'], 'Telemetry interval', 15, 60)
    if v['telemetry']['interval_minutes'] not in (15, 30, 60):
        raise ValueError('Telemetry interval must be 15, 30 or 60 minutes.')
    m = v['messages']
    if not isinstance(m['target'], str) or len(m['target']) > 9:
        raise ValueError('Neplatná výchozí cílová značka.')
    m['target'] = normalize_call(m['target']) if m['target'].strip() else ''
    if m['target'] == i['call']:
        raise ValueError('Cílová značka zpráv se nesmí rovnat vlastní značce.')
    m['path'] = normalize_path(m['path'])
    aliases = m['receive_aliases']
    if not isinstance(aliases, list) or len(aliases) > 6:
        raise ValueError('Zprávy: nejvýše 6 dalších přijímaných SSID.')
    aliases = [normalize_call(value) for value in aliases]
    if any(alias.split('-')[0] != i['call'].split('-')[0] for alias in aliases):
        raise ValueError('Přijímané značky musejí patřit ke stejné základní značce jako iGate.')
    m['receive_aliases'] = list(dict.fromkeys(aliases))
    m['auto_ack'] = _bool(m['auto_ack'], 'Automatické potvrzování APRS zpráv (RF TX)')
    m['retry_seconds'] = _int(m['retry_seconds'], 'Opakování zprávy (s)', 30, 180)
    m['max_attempts'] = _int(m['max_attempts'], 'Počet odeslání', 1, 5)
    blocked=m['blocked_senders']
    if not isinstance(blocked,list) or len(blocked)>24:
        raise ValueError('Messaging blocked senders: maximum 24')
    m['blocked_senders']=sorted(set(normalize_call(x) for x in blocked))
    p = v['position']
    p['beacon_enabled'] = _bool(p['beacon_enabled'], 'Pozicni majak')
    p['beacon_interval'] = _int(p['beacon_interval'], 'Interval majaku', 30, 120)
    if p['latitude'] is None and p['longitude'] is None:
        if p['beacon_enabled']:
            raise ValueError('Nejprve vyplň polohu před zapnutím APRS-IS majáku.')
    elif p['latitude'] is None or p['longitude'] is None:
        raise ValueError('Zadej obě GPS souřadnice, nebo žádnou.')
    else:
        p['latitude'] = decimal_coordinate(p['latitude'], True)
        p['longitude'] = decimal_coordinate(p['longitude'], False)
    if not isinstance(p['comment'], str) or len(p['comment']) > 43 or any(ord(c) < 32 or ord(c) > 126 for c in p['comment']):
        raise ValueError('Komentář musí mít maximálně 43 tisknutelných ASCII znaků.')
    if p['latitude'] is not None:
        aprsis_position(i['call'], p['latitude'], p['longitude'], p['comment'],
                        symbol_code(i['symbol_table'], i['symbol'], i['overlay']))
        if d['beacon_enabled']:
            aprsis_position(d['call'], p['latitude'], p['longitude'], d['beacon_comment'],
                            symbol_code(d['symbol_table'], d['symbol'], d['overlay']))
    elif d['beacon_enabled']:
        raise ValueError('Configure own GPS before enabling a DIGI position beacon.')
    return v



# v1.6 used these sections; v1.9 no longer supports their schema.
# Never silently drop arbitrary unknown configuration fields.
_LEGACY_SECTIONS = frozenset(('health', 'objects'))


def _upgrade_v16_config(raw, config_path: Path):
    """Backup and convert known v1.6-only settings, disabling automatic TX.

    Unrecognized non-legacy values still fail strict validation.
    Legacy APRS objects remain recoverable in a private backup because v1.9
    uses a different object workflow and cannot import the old scheduler safely.
    """
    if not isinstance(raw, dict):
        raise ValueError('Konfigurace musi byt objekt JSON.')
    legacy = sorted(_LEGACY_SECTIONS.intersection(raw))
    if not legacy:
        return validate_config(raw)

    compatible = copy.deepcopy({k: v for k, v in raw.items() if k not in _LEGACY_SECTIONS})
    # Disable automatic actions before validating the migrated state, so a legacy
    # configuration cannot reactivate RF transmissions and does not require old
    # position-beacon dependencies merely to complete a safe migration.
    for section, key in (('igate', 'autostart'), ('digi', 'autostart'),
                         ('messages', 'auto_ack'), ('digi', 'beacon_enabled'),
                         ('digi', 'telemetry_enabled'), ('igate', 'telemetry_enabled'),
                         ('position', 'beacon_enabled')):
        if isinstance(compatible.get(section), dict) and key in compatible[section]:
            compatible[section][key] = False
    upgraded = validate_config(compatible)  # reject other unsupported values

    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    suffix = secrets.token_hex(4)
    backup = config_path.with_name(f'{config_path.stem}.before-v19-{stamp}-{suffix}.json')
    _atomic_json(backup, raw)
    _atomic_json(config_path, upgraded)
    logging.getLogger('ok5tvr.aprs').warning(
        'Konfigurace v1.6 prevedena do v1.9; nekompatibilni sekce %s zalohovany do %s. '
        'Automaticke iGate/DIGI/ACK a majaky jsou vypnute; '
        'stare APRS objekty zustaly pouze v zaloze.',
        ', '.join(legacy), backup)
    return upgraded


class ServiceConfig:
    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path).expanduser().resolve()
        self.secret_path = self.path.with_name('secrets.json')
        self.data = None
        self.secrets = None

    def load_or_create(self):
        if self.path.exists():
            self.data = _upgrade_v16_config(json.loads(self.path.read_text(encoding='utf-8')), self.path)
        else:
            self.data = validate_config({})
            _atomic_json(self.path, self.data)
        if self.secret_path.exists():
            secret_data = json.loads(self.secret_path.read_text(encoding='utf-8'))
            if not isinstance(secret_data, dict):
                raise ValueError('Neplatný soubor credentials.')
        else:
            secret_data = {}
        self.secrets = {
            'web_username': secret_data.get('web_username', 'ok5tvr'),
            'viewer_token': secret_data.get('viewer_token') or secrets.token_urlsafe(32),
            'admin_token': secret_data.get('admin_token') or secrets.token_urlsafe(32),
            'igate_passcode': str(secret_data.get('igate_passcode', '')),
        }
        username = self.secrets['web_username']
        if not isinstance(username, str) or not re.fullmatch(r'[A-Za-z0-9_-]{3,32}', username):
            raise ValueError('Neplatne prihlasovaci jmeno webu (3-32 znaku).')
        _atomic_json(self.secret_path, self.secrets)
        return self

    def update(self, changes: dict, passcode: str | None = None):
        new = validate_config(_merge_known(copy.deepcopy(self.data), changes))
        if passcode is not None:
            if passcode and (not passcode.isascii() or not passcode.isdigit() or not 0 <= int(passcode) <= 32767):
                raise ValueError('APRS-IS passcode musí být číslo 0–32767.')
        self.data = new
        _atomic_json(self.path, self.data)
        if passcode is not None:
            self.secrets['igate_passcode'] = passcode
            _atomic_json(self.secret_path, self.secrets)
        return self.public_view()

    def public_view(self):
        result = copy.deepcopy(self.data)
        result['igate']['has_passcode'] = bool(self.secrets['igate_passcode'])
        return result

    def links(self, host='127.0.0.1'):
        prefix=f'http://{host}:{self.data["web"]["port"]}'
        return {'web': prefix+'/',
                'login': prefix+'/login',
                'map': prefix+'/map?key='+self.secrets['viewer_token'],
                'admin':prefix+'/app',
                'messages':prefix+'/app#messages',
                'operations':prefix+'/app#objects'}
