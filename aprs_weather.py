"""Conservative APRS weather decoding for standard ASCII weather extensions.

Units follow APRS spec: temperature °F, wind mph, pressure tenths of hPa,
rain hundredths of inch, humidity "00" means 100 percent.
Incomplete and ambiguous fields stay null; never invent measurements.
"""
from __future__ import annotations

import re


def _number(text, pattern, minimum, maximum, multiplier=1.0, offset=0.0):
    hit = re.search(pattern, text)
    if not hit:
        return None
    try:
        value = int(hit.group(1))
    except ValueError:
        return None
    if not minimum <= value <= maximum:
        return None
    return round(value * multiplier + offset, 2)


def decode_weather(info: bytes) -> dict | None:
    if not isinstance(info, (bytes, bytearray)) or len(info) > 1000:
        return None
    text = bytes(info).decode('ascii', 'replace')
    # '_' at the beginning denotes timestamped positionless WX. Position-bearing
    # WX requires a weather-symbol suffix (underscore) after lat/lon.
    is_weather = text.startswith('_') or (text[:1] in ('!', '=', '/', '@', ';', ')')
                      and re.search(r'[0-9]{4}\.[0-9]{2}[NS].{1}[0-9]{5}\.[0-9]{2}[EW]_', text[:70]) is not None)
    if not is_weather:
        return None
    # Some positionless WX reports begin with DDHHMMz or HHMMSS, then cDDD...
    # Look for standard weather field tags after the APRS leading payload.
    data = text
    wind_direction = _number(data, r'c([0-9]{3})(?=s[0-9.]{3})', 0, 360)
    wind_mph = _number(data, r'c[0-9]{3}s([0-9]{3})', 0, 400)
    if wind_direction is None:
        wind_mph = None
    temperature_f = re.search(r't(-?[0-9]{3})', data)
    temp = None
    if temperature_f:
        value=int(temperature_f.group(1))
        if -150 <= value <= 160:
            temp=round((value-32)*5/9,2)
    gust = _number(data, r'g([0-9]{3})', 0, 400)
    rain_h = _number(data, r'r([0-9]{3})', 0, 999, .254)
    rain_24 = _number(data, r'p([0-9]{3})', 0, 999, .254)
    rain_00 = _number(data, r'P([0-9]{3})', 0, 999, .254)
    humidity = _number(data, r'h([0-9]{2})', 0, 99)
    if humidity == 0:
        humidity = 100
    pressure = _number(data, r'b([0-9]{5})', 8000, 11000, .1)
    result = {'temperature_c':temp, 'wind_direction_deg':wind_direction,
              'wind_kmh':round(wind_mph*1.609344,2) if wind_mph is not None else None,
              'gust_kmh':round(gust*1.609344,2) if gust is not None else None,
              'rain_1h_mm':rain_h, 'rain_24h_mm':rain_24,
              'rain_midnight_mm':rain_00, 'humidity_pct':humidity,
              'pressure_hpa':pressure}
    return result if any(value is not None for value in result.values()) else None
