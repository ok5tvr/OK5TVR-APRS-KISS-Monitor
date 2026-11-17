"""Persistent object definitions and runtime-only, paced scheduling."""
import copy
import math
import re
import time
from datetime import datetime
from aprs_messages import normalize_path


def validate_entries(entries):
    if not isinstance(entries, list) or len(entries)>5:
        raise ValueError('Ulož nejvýše 5 objektů.')
    result=[]; names=set()
    for entry in entries:
        if not isinstance(entry,dict): raise ValueError('Invalid object')
        name=str(entry.get('name','')).strip().upper()
        if not re.fullmatch(r'[A-Z0-9 _.-]{1,9}',name) or name in names:
            raise ValueError('Objekt musí mít jedinečný název, 1–9 ASCII znaků.')
        names.add(name)
        lat=float(entry.get('lat',0)); lon=float(entry.get('lon',0))
        if not math.isfinite(lat) or not math.isfinite(lon) or not -90<=lat<=90 or not -180<=lon<=180:
            raise ValueError('Invalid coordinates')
        comment=entry.get('comment',''); table=entry.get('symbol_table','/'); symbol=entry.get('symbol','r')
        if not isinstance(comment,str) or not re.fullmatch(r'[\x20-\x7e]{0,43}',comment): raise ValueError('Komentář: max. 43 ASCII znaků.')
        if table not in ('/','\\') or not isinstance(symbol,str) or len(symbol)!=1 or not 33<=ord(symbol)<=126: raise ValueError('Invalid symbol')
        transport=entry.get('transport','rf'); schedule=entry.get('schedule','manual')
        if transport not in ('rf','inet') or schedule not in ('manual','interval','times'): raise ValueError('Invalid transport/schedule')
        interval=entry.get('interval_minutes',30)
        if isinstance(interval,bool) or not isinstance(interval,(float,int)) or not math.isfinite(interval) or not 1<=interval<=1440: raise ValueError('Interval: 1–1440 min.')
        times=entry.get('times',[])
        if not isinstance(times,list) or len(times)>24 or any(not isinstance(t,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',t) for t in times): raise ValueError('Časy: HH:MM, nejvýše 24.')
        if schedule=='times' and not times: raise ValueError('Zadej alespoň jeden čas.')
        for flag in ('enabled','alive'):
            if flag in entry and type(entry[flag]) is not bool: raise ValueError('Invalid flag')
        result.append(dict(name=name,lat=lat,lon=lon,comment=comment,symbol_table=table,symbol=symbol,
            transport=transport,path=normalize_path(entry.get('path','WIDE1-1')),schedule=schedule,
            interval_minutes=interval,times=sorted(set(times)),enabled=entry.get('enabled',True),alive=entry.get('alive',True)))
    return result


class ObjectSchedule:
    def __init__(self):
        self.active=False; self.epoch=0; self.next={}; self.seen=set(); self.status={}; self.pace=0
    def stop(self):
        self.active=False; self.epoch+=1; self.next={}; self.seen=set()
    def start(self,entries,now=None):
        self.stop(); self.active=True
        now=time.monotonic() if now is None else now
        self.next={i:now+e['interval_minutes']*60 for i,e in enumerate(entries)}
        self.pace=now
    def tick(self,entries,send,now=None,wall=None):
        now=time.monotonic() if now is None else now
        wall=wall or datetime.now().astimezone()
        if not self.active or now<self.pace:return
        day=wall.strftime('%Y-%m-%d'); minute=wall.strftime('%H:%M')
        self.seen={key for key in self.seen if key[0]==day}
        for i,e in enumerate(entries):
            if not e['enabled'] or e['schedule']=='manual':continue
            key=(day,minute,i)
            due=(now>=self.next.get(i,now)) if e['schedule']=='interval' else (minute in e['times'] and key not in self.seen)
            if not due:continue
            # Consume a deadline even if the transport is down; never replay missed slots.
            self.next[i]=now+e['interval_minutes']*60; self.seen.add(key); self.pace=now+5
            try: self.status[i]=send(i,e)
            except (ValueError,RuntimeError) as exc:self.status[i]=str(exc)
            return
    def snapshot(self,entries):
        return dict(active=self.active,entries=copy.deepcopy(entries),status={str(k):v for k,v in self.status.items()},
                    device_time=datetime.now().astimezone().isoformat(timespec='seconds'))
