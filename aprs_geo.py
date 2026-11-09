"""Ground-distance/initial-bearing for APRS stations, not an RF propagation metric."""
from __future__ import annotations
import math

POINTS_CS = ('S', 'SSV', 'SV', 'VSV', 'V', 'VJV', 'JV', 'JJV',
             'J', 'JJZ', 'JZ', 'ZJZ', 'Z', 'ZSZ', 'SZ', 'SSZ')
POINTS_EN = ('N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
             'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW')

def distance_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> dict:
    """Great-circle distance (km) and *initial true bearing* from point 1 to point 2.

    The calculation is geographic and does not prove direct VHF propagation.
    """
    coords = (lat1, lon1, lat2, lon2)
    if not all(isinstance(x, (int,float)) and math.isfinite(x) for x in coords):
        raise ValueError('Invalid GPS coordinates')
    if max(abs(lat1),abs(lat2)) > 90 or max(abs(lon1),abs(lon2)) > 180:
        raise ValueError('GPS coordinates out of range')
    p1, p2 = math.radians(lat1), math.radians(lat2)
    delta_lat = p2 - p1
    delta_lon = math.radians(((lon2-lon1+180) % 360)-180)
    a = math.sin(delta_lat/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(delta_lon/2)**2
    km = 6371.0088 * 2 * math.asin(min(1.0,math.sqrt(max(0.0,a))))
    if km < 0.001:  # Bearing at the same position is undefined.
        return dict(distance_km=round(km,2),bearing_deg=None,compass_cs='—',compass_en='—')
    y = math.sin(delta_lon) * math.cos(p2)
    x = math.cos(p1)*math.sin(p2) - math.sin(p1)*math.cos(p2)*math.cos(delta_lon)
    bearing=(math.degrees(math.atan2(y,x))+360)%360
    index=int((bearing+11.25)//22.5)%16
    return dict(distance_km=round(km,2),bearing_deg=round(bearing,1),
                compass_cs=POINTS_CS[index],compass_en=POINTS_EN[index])
