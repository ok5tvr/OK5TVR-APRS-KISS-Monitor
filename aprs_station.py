"""Station coordinates, APRS-IS-only position beacons and non-secret local settings."""
from __future__ import annotations
import json
import math
import os
import re
from pathlib import Path

SETTINGS = Path.home() / '.ok5tvr_aprs_monitor.json'


def decimal_coordinate(value, latitude: bool) -> float:
    try:
        v = float(str(value).strip().replace(',', '.'))
    except ValueError:
        raise ValueError('Souřadnice musí být desetinné číslo (např. 49.7384).') from None
    if not math.isfinite(v) or abs(v) > (90 if latitude else 180):
        raise ValueError('GPS souřadnice mimo rozsah ±90°/±180°.')
    return v


def maidenhead_center(locator: str) -> tuple[float, float]:
    """Approximate center of 4/6/8-char Maidenhead square; not exact QTH."""
    loc=locator.upper().strip()
    if len(loc) not in (4,6,8) or not re.fullmatch(r'[A-R]{2}[0-9]{2}(?:[A-X]{2}(?:[0-9]{2})?)?',loc):
        raise ValueError('Lokátor musí mít formát JN69 nebo JN69PS (případně 8 znaků).')
    lon=-180+(ord(loc[0])-65)*20+(ord(loc[2])-48)*2
    lat=-90+(ord(loc[1])-65)*10+(ord(loc[3])-48)
    width,height=2.0,1.0
    if len(loc)>=6:
        width/=24; height/=24
        lon+=(ord(loc[4])-65)*width;lat+=(ord(loc[5])-65)*height
    if len(loc)>=8:
        width/=10; height/=10
        lon+=(ord(loc[6])-48)*width;lat+=(ord(loc[7])-48)*height
    return round(lat+height/2,7),round(lon+width/2,7)


def aprs_coord(value: float, latitude: bool) -> str:
    total=round(abs(value)*6000)
    deg, mins=divmod(total,6000)
    limit=90 if latitude else 180
    if deg>limit or (deg==limit and mins): raise ValueError('Poloha mimo rozsah APRS')
    hemi=('N' if value>=0 else 'S') if latitude else ('E' if value>=0 else 'W')
    return f'{deg:02d}{mins//100:02d}.{mins%100:02d}{hemi}' if latitude else f'{deg:03d}{mins//100:02d}.{mins%100:02d}{hemi}'


def aprsis_position(call: str, lat: float, lon: float, comment: str='OK5TVR RX iGate', symbol: str='R&') -> str:
    from aprs_features import CALL_RE
    call=call.strip().upper()
    if not CALL_RE.fullmatch(call):
        raise ValueError('Neplatná značka iGate. Použij např. OK5TVR-10.')
    lat=decimal_coordinate(lat,True); lon=decimal_coordinate(lon,False)
    if symbol not in ('R&','I&','I#','1#','/#'):
        raise ValueError('Nepodporovaný APRS symbol')
    comment=comment.strip()
    if len(comment)>43 or any(ord(c)<32 or ord(c)>126 for c in comment):
        raise ValueError('Komentář: maximálně 43 znaků ASCII bez diakritiky.')
    # & gateway symbol with R overlay (receive-only); no q constructs in client-originated packets.
    payload='!'+aprs_coord(lat,True)+symbol[0]+aprs_coord(lon,False)+symbol[1]+comment
    line=f'{call}>APZKIS,TCPIP*:{payload}'
    if len(line.encode('ascii'))+2>512: raise ValueError('Překročen limit APRS-IS')
    return line


def load_settings() -> dict:
    try:
        value=json.loads(SETTINGS.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else {}
    except (OSError,ValueError,UnicodeError):
        return {}


def save_settings(data: dict):
    """Persist location and callsign only. Never save passcode or enable radio TX."""
    clean={k:data[k] for k in ('latitude','longitude','comment','locator','beacon_enabled',
                             'beacon_interval','igate_call','digi_call','digi_mode','digi_trace','ui_language') if k in data}
    temporary=SETTINGS.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(clean,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    if os.name!='nt': os.chmod(temporary,0o600)
    temporary.replace(SETTINGS)
