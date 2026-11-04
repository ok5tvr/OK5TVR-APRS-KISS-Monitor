"""Validated configuration and private credentials for headless APRS service.

No network, RF, or state-changing action is enabled on a fresh installation.
Sensitive credentials are stored in a separate 0600 file (never in web API output).
"""
from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import re
import secrets
import tempfile

from aprs_features import CALL_RE
from aprs_messages import normalize_call, normalize_path
from aprs_digi import DigiConfig
from aprs_station import decimal_coordinate, aprsis_position
from aprs_operations import validate_objects_settings

DEFAULT_PATH = Path.home() / '.config' / 'ok5tvr-aprs' / 'config.json'
DEFAULT_CONFIG = {
    'serial': {'port': 'auto', 'baud': 115200, 'retry_seconds': 4},
    'web': {'port': 8765, 'lan': False},
    'igate': {'call': 'OK5TVR-10', 'host': 'rotate.aprs2.net', 'port': 14580,
              'autostart': False},
    'digi': {'call': 'OK5TVR-3', 'mode': 'fill', 'trace': False,
             'delay_s': 4.0, 'max_per_min': 6, 'min_gap_s': 3.0,
             'autostart': False},
    'messages': {'target': '', 'path': 'WIDE1-1', 'auto_ack': False,
                 'retry_seconds': 45, 'max_attempts': 3},
    'health': {'quiet_warning_minutes': 30, 'disconnect_warning_seconds': 15},
    'objects': {'path': 'WIDE1-1', 'entries': []},
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
    w = v['web']
    w['port'] = _int(w['port'], 'Web port', 1024, 65535)
    w['lan'] = _bool(w['lan'], 'Přístup z LAN')
    i = v['igate']
    if not isinstance(i['call'], str) or not CALL_RE.fullmatch(i['call'].upper()):
        raise ValueError('Zadej platnou AX.25 značku iGate, např. OK5TVR-10.')
    i['call'] = i['call'].upper()
    if not isinstance(i['host'], str) or not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', i['host']) or i['host'].startswith(('-', '.')):
        raise ValueError('Neplatný APRS-IS server.')
    i['port'] = _int(i['port'], 'APRS-IS port', 1, 65535)
    i['autostart'] = _bool(i['autostart'], 'Automatický iGate')
    d = v['digi']
    if not isinstance(d['call'], str):
        raise ValueError('DIGI značka musí být text.')
    d['call'] = d['call'].upper()
    d['trace'] = _bool(d['trace'], 'TRACE')
    d['autostart'] = _bool(d['autostart'], 'Automatický DIGI')
    d['delay_s'] = float(d['delay_s']) if type(d['delay_s']) in (int, float) else d['delay_s']
    d['min_gap_s'] = float(d['min_gap_s']) if type(d['min_gap_s']) in (int, float) else d['min_gap_s']
    d['max_per_min'] = _int(d['max_per_min'], 'DIGI TX/min', 1, 12)
    DigiConfig(d['call'], d['mode'], d['trace'], d['delay_s'],
               d['max_per_min'], d['min_gap_s']).validate()
    m = v['messages']
    if not isinstance(m['target'], str) or len(m['target']) > 9:
        raise ValueError('Neplatná výchozí cílová značka.')
    m['target'] = normalize_call(m['target']) if m['target'].strip() else ''
    if m['target'] == i['call']:
        raise ValueError('Cílová značka zpráv se nesmí rovnat vlastní značce.')
    m['path'] = normalize_path(m['path'])
    m['auto_ack'] = _bool(m['auto_ack'], 'Automatické potvrzování APRS zpráv (RF TX)')
    m['retry_seconds'] = _int(m['retry_seconds'], 'Opakování zprávy (s)', 30, 180)
    m['max_attempts'] = _int(m['max_attempts'], 'Počet odeslání', 1, 5)
    h = v['health']
    h['quiet_warning_minutes'] = _int(h['quiet_warning_minutes'], 'Upozornění na ticho (min)', 5, 240)
    h['disconnect_warning_seconds'] = _int(h['disconnect_warning_seconds'], 'Výpadek USB (s)', 5, 300)
    v['objects'] = validate_objects_settings(v['objects'])
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
        aprsis_position(i['call'], p['latitude'], p['longitude'], p['comment'], 'R&')
    return v


class ServiceConfig:
    def __init__(self, path: str | Path = DEFAULT_PATH):
        self.path = Path(path).expanduser().resolve()
        self.secret_path = self.path.with_name('secrets.json')
        self.data = None
        self.secrets = None

    def load_or_create(self):
        if self.path.exists():
            self.data = validate_config(json.loads(self.path.read_text(encoding='utf-8')))
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
            'viewer_token': secret_data.get('viewer_token') or secrets.token_urlsafe(32),
            'admin_token': secret_data.get('admin_token') or secrets.token_urlsafe(32),
            'igate_passcode': str(secret_data.get('igate_passcode', '')),
        }
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

    def export_backup(self):
        """Portable non-secret backup. Never include passcode or bearer keys."""
        from datetime import datetime, timezone
        return {'format': 'ok5tvr-config-v1',
                'created_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
                'config': copy.deepcopy(self.data),
                'note': 'Secrets are NOT included. Re-enter APRS-IS passcode on target.'}

    def restore_backup(self, document):
        """Import with all automatic TX/network actions disabled for safety."""
        if not isinstance(document, dict) or document.get('format') != 'ok5tvr-config-v1':
            raise ValueError('Neznámý formát zálohy. Vyber export OK5TVR.')
        raw = document.get('config')
        if not isinstance(raw, dict):
            raise ValueError('Záloha neobsahuje konfiguraci.')
        # validate entire payload before writing anything
        clean = validate_config(raw)
        clean['digi']['autostart'] = False
        clean['igate']['autostart'] = False
        clean['messages']['auto_ack'] = False
        return self.update(clean)

    def public_view(self):
        result = copy.deepcopy(self.data)
        result['igate']['has_passcode'] = bool(self.secrets['igate_passcode'])
        return result

    def links(self, host='127.0.0.1'):
        prefix=f'http://{host}:{self.data["web"]["port"]}'
        return {'map': prefix+'/?key='+self.secrets['viewer_token'],
                'admin':prefix+'/control?admin='+self.secrets['admin_token'],
                'messages':prefix+'/messages?admin='+self.secrets['admin_token'],
                'objects':prefix+'/operations?admin='+self.secrets['admin_token'],
                'diagnostics':prefix+'/diagnostics?admin='+self.secrets['admin_token']}
