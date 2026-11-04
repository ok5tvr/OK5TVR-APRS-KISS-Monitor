#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single-window desktop frontend for OK5TVR APRS.

The very same APRSService handles KISS RX/TX, iGate, DIGI, messages, telemetry,
objects and journal. In desktop mode it does NOT start an HTTP server and it
owns exactly one serial reader. All RF actions still require explicit consent.
"""
from __future__ import annotations

import csv
import json
import logging
import math
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from aprs_service import APRSService
from aprs_station import load_settings, save_settings
from service_config import ServiceConfig

VERSION = '1.8.0-rc1'
BG = '#101925'
PANEL = '#1a293a'
INSET = '#203247'
FG = '#eaf2f9'
MUTED = '#aac1d1'
GREEN = '#35d1b6'
ORANGE = '#f3bf76'


class NativeMap(tk.Frame):
    """Offline Tkinter map, no browser, network or additional dependencies."""
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.center_lat, self.center_lon = 49.74, 13.37
        self.lon_span = 16.0
        self.canvas = tk.Canvas(self, bg='#10263c', highlightthickness=0, cursor='fleur')
        self.canvas.pack(fill='both', expand=True)
        self.stations = []
        self.own = None
        self.digi = None
        self._drag = None
        self._map_cache = None
        self._geo = None
        self._pin_data = []
        self._scheduled = False
        self.on_pin = lambda station: None
        self.canvas.bind('<Configure>', lambda _: self.redraw_later())
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<Button-4>', lambda e: self.zoom(0.75))
        self.canvas.bind('<Button-5>', lambda e: self.zoom(1.3))
        self.canvas.bind('<ButtonPress-1>', self._press)
        self.canvas.bind('<B1-Motion>', self._move)
        self.canvas.bind('<ButtonRelease-1>', self._release)

    def _load_geo(self):
        if self._geo is None:
            try:
                self._geo = json.loads((Path(__file__).resolve().parent / 'offline_geography.json').read_text('utf-8'))
            except (OSError, ValueError):
                self._geo = {}
        return self._geo

    def _projection(self):
        w = max(1, self.canvas.winfo_width())
        h = max(1, self.canvas.winfo_height())
        cosine = max(0.2, math.cos(math.radians(self.center_lat)))
        scale = w / self.lon_span
        return w, h, cosine, scale

    def geo_to_screen(self, lat, lon):
        w, h, cosine, scale = self._projection()
        return (w / 2 + (lon - self.center_lon) * scale,
                h / 2 - (lat - self.center_lat) * scale / cosine)

    def screen_to_geo(self, x, y):
        w, h, cosine, scale = self._projection()
        return (self.center_lat - (y - h / 2) * cosine / scale,
                self.center_lon + (x - w / 2) / scale)

    def zoom(self, factor):
        self.lon_span = min(360.0, max(0.15, self.lon_span * factor))
        self.redraw_later()

    def reset(self, lat=None, lon=None):
        if lat is not None and lon is not None:
            self.center_lat, self.center_lon = float(lat), float(lon)
        self.lon_span = 16.0
        self.redraw_later()

    def _wheel(self, event):
        self.zoom(0.75 if event.delta > 0 else 1.3)

    def _press(self, event):
        self._drag = (event.x, event.y, event.x, event.y)

    def _move(self, event):
        if not self._drag:
            return
        x0, y0, x1, y1 = self._drag
        _, _, cosine, scale = self._projection()
        self.center_lon -= (event.x - x1) / scale
        self.center_lat += (event.y - y1) * cosine / scale
        self.center_lat = max(-85, min(85, self.center_lat))
        self._drag = (x0, y0, event.x, event.y)
        self.redraw_later()

    def _release(self, event):
        if self._drag:
            x0, y0, _, _ = self._drag
            if abs(event.x - x0) < 5 and abs(event.y - y0) < 5:
                for x, y, station in reversed(self._pin_data):
                    if abs(x - event.x) <= 14 and abs(y - event.y) <= 14:
                        self.on_pin(station)
                        break
        self._drag = None

    def set_data(self, stations, own, digi):
        self.stations = stations
        self.own, self.digi = own, digi
        self.redraw_later()

    def redraw_later(self):
        if not self._scheduled:
            self._scheduled = True
            self.after(110, self._redraw)

    def _redraw(self):
        self._scheduled = False
        c = self.canvas
        if not c.winfo_exists():
            return
        c.delete('all')
        w, h, cosine, scale = self._projection()
        latitude_half = h * cosine / (2 * scale)
        lo_lon, hi_lon = self.center_lon - self.lon_span/2, self.center_lon + self.lon_span/2
        lo_lat, hi_lat = self.center_lat - latitude_half, self.center_lat + latitude_half
        layer = 'central' if self.lon_span <= 22 and 40 < self.center_lat < 59 else 'europe' if self.lon_span <= 90 else 'world'
        data = self._load_geo().get(layer, {})
        for typ, color, fill in (('land', '#42635e', '#1c4250'),
                                  ('borders', '#769b9d', ''), ('rivers', '#287ca9', '')):
            for item in data.get(typ, []):
                points = item[1] if typ == 'land' else item
                if len(points) < 2:
                    continue
                bbox = (min(p[0] for p in points), max(p[0] for p in points),
                        min(p[1] for p in points), max(p[1] for p in points))
                if bbox[1] < lo_lon or bbox[0] > hi_lon or bbox[3] < lo_lat or bbox[2] > hi_lat:
                    continue
                stride = max(1, len(points)//500)
                xy=[]
                for lon, lat in points[::stride]:
                    xy.extend((w/2+(lon-self.center_lon)*scale,
                               h/2-(lat-self.center_lat)*scale/cosine))
                if len(xy)<4:
                    continue
                if fill and len(xy)>=6:
                    c.create_polygon(xy, outline=color, fill=fill, width=0.8)
                else:
                    c.create_line(xy, fill=color, width=0.8, smooth=False)
        for lat_step in range(-80, 81, 5 if self.lon_span > 25 else 1):
            if not lo_lat <= lat_step <= hi_lat: continue
            _, y = self.geo_to_screen(lat_step, self.center_lon)
            c.create_line(0,y,w,y,fill='#294359',dash=(3,9))
        for lon_step in range(-180, 181, 5 if self.lon_span > 25 else 1):
            if not lo_lon <= lon_step <= hi_lon: continue
            x, _ = self.geo_to_screen(self.center_lat,lon_step)
            c.create_line(x,0,x,h,fill='#294359',dash=(3,9))
        self._pin_data=[]
        for s in self.stations:
            self._pin(s, '#ffd57f', 4)
        if self.own:
            self._pin({**self.own,'call':self.own.get('call','iGate')}, GREEN, 8)
        if self.digi and self.digi.get('active'):
            self._pin({**self.digi,'call':self.digi.get('call','DIGI')}, '#87afff', 7)
        c.create_rectangle(8,h-31,250,h-7,fill='#152a40',outline='#446179')
        c.create_text(15,h-19,anchor='w',text=f'{self.center_lat:.3f}° N / {self.center_lon:.3f}° E  ·  ±{self.lon_span/2:.2f}°',fill=FG,font=('Segoe UI',9))

    def _pin(self, s, color, size):
        try:
            if s.get('lat') is None or s.get('lon') is None:
                return
            x,y = self.geo_to_screen(float(s['lat']),float(s['lon']))
        except (ValueError, TypeError, KeyError):
            return
        w,h,_,_ = self._projection()
        if not 0<=x<=w or not 0<=y<=h:
            return
        self.canvas.create_oval(x-size,y-size,x+size,y+size,fill=color,outline='#071828',width=2)
        self.canvas.create_text(x+size+3,y,anchor='w',text=str(s.get('call','?')),fill=FG,font=('Segoe UI Semibold',9))
        self._pin_data.append((x,y,s))


class DesktopApp:
    """All APRS modules in one Tk notebook. No embedded or external browser."""
    def __init__(self, root, service=None, start_service=True):
        self.root = root
        self.root.title(f'OK5TVR APRS KISS Monitor · v{VERSION}')
        screen_w,screen_h=self.root.winfo_screenwidth(),self.root.winfo_screenheight()
        self.root.geometry(f'{min(1410,max(990,screen_w-45))}x{min(880,max(650,screen_h-85))}')
        self.root.minsize(990,650)
        self.root.configure(bg=BG)
        self.config = service.config if service else ServiceConfig().load_or_create()
        self.service = service or APRSService(self.config)
        self.thread = None
        self.responses = queue.Queue()
        self.last_rx = None
        self.last_msg = None
        self.last_journal = None
        self.current_inbox = []
        self.current_outbox = []
        self.lang = load_settings().get('ui_language','cs')
        if self.lang not in ('cs','en'):
            self.lang='cs'
        self.labels=[]
        self.tabs=[]
        self.variables={}
        self.last_map_refresh=0
        self._closing=False
        self._style()
        self._build()
        self._load_config()
        if start_service:
            self.thread=threading.Thread(target=self.service.run,kwargs={'with_web':False},
                                         name='OK5TVR-APRS-Desktop-Backend',daemon=True)
            self.thread.start()
        self.root.after(400,self._poll)
        self.root.protocol('WM_DELETE_WINDOW',self.close)

    def t(self, cs, en):
        return en if self.lang=='en' else cs

    def label(self,parent,cs,en=None,**kwargs):
        label=tk.Label(parent,text=self.t(cs,en or cs),bg=kwargs.pop('bg',BG),fg=kwargs.pop('fg',FG),
                       font=kwargs.pop('font',('Segoe UI',10)),**kwargs)
        self.labels.append((label,cs,en or cs))
        return label

    def button(self,parent,cs,en,callback,kind='normal',**kwargs):
        button=tk.Button(parent,text=self.t(cs,en),command=callback,bd=0,relief='flat',cursor='hand2',
                          font=('Segoe UI Semibold',10),padx=12,pady=8,
                          bg=GREEN if kind=='primary' else ('#5d3345' if kind=='warn' else INSET),
                          fg=BG if kind=='primary' else FG,activeforeground=FG,
                          activebackground='#357b80',**kwargs)
        self.labels.append((button,cs,en))
        return button

    def tab(self,cs,en):
        frame=tk.Frame(self.notebook,bg=BG)
        self.notebook.add(frame,text=self.t(cs,en))
        self.tabs.append((frame,cs,en))
        return frame

    def _style(self):
        style=ttk.Style(self.root)
        style.theme_use('clam')
        style.configure('APRS.TNotebook',background=BG,borderwidth=0,tabmargins=(0,7,0,0))
        style.configure('APRS.TNotebook.Tab',background=INSET,foreground=FG,
                        font=('Segoe UI Semibold',10),padding=(16,11))
        style.map('APRS.TNotebook.Tab',background=[('selected','#1e7f78')],foreground=[('selected','white')])
        style.configure('APRS.Treeview',background=PANEL,fieldbackground=PANEL,foreground=FG,
                        rowheight=27,font=('Segoe UI',9),borderwidth=0)
        style.configure('APRS.Treeview.Heading',background=INSET,foreground=FG,
                        font=('Segoe UI Semibold',9),padding=7)
        style.map('APRS.Treeview',background=[('selected','#216e80')],foreground=[('selected','white')])
        style.configure('APRS.TCombobox',fieldbackground=INSET,background=INSET,foreground=FG)
        style.map('APRS.TCombobox',fieldbackground=[('readonly',INSET)],foreground=[('readonly',FG)])

    def field(self,parent,cs,en,initial='',width=20,secret=False):
        wrapper=tk.Frame(parent,bg=PANEL)
        wrapper.pack(fill='x',pady=3)
        self.label(wrapper,cs,en,bg=PANEL,fg=MUTED,width=20,anchor='w').pack(side='left')
        var=tk.StringVar(value=str(initial))
        inp=tk.Entry(wrapper,textvariable=var,bg=INSET,fg=FG,insertbackground=FG,
                     font=('Consolas',10),show='*' if secret else '',relief='flat',width=width)
        inp.pack(side='left',fill='x',expand=True,ipady=6)
        return var

    def check(self,parent,cs,en,initial=False):
        var=tk.BooleanVar(value=initial)
        cb=tk.Checkbutton(parent,text=self.t(cs,en),variable=var,bg=PANEL,fg=FG,
                          selectcolor=INSET,activebackground=PANEL,activeforeground=FG,
                          font=('Segoe UI',10),anchor='w')
        cb.pack(fill='x',pady=2)
        self.labels.append((cb,cs,en))
        return var

    def combo(self,parent,cs,en,choices,initial):
        wrap=tk.Frame(parent,bg=PANEL)
        wrap.pack(fill='x',pady=3)
        self.label(wrap,cs,en,bg=PANEL,fg=MUTED,width=20,anchor='w').pack(side='left')
        var=tk.StringVar(value=initial)
        inp=ttk.Combobox(wrap,textvariable=var,values=choices,state='readonly',style='APRS.TCombobox',width=20)
        inp.pack(side='left',fill='x',expand=True)
        return var

    def pane(self,parent,title_cs,title_en):
        p=tk.LabelFrame(parent,text=self.t(title_cs,title_en),bg=PANEL,fg=GREEN,padx=12,pady=10,
                        font=('Segoe UI Semibold',11),relief='groove',bd=1)
        self.labels.append((p,title_cs,title_en))
        return p

    def _tree(self,parent,columns,widths,height=10):
        outer=tk.Frame(parent,bg=PANEL)
        tree=ttk.Treeview(outer,columns=columns,show='headings',height=height,style='APRS.Treeview')
        for name,width in zip(columns,widths):
            tree.heading(name,text=name)
            tree.column(name,width=width,minwidth=50,stretch=name==columns[-1])
        bar=ttk.Scrollbar(outer,orient='vertical',command=tree.yview)
        tree.configure(yscrollcommand=bar.set)
        bar.pack(side='right',fill='y')
        tree.pack(fill='both',expand=True)
        return outer,tree

    def _build(self):
        header=tk.Frame(self.root,bg=BG)
        header.pack(fill='x',padx=17,pady=(11,3))
        self.label(header,'OK5TVR','OK5TVR',fg=GREEN,font=('Segoe UI Semibold',14)).pack(side='left')
        self.label(header,'  APRS KISS Monitor  ·  USB TNC  ·  v1.8 RC1',
                   '  APRS KISS Monitor  ·  USB TNC  ·  v1.8 RC1',font=('Segoe UI',14)).pack(side='left')
        self.language=tk.StringVar(value='EN' if self.lang=='en' else 'CZ')
        pick=ttk.Combobox(header,textvariable=self.language,values=('CZ','EN'),width=4,
                          state='readonly',style='APRS.TCombobox')
        pick.pack(side='right',padx=(8,0))
        pick.bind('<<ComboboxSelected>>',self.switch_language)
        self.label(header,'Jazyk / Language','Language / Jazyk',fg=MUTED).pack(side='right')
        self.status=tk.StringVar(value=self.t('Inicializuji provoz…','Initializing…'))
        self.label(self.root,'', '',fg=MUTED,textvariable=self.status,anchor='w').pack(fill='x',padx=18)
        self.notebook=ttk.Notebook(self.root,style='APRS.TNotebook')
        self.notebook.pack(fill='both',expand=True,padx=13,pady=(3,7))
        self.monitor=self.tab('Příjem / TX','Monitor / TX')
        self.map_tab=self.tab('Mapa','Map')
        self.messages_tab=self.tab('Zprávy','Messages')
        self.objects_tab=self.tab('Objekty','Objects')
        self.config_tab=self.tab('iGate / DIGI','iGate / DIGI')
        self.telemetry_tab=self.tab('Telemetrie','Telemetry')
        self.diagnostics_tab=self.tab('Diagnostika / deník','Diagnostics / log')
        self._build_monitor()
        self._build_map()
        self._build_messages()
        self._build_objects()
        self._build_config()
        self._build_telemetry()
        self._build_diagnostics()
        self.notebook.bind('<<NotebookTabChanged>>',lambda _: self._refresh(force=True))
        self.label(self.root,'Jedno okno · jedna USB KISS služba · RF vysílání jen po potvrzení',
                   'One window · one USB KISS backend · RF transmissions require confirmation',
                   fg=MUTED,font=('Segoe UI',9)).pack(anchor='w',padx=18,pady=(0,9))

    def switch_language(self,event=None):
        self.lang='en' if self.language.get()=='EN' else 'cs'
        saved=load_settings()
        saved['ui_language']=self.lang
        try:save_settings(saved)
        except OSError:pass
        for widget,cs,en in self.labels:
            try:
                if widget.winfo_exists():widget.configure(text=self.t(cs,en))
            except tk.TclError:pass
        for frame,cs,en in self.tabs:
            self.notebook.tab(frame,text=self.t(cs,en))
        self._refresh(force=True)

    def _build_monitor(self):
        top=tk.Frame(self.monitor,bg=PANEL,padx=12,pady=10)
        top.pack(fill='x',padx=7,pady=7)
        self.label(top,'USB KISS port','USB KISS port',bg=PANEL,fg=MUTED).pack(side='left',padx=5)
        self.port=tk.StringVar(value=self.config.data['serial']['port'])
        self.port_combo=ttk.Combobox(top,textvariable=self.port,state='normal',width=21,
                                      style='APRS.TCombobox')
        self.port_combo.pack(side='left',padx=(0,5))
        self.button(top,'⟳ Porty','⟳ Ports',self.refresh_ports).pack(side='left',padx=4)
        self.button(top,'Připojit','Connect',self.serial_connect,kind='primary').pack(side='left',padx=4)
        self.button(top,'Odpojit','Disconnect',lambda:self._act('serial_disconnect',{})).pack(side='left',padx=4)
        self.button(top,'Test RF TX','RF TX test',self.test_tx,kind='warn').pack(side='left',padx=4)
        self.button(top,'Export CSV','Export CSV',self.export_rx_csv).pack(side='right')
        self.refresh_ports()
        self.monitor_counters=tk.StringVar(value='RX 0  ·  TX 0  ·  DIGI 0  ·  APRS-IS 0')
        self.label(self.monitor,'','',textvariable=self.monitor_counters,fg=GREEN,
                   font=('Segoe UI Semibold',11)).pack(anchor='w',padx=18,pady=(7,2))
        grid, self.rx_tree=self._tree(self.monitor,
                     ('Čas','Značka','Cíl','Cesta','Typ','Obsah'),(165,112,100,165,95,550),height=16)
        grid.pack(fill='both',expand=True,padx=8,pady=8)
        self.rx_tree.bind('<<TreeviewSelect>>',self.select_rx)
        self.rx_details=tk.Text(self.monitor,height=5,bg=PANEL,fg=FG,wrap='word',
                                 insertbackground=FG,font=('Consolas',10),relief='flat',padx=9,pady=7)
        self.rx_details.pack(fill='x',padx=8,pady=(0,8))
        self.rx_details.configure(state='disabled')

    def _build_map(self):
        tools=tk.Frame(self.map_tab,bg=BG)
        tools.pack(fill='x',padx=8,pady=(8,4))
        self.button(tools,'+ Přiblížit','+ Zoom in',lambda:self.native_map.zoom(.75)).pack(side='left',padx=3)
        self.button(tools,'− Oddálit','− Zoom out',lambda:self.native_map.zoom(1.3)).pack(side='left',padx=3)
        self.button(tools,'QTH iGate','iGate QTH',self.center_map).pack(side='left',padx=3)
        self.map_description=tk.StringVar(value=self.t('Čekám na GPS pozice…','Waiting for GPS positions…'))
        self.label(tools,'','',fg=MUTED,textvariable=self.map_description).pack(side='right',padx=8)
        body=tk.PanedWindow(self.map_tab,orient='horizontal',bg=BG,sashwidth=6)
        body.pack(fill='both',expand=True,padx=8,pady=5)
        self.native_map=NativeMap(body)
        body.add(self.native_map,stretch='always',minsize=480)
        side=tk.Frame(body,bg=PANEL)
        body.add(side,minsize=235,width=300)
        self.label(side,'Slyšené stanice','Heard stations',bg=PANEL,
                   font=('Segoe UI Semibold',12),fg=GREEN).pack(anchor='w',padx=10,pady=12)
        grid,self.station_tree=self._tree(side,('Značka','Rámců','Pozice'),(115,65,85),height=18)
        grid.pack(fill='both',expand=True,padx=6,pady=3)
        self.station_tree.bind('<<TreeviewSelect>>',self.select_station)
        self.map_selected=tk.StringVar(value='')
        self.label(side,'','',textvariable=self.map_selected,fg=MUTED,bg=PANEL,
                   wraplength=250,justify='left').pack(fill='x',padx=10,pady=10)
        self.native_map.on_pin=self.pin_selected

    def _build_messages(self):
        top=self.pane(self.messages_tab,'Nová zpráva přes RF / USB KISS','New message via RF / USB KISS')
        top.pack(fill='x',padx=8,pady=(8,5))
        fields=tk.Frame(top,bg=PANEL)
        fields.pack(fill='x')
        left=tk.Frame(fields,bg=PANEL)
        left.pack(side='left',fill='x',expand=True,padx=(0,12))
        right=tk.Frame(fields,bg=PANEL)
        right.pack(side='left',fill='x',expand=True)
        self.m_target=self.field(left,'Komu','Recipient',width=13)
        self.m_path=self.combo(left,'RF cesta','RF path',('DIRECT','WIDE1-1','WIDE1-1,WIDE2-1'),'WIDE1-1')
        self.m_body=self.field(right,'Text (ASCII)','Message (ASCII)',width=55)
        self.button(right,'Odeslat APRS zprávu','Send APRS message',self.send_message,kind='primary').pack(anchor='e',pady=5)
        opts=tk.Frame(self.messages_tab,bg=PANEL,padx=10,pady=7)
        opts.pack(fill='x',padx=8,pady=4)
        self.m_aliases=tk.StringVar()
        self.label(opts,'Přijímat pro (SSID):','Receive for (SSID):',bg=PANEL,fg=MUTED).pack(side='left',padx=(0,6))
        tk.Entry(opts,textvariable=self.m_aliases,bg=INSET,fg=FG,insertbackground=FG,
                 relief='flat',width=28).pack(side='left',ipady=6,padx=(0,10))
        self.m_autoack=tk.BooleanVar(value=False)
        cb=tk.Checkbutton(opts,text=self.t('Automatické ACK (RF TX)','Automatic ACK (RF TX)'),
                          variable=self.m_autoack,bg=PANEL,fg=FG,selectcolor=INSET,
                          activebackground=PANEL,activeforeground=FG)
        cb.pack(side='left')
        self.labels.append((cb,'Automatické ACK (RF TX)','Automatic ACK (RF TX)'))
        self.button(opts,'Uložit nastavení','Save settings',self.save_message_settings).pack(side='left',padx=8)
        self.msg_overview=tk.StringVar(value='Inbox 0 · Outbox 0')
        self.label(self.messages_tab,'','',textvariable=self.msg_overview,fg=GREEN).pack(anchor='w',padx=15,pady=3)
        panels=tk.PanedWindow(self.messages_tab,orient='vertical',bg=BG,sashwidth=5)
        panels.pack(fill='both',expand=True,padx=8,pady=(2,4))
        boxin=tk.Frame(panels,bg=PANEL)
        panels.add(boxin,minsize=145,stretch='always')
        self.label(boxin,'Inbox – přijaté RF zprávy','Inbox – received RF messages',
                   fg=GREEN,bg=PANEL,font=('Segoe UI Semibold',11)).pack(anchor='w',padx=7,pady=5)
        grid,self.in_tree=self._tree(boxin,('UTC','Od','Komu','Text','ID'),(175,110,110,620,60),height=8)
        grid.pack(fill='both',expand=True,padx=5)
        buttons=tk.Frame(boxin,bg=PANEL)
        buttons.pack(fill='x',padx=5,pady=4,before=grid)
        self.button(buttons,'ACK','ACK',lambda:self.ack_message(False)).pack(side='left',padx=4)
        self.button(buttons,'REJ','REJ',lambda:self.ack_message(True),kind='warn').pack(side='left',padx=4)
        self.button(buttons,'Odpovědět','Reply',self.reply_message).pack(side='left',padx=4)
        boxout=tk.Frame(panels,bg=PANEL)
        panels.add(boxout,minsize=145,stretch='always')
        self.label(boxout,'Outbox – odeslané zprávy','Outbox – sent messages',
                   fg=GREEN,bg=PANEL,font=('Segoe UI Semibold',11)).pack(anchor='w',padx=7,pady=5)
        grid,self.out_tree=self._tree(boxout,('UTC','Komu','Text','Stav','Pokusy','ID'),(160,110,560,115,70,60),height=7)
        grid.pack(fill='both',expand=True,padx=5)
        btm=tk.Frame(boxout,bg=PANEL)
        btm.pack(fill='x',padx=5,pady=4,before=grid)
        self.button(btm,'Zrušit opakování','Cancel retries',self.cancel_message).pack(side='left',padx=4)
        self.button(btm,'Obnovit','Refresh',lambda:self._refresh(force=True)).pack(side='left',padx=4)
        self.msg_diagnostics=tk.StringVar(value='')
        self.label(self.messages_tab,'','',textvariable=self.msg_diagnostics,fg=MUTED,
                   anchor='w',wraplength=1150).pack(fill='x',padx=12,pady=3)

    def _build_objects(self):
        content=tk.Frame(self.objects_tab,bg=BG)
        content.pack(fill='both',expand=True,padx=8,pady=8)
        left=self.pane(content,'APRS objekty – ruční vysílání','APRS objects – manual transmission')
        left.pack(side='left',fill='both',expand=True,padx=(0,7))
        right=self.pane(content,'Vlastní poziční a statusové zprávy','Own position and status packets')
        right.pack(side='left',fill='both',expand=True,padx=(7,0))
        self.o_name=self.field(left,'Název objektu','Object name','APRS-TEST')
        self.o_lat=self.field(left,'GPS šířka','Latitude','49.7384')
        self.o_lon=self.field(left,'GPS délka','Longitude','13.3736')
        self.o_comment=self.field(left,'Komentář ASCII','ASCII comment','OK5TVR APRS')
        self.o_path=self.combo(left,'RF cesta','RF path',('DIRECT','WIDE1-1','WIDE1-1,WIDE2-1'),'DIRECT')
        self.o_table=self.combo(left,'Tabulka symbolu','Symbol table',('/','\\'),'/')
        self.o_symbol=self.field(left,'APRS symbol','APRS symbol','r',width=4)
        tools=tk.Frame(left,bg=PANEL)
        tools.pack(fill='x',pady=12)
        self.button(tools,'Vyslat LIVE','Transmit LIVE',lambda:self.send_object(True),kind='primary').pack(side='left',padx=2)
        self.button(tools,'Ukončit KILL','Kill object',lambda:self.send_object(False),kind='warn').pack(side='left',padx=7)
        self.label(left,'Objektový rámec jde do USB KISS TX fronty po potvrzení. '
                   'KILL vyžaduje stejný název. Vysílání kontroluj druhým rádiem.',
                   'Object frame is queued to USB KISS after confirmation. '
                   'KILL requires the same object name. Verify over the air with another radio.',
                   bg=PANEL,fg=ORANGE,wraplength=460,justify='left').pack(anchor='w',pady=12)
        self.o_status=self.field(right,'Stavový text','Status text','OK5TVR APRS online')
        self.o_status_path=self.combo(right,'RF cesta','RF path',('DIRECT','WIDE1-1','WIDE1-1,WIDE2-1'),'DIRECT')
        self.button(right,'Vyslat status','Send status',self.send_status,kind='primary').pack(anchor='w',pady=10)
        self.button(right,'Vyslat GPS pozici','Send position',self.send_position).pack(anchor='w',pady=7)
        self.label(right,'GPS pozice a symbol se nastavují v záložce iGate / DIGI.',
                   'GPS coordinates and symbol are configured in the iGate / DIGI tab.',
                   bg=PANEL,fg=MUTED,wraplength=390,justify='left').pack(anchor='w',pady=7)
        self.label(right,'Poslední objekty','Recent objects',fg=GREEN,bg=PANEL,
                   font=('Segoe UI Semibold',11)).pack(anchor='w',pady=(20,6))
        grid,self.obj_tree=self._tree(right,('UTC','Objekt','Stav','Cesta'),(175,112,70,95),height=9)
        grid.pack(fill='both',expand=True)

    def _build_config(self):
        ribbon=tk.Frame(self.config_tab,bg=BG,pady=7)
        ribbon.pack(fill='x',padx=8)
        self.button(ribbon,'Uložit veškeré nastavení','Save all settings',self.save_config,kind='primary').pack(side='left',padx=3)
        self.button(ribbon,'iGate ZAP','iGate ON',lambda:self.toggle_igate(True)).pack(side='left',padx=5)
        self.button(ribbon,'iGate VYP','iGate OFF',lambda:self.toggle_igate(False)).pack(side='left',padx=3)
        self.button(ribbon,'DIGI ZAP','DIGI ON',lambda:self.toggle_digi(True),kind='warn').pack(side='left',padx=10)
        self.button(ribbon,'DIGI VYP','DIGI OFF',lambda:self.toggle_digi(False)).pack(side='left',padx=3)
        self.label(ribbon,'Po změně konfigurace znovu zapni iGate/DIGI.',
                   'After changing settings, restart iGate/DIGI.',fg=MUTED).pack(side='right')
        columns=tk.Frame(self.config_tab,bg=BG)
        columns.pack(fill='both',expand=True,padx=7,pady=4)
        ig=self.pane(columns,'iGate / APRS-IS','iGate / APRS-IS')
        ig.pack(side='left',fill='both',expand=True,padx=4)
        dg=self.pane(columns,'DIGI / RF','DIGI / RF')
        dg.pack(side='left',fill='both',expand=True,padx=4)
        ps=self.pane(columns,'Vlastní GPS / majáky','Own GPS / beacons')
        ps.pack(side='left',fill='both',expand=True,padx=4)
        self.i_call=self.field(ig,'Značka iGate','iGate callsign')
        self.i_host=self.field(ig,'APRS-IS server','APRS-IS server')
        self.i_port=self.field(ig,'TCP port','TCP port')
        self.i_pass=self.field(ig,'Passcode (změna)','Passcode (change)',secret=True)
        self.i_table=self.combo(ig,'Tabulka symbolu','Symbol table',('/','\\'),'\\')
        self.i_symbol=self.field(ig,'Symbol','Symbol')
        self.i_overlay=self.field(ig,'Overlay (A–Z,0–9)','Overlay (A–Z,0–9)')
        self.i_autostart=self.check(ig,'Automaticky zapnout iGate','Autostart iGate')
        self.i_state=tk.StringVar(value='iGate: off')
        self.label(ig,'','',textvariable=self.i_state,bg=PANEL,fg=GREEN,wraplength=320).pack(anchor='w',pady=11)
        self.d_call=self.field(dg,'Značka DIGI','DIGI callsign')
        self.d_mode=self.combo(dg,'Režim DIGI','DIGI mode',('fill','regional'),'fill')
        self.d_trace=self.check(dg,'Povolit TRACE','Enable TRACE')
        self.d_delay=self.field(dg,'Odklad (s)','Delay (s)')
        self.d_limit=self.field(dg,'Max TX / min','Max TX / min')
        self.d_gap=self.field(dg,'Min. TX odstup (s)','Min. TX gap (s)')
        self.d_table=self.combo(dg,'Tabulka symbolu','Symbol table',('/','\\'),'\\')
        self.d_symbol=self.field(dg,'Symbol','Symbol')
        self.d_overlay=self.field(dg,'Overlay','Overlay')
        self.d_autostart=self.check(dg,'Automatické spuštění DIGI (RF)','Autostart DIGI (RF)')
        self.d_state=tk.StringVar(value='DIGI: off')
        self.label(dg,'','',textvariable=self.d_state,bg=PANEL,fg=GREEN,wraplength=320).pack(anchor='w',pady=11)
        self.p_lat=self.field(ps,'Zem. šířka','Latitude')
        self.p_lon=self.field(ps,'Zem. délka','Longitude')
        self.p_comment=self.field(ps,'Komentář','Comment')
        self.p_beacon=self.check(ps,'GPS maják iGate na APRS-IS','iGate GPS beacon on APRS-IS')
        self.p_interval=self.combo(ps,'Interval (min)','Interval (min)',('30','60','120'),'30')
        self.d_beacon=self.check(ps,'GPS maják DIGI na APRS-IS','DIGI GPS beacon on APRS-IS')
        self.d_beacon_comment=self.field(ps,'Komentář DIGI','DIGI comment')
        self.d_beacon_interval=self.combo(ps,'DIGI interval (min)','DIGI interval (min)',('30','60','120'),'30')
        self.label(ps,'APRS-IS je jednosměrná RF → IS; automatické IS → RF není zapnuté.',
                   'APRS-IS is receive-only RF → IS; automatic IS → RF is not enabled.',
                   bg=PANEL,fg=ORANGE,wraplength=320,justify='left').pack(anchor='w',pady=(10,2))

    def _build_telemetry(self):
        left=self.pane(self.telemetry_tab,'Odesílání telemetrie APRS T#','Sending APRS T# telemetry')
        left.pack(fill='x',padx=12,pady=(12,7))
        self.t_igate=self.check(left,'iGate telemetrie → APRS-IS','iGate telemetry → APRS-IS')
        self.t_digi=self.check(left,'DIGI telemetrie','DIGI telemetry')
        self.t_transport=self.combo(left,'DIGI transport','DIGI transport',('is','rf'),'is')
        self.t_rfpath=self.combo(left,'DIGI RF cesta','DIGI RF path',('DIRECT','WIDE1-1'),'DIRECT')
        self.t_interval=self.combo(left,'Každých (min)','Report every (min)',('15','30','60'),'15')
        row=tk.Frame(left,bg=PANEL)
        row.pack(fill='x',pady=8)
        self.button(row,'Uložit telemetrii','Save telemetry',self.save_telemetry,kind='primary').pack(side='left',padx=3)
        self.button(row,'Vyslat nyní','Send now',self.telemetry_now,kind='warn').pack(side='left',padx=8)
        self.label(row,'15minutové okno · RF DIGI metadata mohou znamenat 5 rámců',
                   'Rolling 15 minutes · RF DIGI metadata may require 5 frames',
                   bg=PANEL,fg=ORANGE).pack(side='left',padx=12)
        meters=self.pane(self.telemetry_tab,'Statistiky za posledních 15 minut','Statistics for the last 15 minutes')
        meters.pack(fill='both',expand=True,padx=12,pady=8)
        self.telemetry_text=tk.Text(meters,bg=PANEL,fg=FG,insertbackground=FG,
                                    relief='flat',font=('Consolas',12),state='disabled',height=15)
        self.telemetry_text.pack(fill='both',expand=True)

    def _build_diagnostics(self):
        metrics=tk.Frame(self.diagnostics_tab,bg=PANEL,padx=12,pady=9)
        metrics.pack(fill='x',padx=8,pady=7)
        self.diag_text=tk.StringVar(value='')
        self.label(metrics,'','',textvariable=self.diag_text,bg=PANEL,fg=GREEN,
                   justify='left',wraplength=1150).pack(anchor='w')
        actions=tk.Frame(self.diagnostics_tab,bg=BG)
        actions.pack(fill='x',padx=8,pady=4)
        self.journal_filter=tk.StringVar(value='ALL')
        self.label(actions,'Filtr deníku','Journal filter',fg=MUTED).pack(side='left',padx=3)
        ttk.Combobox(actions,textvariable=self.journal_filter,values=(
            'ALL','RX','TX','USB','IGATE','DIGI','TELEM','OBJECT','STATUS','POSITION','CONFIG','KISS'),
            state='readonly',width=12,style='APRS.TCombobox').pack(side='left',padx=4)
        self.button(actions,'Obnovit','Refresh',lambda:self._refresh(force=True)).pack(side='left',padx=4)
        self.button(actions,'Export CSV','Export CSV',self.export_journal_csv).pack(side='left',padx=4)
        self.button(actions,'Záloha JSON','Backup JSON',self.backup_config).pack(side='right',padx=3)
        self.button(actions,'Obnova JSON','Restore JSON',self.restore_config,kind='warn').pack(side='right',padx=3)
        grid,self.journal_tree=self._tree(self.diagnostics_tab,
                     ('UTC','Kategorie','Výsledek','Zdroj','Cíl','Detail'),
                     (190,95,115,115,115,590),height=19)
        grid.pack(fill='both',expand=True,padx=8,pady=5)
        bottom=self.pane(self.diagnostics_tab,'Diagnostika příjmu APRS zpráv','APRS message RX diagnostics')
        bottom.pack(fill='x',padx=8,pady=(5,8))
        self.heard_var=tk.StringVar(value='')
        self.label(bottom,'','',textvariable=self.heard_var,bg=PANEL,fg=MUTED,
                   justify='left',wraplength=1200).pack(anchor='w')

    def _load_config(self):
        c=self.config.data
        i,d,p,m,t=c['igate'],c['digi'],c['position'],c['messages'],c['telemetry']
        vals=[
            (self.port,c['serial']['port']),
            (self.i_call,i['call']), (self.i_host,i['host']), (self.i_port,i['port']),
            (self.i_table,i['symbol_table']), (self.i_symbol,i['symbol']), (self.i_overlay,i['overlay']),
            (self.d_call,d['call']), (self.d_mode,d['mode']), (self.d_delay,d['delay_s']),
            (self.d_limit,d['max_per_min']), (self.d_gap,d['min_gap_s']),
            (self.d_table,d['symbol_table']), (self.d_symbol,d['symbol']), (self.d_overlay,d['overlay']),
            (self.p_lat,p['latitude'] if p['latitude'] is not None else ''),
            (self.p_lon,p['longitude'] if p['longitude'] is not None else ''),
            (self.p_comment,p['comment']), (self.p_interval,p['beacon_interval']),
            (self.d_beacon_interval,d['beacon_interval']), (self.d_beacon_comment,d['beacon_comment']),
            (self.m_target,m['target']), (self.m_path,m['path'] or 'DIRECT'),
            (self.m_aliases,', '.join(m['receive_aliases'])),
            (self.t_transport,d['telemetry_transport']), (self.t_rfpath,d['telemetry_rf_path'] or 'DIRECT'),
            (self.t_interval,t['interval_minutes'])]
        for var,value in vals:var.set(str(value))
        for var,value in (
            (self.i_autostart,i['autostart']),(self.d_autostart,d['autostart']),
            (self.d_trace,d['trace']),(self.p_beacon,p['beacon_enabled']),
            (self.d_beacon,d['beacon_enabled']),(self.m_autoack,m['auto_ack']),
            (self.t_igate,i['telemetry_enabled']),(self.t_digi,d['telemetry_enabled'])):
            var.set(value)
        self.i_pass.set('')  # credentials never echoed back into the GUI
        if p['latitude'] is not None and p['longitude'] is not None:
            self.native_map.reset(p['latitude'],p['longitude'])

    def refresh_ports(self):
        try:
            from serial.tools import list_ports
            options=['auto']+[p.device for p in list_ports.comports()]
        except ImportError:
            options=['auto']
        chosen=self.port.get()
        if chosen and chosen not in options:options.append(chosen)
        self.port_combo.configure(values=options)

    def _act(self,action,payload=None,callback=None,quiet=False):
        if not self.service.running:
            messagebox.showwarning('OK5TVR APRS',self.t('APRS backend není spuštěný.',
                                                      'APRS backend is not running.'))
            return
        def work():
            try:
                result=self.service.command(action,payload or {})
                self.responses.put((True,result,callback,quiet))
            except (OSError,ValueError,TimeoutError,RuntimeError) as exc:
                self.responses.put((False,str(exc),None,False))
        threading.Thread(target=work,name=f'GUI command {action}',daemon=True).start()

    def _poll(self):
        if self._closing:return
        for _ in range(30):
            try:success,value,callback,quiet=self.responses.get_nowait()
            except queue.Empty:break
            if success:
                if callback:
                    try:callback(value)
                    except (OSError,ValueError,tk.TclError) as exc:
                        messagebox.showerror('OK5TVR APRS',str(exc))
                elif not quiet:
                    messagebox.showinfo('OK5TVR APRS',str(value))
            else:
                messagebox.showerror('OK5TVR APRS',str(value))
        try:self._refresh()
        except (OSError,ValueError,TypeError,tk.TclError) as exc:
            self.status.set(f'UI: {exc}')
        self.root.after(1200,self._poll)

    def _refresh(self,force=False):
        if self._closing:return
        state=self.service.state.snapshot()
        diag=self.service.diagnostics_snapshot()
        radio=state['rf_status']
        gate=state['igate_status']
        dig=diag['digi']
        self.status.set(f'USB: {radio}   │   APRS-IS: {gate}   │   DIGI: '
                        + (self.t('Zapnuto','On') if dig.get('enabled') else self.t('Vypnuto','Off')))
        self.monitor_counters.set(f"RX: {state['rx']}   TX: {state['tx_requests']}   "
                                  f"DIGI: {dig.get('tx_written',0)}   APRS-IS: {state['igate_sent']}   "
                                  f"KISS error: {diag['counters'].get('invalid',0)}")
        self.i_state.set(f"iGate: {gate}")
        self.d_state.set(f"DIGI: {self.t('Zapnuto','On') if dig.get('enabled') else self.t('Vypnuto','Off')}"
                         f" · TX {dig.get('tx_written',0)} · pending {dig.get('pending',0)}")
        selected=self.notebook.select()
        if selected==str(self.monitor) or force:
            self._refresh_rx(state,force)
        if selected==str(self.map_tab):
            self._refresh_map(state,force)
        if selected==str(self.messages_tab):
            self._refresh_messages(force)
        if selected==str(self.objects_tab):
            self._refresh_objects(diag)
        if selected==str(self.telemetry_tab):
            self._refresh_telemetry(diag)
        if selected==str(self.diagnostics_tab):
            self._refresh_diagnostics(diag,force)

    def _refresh_rx(self,state,force):
        signature=(state['rx'],state['demo'])
        if not force and self.last_rx==signature:return
        self.last_rx=signature
        old=self.rx_tree.focus()
        self.rx_tree.delete(*self.rx_tree.get_children())
        history=state['history']
        for n,row in enumerate(history):
            self.rx_tree.insert('', 'end', iid=str(n),values=(
                row['time'],row['source'],row['destination'],row['path'],
                row['kind'],row['summary'][:170]))
        self._rx_current=history
        if old in self.rx_tree.get_children():
            self.rx_tree.selection_set(old)

    def select_rx(self,_event=None):
        selected=self.rx_tree.selection()
        if not selected:return
        row=self._rx_current[int(selected[0])]
        content=(f"{row['time']}  {row['source']} > {row['destination']}  {row['path']}\n"
                 f"{row['kind']}: {row['summary']}\n"
                 f"{row.get('payload','')}\nHEX: {row.get('hex_data','')}")
        self.rx_details.configure(state='normal')
        self.rx_details.delete('1.0','end')
        self.rx_details.insert('1.0',content)
        self.rx_details.configure(state='disabled')

    def _refresh_map(self,state,force):
        stations=state['stations']
        stamp=(state['rx'],len(stations),state.get('position_count'))
        if not force and getattr(self,'_map_stamp',None)==stamp:return
        self._map_stamp=stamp
        self.native_map.set_data(stations,state.get('own_position'),state.get('digi_position'))
        self.map_description.set(self.t('Stanice: ','Stations: ')+str(len(stations))+
                                 self.t(' · s GPS: ',' · with GPS: ')+str(state['position_count']))
        self.station_tree.delete(*self.station_tree.get_children())
        self._map_rows=sorted(stations,key=lambda s:s['last'],reverse=True)
        for n,station in enumerate(self._map_rows[:240]):
            coords='GPS' if station['lat'] is not None else '—'
            self.station_tree.insert('','end',iid=str(n),values=(station['call'],station['count'],coords))

    def center_map(self):
        p=self.config.data['position']
        if p['latitude'] is not None:
            self.native_map.reset(p['latitude'],p['longitude'])
        else:
            self.native_map.reset(49.7384,13.3736)

    def _display_station(self,s):
        lat,lon=s.get('lat'),s.get('lon')
        self.map_selected.set(f"{s.get('call','')} · {s.get('kind','')}\n"
                              f"{lat}, {lon}\n{s.get('summary','')}")
        if lat is not None and lon is not None:
            self.native_map.center_lat=float(lat)
            self.native_map.center_lon=float(lon)
            self.native_map.redraw_later()

    def pin_selected(self,station):
        self._display_station(station)

    def select_station(self,_event=None):
        item=self.station_tree.selection()
        if not item:return
        idx=int(item[0])
        if idx<len(self._map_rows):self._display_station(self._map_rows[idx])

    def _refresh_messages(self,force):
        snapshot=self.service.messages_snapshot()
        self.current_inbox=snapshot['inbox']
        self.current_outbox=snapshot['outbox']
        serial=(tuple((r['id'],r['duplicates'],r['ack_sent']) for r in snapshot['inbox']),
                tuple((r['id'],r['status'],r['attempts'],r['last_error']) for r in snapshot['outbox']))
        self.msg_overview.set('RX → '+', '.join(snapshot.get('receive_calls',[]))+
                              f"   │   Inbox {snapshot['stats']['inbox']} · "
                              f"Outbox {snapshot['stats']['outbox']} · "
                              f"Pending {snapshot['stats']['pending']}")
        if force or self.last_msg!=serial:
            self.last_msg=serial
            self.in_tree.delete(*self.in_tree.get_children())
            self.out_tree.delete(*self.out_tree.get_children())
            for row in snapshot['inbox']:
                self.in_tree.insert('','end',iid=str(row['id']),values=(
                    row['arrived_at'],row['sender'],row['recipient'],row['text'],row['message_id'] or ''))
            for row in snapshot['outbox']:
                self.out_tree.insert('','end',iid=str(row['id']),values=(
                    row['created_at'],row['recipient'],row['text'],row['status'],
                    f"{row['attempts']}/{row['max_attempts']}",row['message_id']))
        heard=snapshot.get('heard_messages',[])
        if heard:
            lines=[f"{row.get('time','')}  {row.get('sender','')} → {row.get('recipient','')} "
                   f"[{row.get('result','')}] {row.get('note','')}" for row in heard[:3]]
            self.msg_diagnostics.set('\n'.join(lines))
        else:
            self.msg_diagnostics.set(self.t('Žádná zpráva zachycená přes RF KISS.',
                                            'No message frames heard via RF KISS.'))

    def _refresh_objects(self,diag):
        self.obj_tree.delete(*self.obj_tree.get_children())
        for row in diag.get('recent_objects',[])[:32]:
            self.obj_tree.insert('','end',values=(row.get('queued_utc',''),
                row['name'],'LIVE' if row['alive'] else 'KILL',row['path']))

    def _refresh_telemetry(self,diag):
        t=diag['telemetry']
        metrics=[
            (self.t('Okno','Window'),'15 min'),
            (self.t('Přijaté pakety RX','Received RX packets'),t['rx_packets']),
            (self.t('Odeslané do USB TX','Written to USB TX'),t['tx_packets']),
            (self.t('Unikátní stanice','Unique stations'),t['unique_stations']),
            (self.t('Stanice se souřadnicemi','Stations with GPS'),t['positioned_stations']),
            (self.t('Průměrná vzdálenost (km)','Average distance (km)'),t['avg_distance_km']),
            (self.t('Max. vzdálenost (km)','Max. distance (km)'),t['dx_max_km']),
            (self.t('DX značka','DX callsign'),t['dx_callsign']),
            (self.t('Předané iGate → APRS-IS','Forwarded RF → APRS-IS'),t['igate_forwarded']),
            (self.t('DIGI opakování TX','DIGI repeated TX'),t['digi_tx']),
            (self.t('RX paketů / min','RX packets / min'),t['rx_per_min']),
            (self.t('TX paketů / min','TX packets / min'),t['tx_per_min']),
            (self.t('Chyby USB TX','USB TX errors'),t['tx_errors']),
            (self.t('Ztracené vzorky','Dropped samples'),t['dropped_samples']),
        ]
        text='\n'.join(f'{name:<36} {value if value is not None else "—"}' for name,value in metrics)
        text+='\n\n'+self.t('GPS vzdálenost je vypočtená ze zaslaných poloh, ne zjištěný RF dosah.',
                               'GPS distance is calculated from reported positions, not measured RF range.')
        self.telemetry_text.configure(state='normal')
        self.telemetry_text.delete('1.0','end')
        self.telemetry_text.insert('1.0',text)
        self.telemetry_text.configure(state='disabled')

    def _refresh_diagnostics(self,diag,force):
        status=(self.t('USB připojeno','USB connected') if diag['radio_connected'] else
                self.t('USB odpojeno','USB disconnected'))
        self.diag_text.set(
            f"{status} · {diag['usb_port']} · "
            f"{self.t('Připojení','Connections')}: {diag['usb_connections']}\n"
            f"{self.t('Poslední RF rámec','Last RF frame')}: {diag['last_rf_frame_utc'] or '—'} · "
            f"{self.t('APRS-IS online','APRS-IS online')}: {diag['igate_connected']} · "
            f"{self.t('DIGI zapnuto','DIGI enabled')}: {diag['digi'].get('enabled')}\n"
            f"USB: {diag['last_usb_error'] or 'OK'} · APRS-IS: {diag['igate_last_error'] or 'OK'} · "
            f"{self.t('Doba běhu','Uptime')}: {diag['uptime_s']} s")
        category=self.journal_filter.get()
        journal=self.service.journal_snapshot(150,'' if category=='ALL' else category)
        stamp=(category,journal[0]['id'] if journal else None,len(journal))
        if force or stamp!=self.last_journal:
            self.last_journal=stamp
            self.journal_tree.delete(*self.journal_tree.get_children())
            for entry in journal:
                self.journal_tree.insert('','end',values=(entry['utc'],entry['category'],
                    entry['outcome'],entry['source'],entry['target'],entry['detail']))
        heard=self.service.messages.snapshot().get('heard_messages',[])
        self.heard_var.set('\n'.join(
            f"{r['time']}  {r['sender']} → {r['recipient']}  [{r['result']}] {r['note']}"
            for r in heard[:4]) or self.t('Zatím žádné adresované zprávy zachycené přes RF.',
                                         'No addressed message frames heard over RF yet.'))

    @staticmethod
    def _as_int(value,default=None):
        return int(value) if str(value).strip() else default

    @staticmethod
    def _as_float(value,default=None):
        return float(value.replace(',','.')) if str(value).strip() else default

    def _confirm(self,cs,en):
        return messagebox.askyesno('OK5TVR APRS',self.t(cs,en),parent=self.root)

    def serial_connect(self):
        port=self.port.get().strip()
        if not port:
            messagebox.showwarning('OK5TVR APRS',self.t('Vyber COM port.','Select a COM port.'))
            return
        def reconnect(_):self._act('serial_reconnect',{})
        if port != self.config.data['serial']['port']:
            self._act('save',{'config':{'serial':{'port':port}}},callback=reconnect)
        else:
            reconnect(None)

    def test_tx(self):
        if self._confirm('Odeslat JEDEN testovací APRS status přes USB KISS TNC a RF?',
                         'Transmit ONE test APRS status over USB KISS TNC and RF?'):
            self._act('tx_test',{'confirm':True})

    def export_rx_csv(self):
        path=filedialog.asksaveasfilename(parent=self.root,title='RX APRS CSV',
                                         defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        try:
            rows=self.service.state.snapshot()['history']
            with open(path,'w',newline='',encoding='utf-8-sig') as out:
                writer=csv.writer(out,delimiter=';')
                writer.writerow(['UTC','Source','Destination','Path','Type','Summary','Payload','Hex'])
                for r in reversed(rows):
                    writer.writerow([r.get(k,'') for k in ('time','source','destination','path',
                                                           'kind','summary','payload','hex_data')])
        except OSError as exc:
            messagebox.showerror('CSV',str(exc))

    def send_message(self):
        text=self.m_body.get().strip()
        call=self.m_target.get().strip().upper()
        if not call or not text:
            messagebox.showwarning('APRS',self.t('Vyplň cílovou značku a text.',
                                                 'Enter recipient callsign and message.'))
            return
        if not self._confirm(f'Odeslat APRS zprávu přes RF na {call}? '
                             'Zpráva je veřejná a může se opakovat do ACK.',
                             f'Send APRS message over RF to {call}? '
                             'Messages are public and may be retried until ACK.'):
            return
        def done(value):
            self.m_body.set('')
            messagebox.showinfo('APRS',str(value))
            self._refresh(force=True)
        self._act('message_send',{'target':call,'text':text,
                                  'path':self.m_path.get(),'confirm':True},callback=done)

    def _selected_message_id(self,tree):
        selected=tree.selection()
        if selected:return int(selected[0])
        messagebox.showwarning('APRS',self.t('Nejprve vyber zprávu v tabulce.',
                                             'Select a message in the table first.'))
        return None

    def ack_message(self,reject=False):
        number=self._selected_message_id(self.in_tree)
        if number is None:return
        kind='REJ' if reject else 'ACK'
        if self._confirm(f'Odeslat jednorázové {kind} přes RF?',
                         f'Transmit one {kind} response via RF?'):
            self._act('message_rej' if reject else 'message_ack',
                      {'id':number,'confirm':True})

    def reply_message(self):
        number=self._selected_message_id(self.in_tree)
        if number is None:return
        for row in self.current_inbox:
            if row['id']==number:
                self.m_target.set(row['sender'])
                self.m_body.set('')
                return

    def cancel_message(self):
        number=self._selected_message_id(self.out_tree)
        if number is not None:
            self._act('message_cancel',{'id':number})

    def save_message_settings(self):
        aliases=[s.strip().upper() for s in self.m_aliases.get().replace(';',',').split(',') if s.strip()]
        ack=self.m_autoack.get()
        if ack and not self._confirm('Zapnout automatické vysílání ACK při příjmu zpráv? '
                                      'Tato volba zůstane aktivní i po restartu.',
                                      'Enable automatic RF ACK for received messages? '
                                      'This option persists after restart.'):
            return
        cfg={'messages':{'target':self.m_target.get().strip().upper(),
                         'path':self.m_path.get(),
                         'receive_aliases':aliases,'auto_ack':ack}}
        self._act('save',{'config':cfg,'confirm_auto_ack':ack})

    def send_object(self,alive):
        action='LIVE' if alive else 'KILL'
        if not self._confirm(f'Odeslat JEDEN objekt {action} přes RF? '
                             'Při KILL musí být stejný název jako u objektu LIVE.',
                             f'Transmit ONE {action} object over RF? '
                             'KILL must use the original LIVE object name.'):
            return
        req={'confirm':True,'name':self.o_name.get(),'lat':self.o_lat.get(),
             'lon':self.o_lon.get(),'comment':self.o_comment.get(),
             'path':self.o_path.get(),'symbol_table':self.o_table.get(),
             'symbol':self.o_symbol.get(),'alive':alive}
        self._act('object_send',req)

    def send_status(self):
        if self._confirm('Odeslat jeden APRS status přes RF?',
                         'Transmit one APRS status over RF?'):
            self._act('status_send',{'confirm':True,'text':self.o_status.get(),
                                     'path':self.o_status_path.get()})

    def send_position(self):
        if self._confirm('Odeslat jednu vlastní APRS GPS pozici přes RF? '
                         'Souřadnice jsou veřejné.',
                         'Transmit one own APRS GPS position over RF? '
                         'Coordinates are public.'):
            self._act('position_send',{'confirm':True,'path':self.o_status_path.get()})

    def save_config(self):
        try:
            latitude=self._as_float(self.p_lat.get())
            longitude=self._as_float(self.p_lon.get())
            data={
                'serial':{'port':self.port.get().strip()},
                'igate':{'call':self.i_call.get().strip().upper(),
                         'host':self.i_host.get().strip(),
                         'port':self._as_int(self.i_port.get()),
                         'symbol_table':self.i_table.get(),
                         'symbol':self.i_symbol.get().strip(),
                         'overlay':self.i_overlay.get().strip().upper(),
                         'autostart':self.i_autostart.get()},
                'digi':{'call':self.d_call.get().strip().upper(),
                        'mode':self.d_mode.get(),
                        'trace':self.d_trace.get(),
                        'delay_s':self._as_float(self.d_delay.get()),
                        'max_per_min':self._as_int(self.d_limit.get()),
                        'min_gap_s':self._as_float(self.d_gap.get()),
                        'symbol_table':self.d_table.get(),
                        'symbol':self.d_symbol.get().strip(),
                        'overlay':self.d_overlay.get().strip().upper(),
                        'autostart':self.d_autostart.get(),
                        'beacon_enabled':self.d_beacon.get(),
                        'beacon_interval':int(self.d_beacon_interval.get()),
                        'beacon_comment':self.d_beacon_comment.get()},
                'position':{'latitude':latitude,'longitude':longitude,
                            'comment':self.p_comment.get(),
                            'beacon_enabled':self.p_beacon.get(),
                            'beacon_interval':int(self.p_interval.get())}}
        except (ValueError,TypeError) as exc:
            messagebox.showerror('OK5TVR APRS',str(exc))
            return
        if self.d_autostart.get():
            if not self._confirm('Opravdu povolit automatický DIGI RF TX po startu? '
                                 'Po zapnutí rádia v KISS režimu může začít opakovat rámce.',
                                 'Really enable automatic DIGI RF TX after startup? '
                                 'When KISS connects it may retransmit frames.'):
                return
        if self.i_autostart.get():
            if not self._confirm('Povolit automatické předávání RF paketů na APRS-IS po startu?',
                                 'Enable automatic RF-to-APRS-IS forwarding after startup?'):
                return
        payload={'config':data,'confirm_auto_tx':self.d_autostart.get(),
                 'confirm_rf_telemetry':self.config.data['digi']['telemetry_enabled'] and
                                          self.config.data['digi']['telemetry_transport']=='rf'}
        if self.i_pass.get().strip():payload['passcode']=self.i_pass.get().strip()
        def done(result):
            self.i_pass.set('')
            messagebox.showinfo('OK5TVR APRS',result)
        self._act('save',payload,callback=done)

    def toggle_igate(self,enable):
        if enable:
            if not self._confirm('Spustit jednosměrnou iGate RF → APRS-IS?',
                                 'Start one-way RF → APRS-IS iGate?'):
                return
        self._act('igate_on' if enable else 'igate_off',{'confirm':enable})

    def toggle_digi(self,enable):
        if enable:
            if not self._confirm('Zapnout automatický DIGI RF TX? '
                                 'Interní DIGI v UV-K1 musí být vypnuto. '
                                 'Vysílání je veřejné a může zatěžovat APRS kanál.',
                                 'Enable automatic DIGI RF TX? '
                                 'Disable radio-internal DIGI first. '
                                 'Retransmissions use the shared APRS channel.'):
                return
        self._act('digi_on' if enable else 'digi_off',{'confirm':enable})

    def save_telemetry(self):
        rf=self.t_digi.get() and self.t_transport.get()=='rf'
        if rf and not self._confirm('Opravdu povolit RF DIGI telemetrii? '
                                     'T# a metadata mohou vyslat až 5 rámců. '
                                     'Výchozí cesta DIRECT minimalizuje zatížení kanálu.',
                                     'Enable DIGI telemetry over RF? '
                                     'A telemetry report plus metadata can transmit up to 5 frames. '
                                     'DIRECT path minimizes channel load.'):
            return
        options={'igate':{'telemetry_enabled':self.t_igate.get()},
                 'digi':{'telemetry_enabled':self.t_digi.get(),
                         'telemetry_transport':self.t_transport.get(),
                         'telemetry_rf_path':self.t_rfpath.get()},
                 'telemetry':{'interval_minutes':int(self.t_interval.get())}}
        self._act('save',{'config':options,'confirm_rf_telemetry':rf})

    def telemetry_now(self):
        if self._confirm('Odeslat jednu telemetrickou sadu přes nastavený transport? '
                         'Při DIGI RF může jít o několik rámců.',
                         'Send a telemetry report using configured transport? '
                         'DIGI RF may transmit several frames.'):
            self._act('telemetry_send_now',{'confirm':True})

    def export_journal_csv(self):
        path=filedialog.asksaveasfilename(parent=self.root,title='OK5TVR APRS journal',
                                         defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if not path:return
        try:
            category=self.journal_filter.get()
            journal=self.service.journal_snapshot(500,'' if category=='ALL' else category)
            with open(path,'w',encoding='utf-8-sig',newline='') as out:
                writer=csv.writer(out,delimiter=';')
                writer.writerow(('UTC','Category','Outcome','Source','Target','Detail'))
                for r in reversed(journal):
                    writer.writerow([r.get(k,'') for k in ('utc','category','outcome','source','target','detail')])
        except (OSError,ValueError) as exc:messagebox.showerror('CSV',str(exc))

    def backup_config(self):
        path=filedialog.asksaveasfilename(parent=self.root,title='OK5TVR APRS backup',
                    defaultextension='.json',filetypes=[('JSON','*.json')],initialfile='OK5TVR_config_backup.json')
        if not path:return
        try:
            data=self.service.config_backup()
            with open(path,'w',encoding='utf-8') as file:
                json.dump(data,file,ensure_ascii=False,indent=2)
            messagebox.showinfo('OK5TVR APRS',self.t('Záloha uložena bez hesel a tokenů.',
                                                    'Backup saved without passwords or tokens.'))
        except (OSError,ValueError) as exc:messagebox.showerror('OK5TVR APRS',str(exc))

    def restore_config(self):
        path=filedialog.askopenfilename(parent=self.root,title='OK5TVR APRS restore',
                                        filetypes=[('JSON','*.json')])
        if not path:return
        try:
            doc=json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError,ValueError) as exc:
            messagebox.showerror('OK5TVR APRS',str(exc));return
        if not self._confirm('Obnovit nastavení? Všechny automatické RF TX, '
                             'iGate a automatické ACK budou vypnuty. Hesla zůstanou zachována.',
                             'Restore configuration? Automatic RF TX, iGate and ACK will be disabled. '
                             'Existing credentials will be preserved.'):
            return
        def done(result):
            self._load_config()
            messagebox.showinfo('OK5TVR APRS',str(result))
        self._act('restore_config',{'backup':doc,'confirm':True},callback=done)

    def close(self):
        if self._closing:return
        self._closing=True
        self.service.stop.set()
        # Allow SQLite/journal to flush; do not hang forever on a broken USB/TCP driver.
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2.5)
        self.root.destroy()


def main():
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s')
    root=tk.Tk()
    DesktopApp(root)
    root.mainloop()


if __name__=='__main__':
    main()
