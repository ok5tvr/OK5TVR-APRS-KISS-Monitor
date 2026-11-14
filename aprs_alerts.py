"""Low-overhead, bounded APRS notifications and optional MQTT publishing.

No received APRS text is executed. MQTT is optional and OFF by default.
Alerts never trigger KISS RF transmissions. Local database is not required.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import json
import queue
import threading
import time


class AlertEngine:
    def __init__(self, config=None, clock=time.monotonic):
        self.clock = clock
        self.config = {}
        self.history = deque(maxlen=100)
        self.last = {}
        self.serial = 0
        self.mqtt_queue = queue.Queue(maxsize=24)
        self.mqtt_stop = threading.Event()
        self.mqtt_errors = 0
        self.worker = threading.Thread(target=self._mqtt_loop,daemon=True,name='ok5tvr-alert-mqtt')
        self.configure(config or {'enabled':False})
        self.worker.start()

    def configure(self, config):
        self.config = dict(config)
        self.last.clear()

    def _new(self,code,message,level='info',call='',cooldown=900):
        if not self.config.get('enabled',False):
            return None
        now=self.clock()
        key=(code,call)
        if now-self.last.get(key,float('-inf'))<cooldown:
            return None
        self.last[key]=now
        self.serial+=1
        event={'id':self.serial,
               'at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
               'code':code, 'level':level,'message':message[:200],
               'callsign':call[:12]}
        self.history.appendleft(event)
        if self.config.get('mqtt_enabled',False):
            try:self.mqtt_queue.put_nowait(event)
            except queue.Full:self.mqtt_errors+=1
        return event

    def on_packet(self,packet,weather=None):
        if getattr(packet,'simulated',False):
            return
        call=packet.source.upper()
        if call in self.config.get('watch_calls',[]):
            self._new('watched_station',f'{call} slyšena na RF',call=call,cooldown=900)
        if not weather:
            return
        t=self.config.get('weather_temp_high')
        if t is not None and weather.get('temperature_c') is not None and weather['temperature_c']>=t:
            self._new('weather_temperature',f'{call}: {weather["temperature_c"]} °C >= {t} °C',
                      'warning',call,cooldown=1800)
        p=self.config.get('weather_pressure_low')
        if p is not None and weather.get('pressure_hpa') is not None and weather['pressure_hpa']<=p:
            self._new('weather_pressure',f'{call}: {weather["pressure_hpa"]} hPa <= {p} hPa',
                      'warning',call,cooldown=1800)

    def tick(self,*,uptime,radio_connected,last_rf_at,igate_online,igate_enabled):
        if uptime>=self.config.get('offline_seconds',300) and not radio_connected:
            self._new('tnc_offline','Primární KISS TNC není připojeno','warning',cooldown=900)
        rf_delay=self.config.get('no_rf_minutes',30)*60
        if radio_connected and uptime>=rf_delay and (
                last_rf_at is None or self.clock()-last_rf_at>=rf_delay):
            self._new('no_rf','Žádný RF APRS paket v nastaveném intervalu','warning',cooldown=1800)
        if igate_enabled and uptime>=self.config.get('offline_seconds',300) and not igate_online:
            self._new('igate_offline','APRS-IS spojení není dostupné','warning',cooldown=900)

    def snapshot(self):
        return {'enabled':self.config.get('enabled',False),
                'events':list(self.history),'latest_id':self.serial,
                'mqtt_enabled':self.config.get('mqtt_enabled',False),
                'mqtt_queued':self.mqtt_queue.qsize(),
                'mqtt_errors':self.mqtt_errors}

    def _mqtt_loop(self):
        while not self.mqtt_stop.is_set():
            try:event=self.mqtt_queue.get(timeout=.2)
            except queue.Empty:continue
            if not self.config.get('mqtt_enabled',False):continue
            try:
                from paho.mqtt import publish
                publish.single(self.config['mqtt_topic'],
                    json.dumps(event,ensure_ascii=False),qos=0,retain=False,
                    hostname=self.config['mqtt_host'],
                    port=self.config['mqtt_port'],keepalive=5)
            except (ImportError,OSError,ValueError) as exc:
                self.mqtt_errors+=1

    def close(self):
        self.mqtt_stop.set()
        self.worker.join(timeout=2)
