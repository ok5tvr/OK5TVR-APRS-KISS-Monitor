"""APRS RF objects/items/status/position, validated before KISS transmission.

APRS 1.0.1 object: ;NAME_____*DDHHMMzDDMM.mmN/DDDMM.mmE>comment
Only printable ASCII on RF. Timestamp is UTC and live/dead is * / _.
This module never transmits on its own.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re

from aprs_features import encode_ui_packet, CALL_RE
from aprs_messages import normalize_path
from aprs_station import aprs_coord, decimal_coordinate

OBJECT_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,8}$")
ITEM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,8}$")
MAX_OBJECTS = 20


def ascii_text(value, max_length=43, allow_empty=True):
    if not isinstance(value, str) or len(value) > max_length or (not allow_empty and not value):
        raise ValueError(f"Text musí mít 1–{max_length} ASCII znaků." if not allow_empty
                         else f"Text smí mít nejvýše {max_length} ASCII znaků.")
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in value):
        raise ValueError("Text musí obsahovat pouze tisknutelné ASCII znaky bez diakritiky.")
    return value


def validate_object(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Objekt musí být JSON objekt.")
    allowed = {'name', 'latitude', 'longitude', 'symbol_table', 'symbol',
               'comment', 'repeat', 'interval_minutes', 'kind'}
    if set(value) - allowed:
        raise ValueError("Nepodporované pole APRS objektu.")
    name = value.get('name', '')
    if not isinstance(name, str) or not OBJECT_NAME_RE.fullmatch(name):
        raise ValueError("Název objektu musí mít 1–9 znaků (A-Z, 0-9, mezera, _ . -).")
    kind = value.get('kind', 'object')
    if kind not in ('object', 'item'):
        raise ValueError("Typ musí být object nebo item.")
    # APRS uncompressed position: table / or backslash, printable symbol code.
    symbol_table = value.get('symbol_table', '/')
    symbol = value.get('symbol', '>')
    if symbol_table not in ('/', '\\') or not isinstance(symbol, str) or len(symbol) != 1 or not 33 <= ord(symbol) <= 126:
        raise ValueError("Neplatný APRS symbol. Tabulka / nebo \\, jediný tisknutelný znak symbolu.")
    repeat = value.get('repeat', False)
    if type(repeat) is not bool:
        raise ValueError("Opakování objektu musí být true/false.")
    interval = value.get('interval_minutes', 30)
    if type(interval) is not int or not 10 <= interval <= 180:
        raise ValueError("Interval objektu musí být 10–180 minut.")
    return {
        'name': name,
        'latitude': decimal_coordinate(value.get('latitude'), True),
        'longitude': decimal_coordinate(value.get('longitude'), False),
        'symbol_table': symbol_table,
        'symbol': symbol,
        'comment': ascii_text(value.get('comment', ''), 43),
        'repeat': repeat,
        'interval_minutes': interval,
        'kind': kind,
    }


def validate_objects_settings(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) - {'path', 'entries'}:
        raise ValueError('Neplatné nastavení APRS objektů.')
    path = normalize_path(value.get('path', 'WIDE1-1'))
    entries = value.get('entries', [])
    if not isinstance(entries, list) or len(entries) > MAX_OBJECTS:
        raise ValueError(f'Lze uložit nejvýše {MAX_OBJECTS} objektů.')
    clean = [validate_object(entry) for entry in entries]
    names = [(x['kind'], x['name']) for x in clean]
    if len(set(names)) != len(names):
        raise ValueError('Duplicitní názvy APRS objektů.')
    return {'path': path, 'entries': clean}


def object_info(entry: dict, alive=True, now: datetime | None = None) -> str:
    obj = validate_object(entry)
    lat = aprs_coord(obj['latitude'], True)
    lon = aprs_coord(obj['longitude'], False)
    symbol = obj['symbol_table'] + lon + obj['symbol']
    state = '*' if alive else '_'
    if obj['kind'] == 'object':
        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError('APRS čas musí obsahovat časovou zónu.')
        utc = current.astimezone(timezone.utc)
        stamp = utc.strftime('%d%H%Mz')
        result = ';' + obj['name'].ljust(9) + state + stamp + lat + symbol + obj['comment']
    else:
        result = ')' + obj['name'] + ('!' if alive else '_') + lat + symbol + obj['comment']
    result.encode('ascii')
    return result


def status_info(text: str) -> str:
    return '>' + ascii_text(text, 67, allow_empty=False)


def position_info(lat, lon, symbol_table='/', symbol='&', comment='') -> str:
    lat = decimal_coordinate(lat, True)
    lon = decimal_coordinate(lon, False)
    if symbol_table not in ('/', '\\') or len(symbol) != 1 or not 33 <= ord(symbol) <= 126:
        raise ValueError('Neplatný APRS symbol pozice.')
    return '!' + aprs_coord(lat, True) + symbol_table + aprs_coord(lon, False) + symbol + ascii_text(comment, 43)


def make_rf_frame(source: str, path: str, info: str) -> bytes:
    if not isinstance(source, str) or not CALL_RE.fullmatch(source.upper()):
        raise ValueError('Neplatná volací značka vysílače.')
    normalized_path = normalize_path(path)
    info.encode('ascii')
    return encode_ui_packet(source.upper(), 'APZKIS', normalized_path, info)
