"""Receive-only, independently reconnecting KISS interfaces (max. two).

Each receiver has a dedicated session and queue. No secondary reader can ever
send RF, enable DIGI, or take ownership of the main TNC. No DSP modulation.
"""
from __future__ import annotations

import collections
import queue
import threading
import time

from aprs_serial import SerialReader
from aprs_tcp import TCPKissReader


class ReadOnlySerial(SerialReader):
    def send(self, encoded_kiss, category='manual'):
        return False


class ReadOnlyTCP(TCPKissReader):
    def send(self, encoded_kiss, category='manual'):
        return False


class SecondaryTNCManager:
    def __init__(self, devices=None, retry_seconds=5):
        self.retry_seconds=retry_seconds
        self.events=queue.Queue(maxsize=1024)
        self.devices={}
        self.entries={}
        self.sessions={}
        self.next_session=1000
        self.configure(devices or [])

    def configure(self, devices):
        self.close()
        self.devices={}
        self.entries={}
        self.sessions={}
        for item in devices:
            self.devices[item['id']]=dict(item)
            self.entries[item['id']]={'reader':None,'stop':None,'next':0.,
                'online':False,'rx':0,'last_rx':'','last_error':'','connections':0}

    def tick(self,on_packet,primary_endpoint=''):
        # Poll secondary RX independently; never block main KISS service.
        for _ in range(120):
            try:session,action,payload=self.events.get_nowait()
            except queue.Empty:break
            name=self.sessions.get(session)
            if name is None or name not in self.entries:continue
            entry=self.entries[name]
            if action=='connected':
                entry['online']=True
                entry['connections']+=1
                entry['last_error']=''
            elif action=='frame':
                entry['rx']+=1
                entry['last_rx']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
                payload.receiver=name
                on_packet(payload,name)
            elif action in ('error','invalid'):
                entry['last_error']=str(payload)[:180]
            elif action=='closed':
                entry['online']=False
                self._stop(name)
        now=time.monotonic()
        for name,conf in self.devices.items():
            if not conf['enabled']:continue
            entry=self.entries[name]
            if entry['reader'] or now<entry['next']:continue
            endpoint=(conf['serial_port'] if conf['transport']=='serial' else
                      f"{conf['host']}:{conf['port']}")
            if endpoint==primary_endpoint:
                entry['last_error']='Primary TNC port already in use'
                entry['next']=now+self.retry_seconds
                continue
            stop=threading.Event()
            self.next_session+=1
            session=self.next_session
            if conf['transport']=='serial':
                reader=ReadOnlySerial(conf['serial_port'],conf['baud'],
                                     self.events,stop,session)
            else:
                reader=ReadOnlyTCP(conf['host'],conf['port'],self.events,stop,session)
            entry['reader']=reader
            entry['stop']=stop
            entry['next']=now+self.retry_seconds
            self.sessions[session]=name
            reader.start()

    def _stop(self,name):
        entry=self.entries[name]
        reader=entry['reader']
        entry['online']=False
        entry['reader']=None
        stopper=entry['stop']
        entry['stop']=None
        if stopper:stopper.set()
        if reader:
            self.sessions.pop(reader.session,None)
            if reader is not threading.current_thread():
                reader.join(timeout=1)

    def close(self):
        for name in list(self.entries):
            self._stop(name)

    def snapshot(self):
        return [
            {'id':name,'transport':cfg['transport'],'endpoint':(
                cfg['serial_port'] if cfg['transport']=='serial' else
                f"{cfg['host']}:{cfg['port']}"),
             'enabled':cfg['enabled'],'connected':self.entries[name]['online'],
             'rx':self.entries[name]['rx'],
             'last_rx':self.entries[name]['last_rx'],
             'last_error':self.entries[name]['last_error'],
             'connections':self.entries[name]['connections'],
             'rx_only':True}
            for name,cfg in self.devices.items()
        ]
