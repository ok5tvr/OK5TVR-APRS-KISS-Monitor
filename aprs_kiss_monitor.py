#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""OK5TVR APRS KISS Monitor 1.3 - APRS map, TX, IS beacon and APRS DIGI.

Target: Quansheng UV-K1(8) with F4HWN Labs KISS TNC (v6.3.0+).
Requires: Python 3.9+, tkinter, pyserial. DIGI, IGate and TX OFF by default.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from urllib.request import urlopen
import queue
import re
import threading
import time
import webbrowser
import weakref
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from aprs_features import (APRSISClient, MonitorState, encode_ui_packet,
                           encode_kiss_data, igate_tnc2, parse_position,
                           CALL_RE, IS_CALL_RE)
from web_panel import WebPanel, local_ipv4
from aprs_digi import DigiConfig, DigiRepeater
from desktop_locale import translate as translate_ui
from aprs_station import (aprsis_position, decimal_coordinate, maidenhead_center,
                          load_settings, save_settings)

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

APP_TITLE = "OK5TVR APRS KISS Monitor"
VERSION = "1.7.0-rc1"
FEND, FESC, TFEND, TFESC = 0xC0, 0xDB, 0xDC, 0xDD
MAX_KISS_FRAME = 4096


# Shared protocol and serial transport, also used by the headless service.
from aprs_protocol import (KissDecoder, Packet, decode_ax25, demo_ax25_packet,
                           display_bytes, parse_address, position_summary,
                           classify_aprs)
from aprs_serial import SerialReader

class App:
    BG = "#101925"
    PANEL = "#192536"
    BORDER = "#344558"
    TEXT = "#EFF5FA"
    SUB = "#A7B9C9"
    ACCENT = "#35D1B6"
    WARNING = "#FFCF83"

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_TITLE} v{VERSION}")
        self.root.geometry("1190x700")
        self.root.minsize(850, 540)
        self.root.configure(bg=self.BG)
        self.events = queue.Queue()
        self.stop_event: threading.Event | None = None
        self.reader: SerialReader | None = None
        self.session = 0
        self.active = False
        self.connecting = False
        self.closing = False
        self.frame_count = 0
        self.control_count = 0
        self.invalid_count = 0
        self.records: list[Packet] = []
        self.packet_by_row: dict[str, Packet] = {}
        self.seq = 0
        self.baud = 115200  # native USB CDC: host baud value is ignored by firmware
        self.state = MonitorState()
        self.web = WebPanel(self.state)
        self.igate_client = None
        self.tx_attempts = 0
        self.last_tx = 0.0
        self.gate_cache = {}  # (src,dst,info) -> recent time: RF duplicates not re-gated
        self.settings = load_settings()  # excludes APRS-IS passcode
        self.language = self.settings.get('ui_language', 'cs')
        if self.language not in ('cs', 'en'):
            self.language = 'cs'
        self._localized_widgets = weakref.WeakKeyDictionary()
        self._localized_windows = weakref.WeakKeyDictionary()
        self._table_titles = {}
        self._status_original = 'Nepřipojeno'
        self._detail_original = ''
        try:
            self.digi = DigiRepeater(DigiConfig(
                call=str(self.settings.get('digi_call','OK5TVR-3')).upper(),
                mode=self.settings.get('digi_mode','fill'),
                trace=bool(self.settings.get('digi_trace',False))))
        except ValueError:
            self.digi = DigiRepeater(DigiConfig(call='OK5TVR-3'))
        self.state.update_digi(self.digi.snapshot())
        self._publish_position_locally()

        self._styles()
        self._layout()
        try:
            self.web.start(lan=False)
            self.web_var.set(f"Web: {self.web.local_url()}")
        except OSError as exc:
            self.web_var.set(f"Web server nelze spustit: {exc}")
        self.refresh_ports()
        self.root.after(80, self._pump)
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

    def tr(self, value):
        return translate_ui(value, self.language)

    def _widget_text(self, widget, original):
        if original:
            self._localized_widgets[widget] = str(original)
            widget.configure(text=self.tr(original))
        return widget

    def _window_title(self, window, original):
        self._localized_windows[window] = original
        window.title(self.tr(original))

    def _message_box(self, fn, title, message, **kwargs):
        return fn(self.tr(title), self.tr(message), **kwargs)

    def set_language(self, event=None):
        chosen = 'en' if self.language_choice.get() == 'EN' else 'cs'
        if chosen == self.language:
            return
        self.language = chosen
        self.settings['ui_language'] = chosen
        try:
            save_settings(self.settings)
        except OSError:
            pass  # Still apply language for this running session.
        for widget, source in list(self._localized_widgets.items()):
            try:
                if widget.winfo_exists():
                    widget.configure(text=self.tr(source))
            except tk.TclError:
                continue
        for window, source in list(self._localized_windows.items()):
            try:
                if window.winfo_exists():
                    window.title(self.tr(source))
            except tk.TclError:
                continue
        for key, source in self._table_titles.items():
            self.table.heading(key, text=self.tr(source))
        self.status_var.set(self.tr(self._status_original))
        self._update_counters()
        if self.table.selection():
            self.on_select()
        elif self._detail_original:
            self.set_detail(self._detail_original)

    def _styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("Dark.Treeview", background=self.PANEL, fieldbackground=self.PANEL,
                        foreground=self.TEXT, borderwidth=0, rowheight=29, font=("Segoe UI", 10))
        style.configure("Dark.Treeview.Heading", background="#25374B", foreground=self.TEXT,
                        padding=(8, 9), relief="flat", font=("Segoe UI Semibold", 10))
        style.map("Dark.Treeview", background=[("selected", "#186F77")], foreground=[("selected", "#FFFFFF")])
        style.configure("Dark.TCombobox", fieldbackground="#26384B", background="#26384B",
                        foreground=self.TEXT, arrowcolor=self.TEXT)
        style.map("Dark.TCombobox", fieldbackground=[("readonly", "#26384B")],
                  foreground=[("readonly", self.TEXT)])
        style.configure("Dark.Vertical.TScrollbar", background="#2A3D52", troughcolor=self.BG,
                        bordercolor=self.BG, arrowcolor=self.TEXT)

    def _label(self, parent, text: str, size=10, color=None, weight="normal", **opts):
        font_name = "Segoe UI Semibold" if weight == "bold" else "Segoe UI"
        widget = tk.Label(parent, text=self.tr(text), bg=opts.pop("bg", self.BG), fg=color or self.TEXT,
                          font=(font_name, size), **opts)
        return self._widget_text(widget, text)

    def _btn(self, parent, text, command, primary=False, **opts):
        widget = tk.Button(parent, text=self.tr(text), command=command, padx=16, pady=8,
                           font=("Segoe UI Semibold", 10), relief="flat", bd=0,
                           fg=self.BG if primary else self.TEXT,
                           bg=self.ACCENT if primary else "#304358",
                           activebackground="#64E5D0" if primary else "#42607E",
                           cursor="hand2", **opts)
        return self._widget_text(widget, text)

    def _layout(self):
        header = tk.Frame(self.root, bg=self.BG)
        header.pack(fill="x", padx=22, pady=(17, 5))
        self._label(header, "OK5TVR", 12, self.ACCENT, "bold").pack(side="left", padx=(0, 12))
        self._label(header, "APRS KISS Monitor", 19, self.TEXT, "bold").pack(side="left")
        self.language_choice = ttk.Combobox(header, state="readonly", width=4,
                                             values=("CZ", "EN"), style="Dark.TCombobox")
        self.language_choice.set("EN" if self.language == "en" else "CZ")
        self.language_choice.pack(side="right", padx=(8, 0))
        self.language_choice.bind("<<ComboboxSelected>>", self.set_language)
        self._label(header, "Jazyk / Language", 9, self.SUB).pack(side="right")
        self._label(header, "UV-K1(8)  ·  F4HWN Labs  ·  KISS TNC", 10, self.SUB).pack(side="right", padx=(0, 16))

        controls = tk.Frame(self.root, bg=self.PANEL, padx=15, pady=13, highlightthickness=1,
                            highlightbackground=self.BORDER)
        controls.pack(fill="x", padx=22, pady=(12, 8))
        self._label(controls, "Sériový port", 10, self.SUB, bg=self.PANEL).pack(side="left", padx=(0, 9))
        self.port_choice = ttk.Combobox(controls, state="readonly", width=36, style="Dark.TCombobox")
        self.port_choice.pack(side="left", padx=(0, 8))
        self.refresh_btn = self._btn(controls, "⟳", self.refresh_ports)
        self.refresh_btn.pack(side="left", padx=(0, 10))
        self.connect_btn = self._btn(controls, "Připojit", self.toggle_connection, primary=True)
        self.connect_btn.pack(side="left", padx=(0, 10))
        self.demo_btn = self._btn(controls, "Ukázkový rámec", self.demo)
        self.demo_btn.pack(side="left", padx=(0, 10))
        self.export_btn = self._btn(controls, "Export CSV", self.export_csv)
        self.export_btn.pack(side="right")

        actions = tk.Frame(self.root, bg=self.BG)
        actions.pack(fill="x", padx=22, pady=(3, 7))
        first = tk.Frame(actions,bg=self.BG); first.pack(fill='x', pady=(0,4))
        self._btn(first, "APRS mapa / web", self.open_map, primary=True).pack(side="left", padx=(0, 8))
        self._btn(first, "Otestovat TX...", self.tx_dialog).pack(side="left", padx=(0, 8))
        self._btn(first, "iGate APRS-IS...", self.igate_dialog).pack(side="left", padx=(0, 8))
        self._btn(first, "APRS DIGI...", self.digi_dialog).pack(side="left", padx=(0, 8))
        self._btn(first, "APRS zprávy", lambda: self.open_service_page("messages")).pack(side="left", padx=(0, 8))
        self._btn(first, "APRS objekty", lambda: self.open_service_page("operations", "objects")).pack(side="left", padx=(0, 8))
        second = tk.Frame(actions,bg=self.BG); second.pack(fill='x')
        self._btn(second, "Pozice iGate / GPS...", self.position_dialog).pack(side="left", padx=(0,8))
        self._btn(second, "Web v LAN...", self.lan_dialog).pack(side="left", padx=(0, 8))
        self._btn(second, "Diagnostika", lambda: self.open_service_page("operations", "diagnostics")).pack(side="left")
        self.web_var = tk.StringVar(value="Web: startuje...")
        self._label(second,"", 9, self.SUB, textvariable=self.web_var).pack(side="right")

        banner = tk.Frame(self.root, bg=self.BG)
        banner.pack(fill="x", padx=22, pady=(5, 12))
        self.status_dot = self._label(banner, "●", 15, self.WARNING)
        self.status_dot.pack(side="left")
        self.status_var = tk.StringVar(value=self.tr("Nepřipojeno"))
        self._label(banner, "", color=self.SUB, textvariable=self.status_var).pack(side="left", padx=(7, 0))
        self.counters_var = tk.StringVar(value="Rámce: 0     Ovládací KISS: 0     Chybné: 0")
        self._label(banner, "", 10, self.SUB, textvariable=self.counters_var).pack(side="right")

        body = tk.Frame(self.root, bg=self.BG)
        body.pack(fill="both", expand=True, padx=22)
        self._label(body, "PŘIJATÉ AX.25 / APRS RÁMCE", 10, self.SUB, "bold").pack(anchor="w", pady=(0, 7))

        grid = tk.Frame(body, bg=self.PANEL, highlightbackground=self.BORDER, highlightthickness=1)
        grid.pack(fill="both", expand=True)
        fields = ("time", "source", "destination", "path", "kind", "summary")
        self.table = ttk.Treeview(grid, columns=fields, show="headings", selectmode="browse",
                                  style="Dark.Treeview")
        specs = {
            "time": ("Čas", 85, "center"),
            "source": ("Zdroj", 110, "w"),
            "destination": ("Cíl", 88, "w"),
            "path": ("Cesta", 160, "w"),
            "kind": ("Typ", 90, "w"),
            "summary": ("Obsah / dekódovaná zpráva", 425, "w"),
        }
        self._table_titles = {key: heading for key, (heading, _, _) in specs.items()}
        for key, (heading, width, align) in specs.items():
            self.table.heading(key, text=self.tr(heading))
            self.table.column(key, width=width, anchor=align, minwidth=65,
                              stretch=key == "summary")
        self.table.tag_configure("sim", foreground=self.WARNING)
        self.table.tag_configure("normal", foreground=self.TEXT)
        scroll = ttk.Scrollbar(grid, orient="vertical", command=self.table.yview,
                               style="Dark.Vertical.TScrollbar")
        self.table.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.table.pack(side="left", fill="both", expand=True)
        self.table.bind("<<TreeviewSelect>>", self.on_select)

        self._label(body, "PODROBNOSTI VYBRANÉHO RÁMCE / HEX", 10, self.SUB, "bold").pack(
            anchor="w", pady=(15, 7))
        self.detail = scrolledtext.ScrolledText(body, height=8, wrap="word", bg=self.PANEL,
                                                fg=self.TEXT, insertbackground=self.TEXT,
                                                relief="flat", padx=12, pady=10,
                                                font=("Consolas", 10), state="disabled")
        self.detail.pack(fill="x")
        self.set_detail("Zatím žádný rámec. Zapni v radiostanici KISS TNC a stiskni na ní 2 pro USB test.\n"
                        "Pro ověření programu bez stanice klikni na Ukázkový rámec.")

        footer = tk.Frame(self.root, bg=self.BG)
        footer.pack(fill="x", padx=22, pady=(10, 16))
        self._label(footer, "DIGI / iGate po startu VYPNUTY · vlastní GPS pouze APRS-IS · web pouze čte",
                    9, self.SUB).pack(side="left")
        self._label(footer, f"v{VERSION}", 9, self.SUB).pack(side="right")

    def set_detail(self, value):
        self._detail_original = value
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", self.tr(value))
        self.detail.configure(state="disabled")

    def refresh_ports(self):
        if self.active or self.connecting:
            return
        previous = self.port_choice.get()
        options = []
        if list_ports:
            options = [f"{p.device} | {p.description}" for p in sorted(list_ports.comports(),
                                                                         key=lambda p: p.device)]
        self.port_choice["values"] = options
        if previous in options:
            self.port_choice.set(previous)
        elif options:
            self.port_choice.current(0)
        else:
            self.port_choice.set("")
            self.set_status("Žádný COM port nenalezen" if list_ports else "Není nainstalován pyserial", False)

    def set_status(self, message: str, connected=False):
        self._status_original = message
        self.status_var.set(self.tr(message))
        self.status_dot.configure(fg=self.ACCENT if connected else self.WARNING)

    def toggle_connection(self):
        if self.active or self.connecting:
            self.disconnect()
        else:
            self.connect()

    def connect(self):
        choice = self.port_choice.get().strip()
        if not choice:
            self._message_box(messagebox.showwarning, APP_TITLE, "Nejprve vyber sériový port. Zkus tlačítko ⟳.")
            return
        if serial is None:
            self._message_box(messagebox.showerror, APP_TITLE, "Chybí knihovna pyserial.\nSpusť spustit.bat nebo:\npy -3 -m pip install pyserial")
            return
        port = choice.split(" | ", 1)[0]
        self.session += 1
        self.stop_event = threading.Event()
        self.reader = SerialReader(port, self.baud, self.events, self.stop_event, self.session)
        self.active = False
        self.connecting = True
        self.closing = False
        self.connect_btn.configure(text="Odpojit")
        self.set_status(f"Otevírám {port} ...")
        self.state.update_status(radio="Připojuji")
        self.reader.start()

    def disconnect(self):
        if self.reader: self.reader.digi_allowed.clear()
        self.digi.stop()
        self.state.update_digi(self.digi.snapshot())
        if self.stop_event is not None:
            self.stop_event.set()
        self.connecting = False
        self.closing = True
        self._widget_text(self.connect_btn, "Odpojuji..."); self.connect_btn.configure( state="disabled")
        self.set_status("Odpojuji sériový port ...")
        self.state.update_status(radio="Odpojuji")

    def _pump(self):
        # All widget changes run on the Tk main thread, never on the serial thread.
        for _ in range(200):
            try:
                session, event_type, value = self.events.get_nowait()
            except queue.Empty:
                break
            if session not in (self.session, -1):
                continue
            if session == -1:
                if event_type == "igate_status":
                    self.state.update_status(igate=value)
                    self.web_var.set("iGate: " + value[:65])
                elif event_type == "igate_sent":
                    self.state.note_igate(True)
                    self._update_counters()
                elif event_type == "igate_beacon":
                    self.state.note_beacon()
                    self._update_counters()
                elif event_type == "igate_error":
                    self.state.update_status(igate="Chyba: " + str(value)[:85])
                    self.web_var.set("iGate chyba: " + str(value)[:55])
                continue
            if event_type == "connected":
                self.active = True
                self.connecting = False
                self._widget_text(self.connect_btn, "Odpojit"); self.connect_btn.configure( state="normal")
                self.set_status(f"Připojeno k {value} – čekám na KISS rámce", True)
                self.state.update_status(radio="Připojeno " + value)
            elif event_type == "frame":
                self.add_packet(value)
            elif event_type == "tx_written":
                self.tx_attempts += 1
                self.state.note_tx()
                if isinstance(value,dict) and value.get('category')=='digi':
                    self.digi.mark_written()
                    self.state.update_digi(self.digi.snapshot())
                    self.set_status("DIGI: paket předán USB KISS TNC (RF ověř druhým přijímačem)",True)
                else:
                    self.set_status("TX: rámec předán USB KISS TNC (RF ověř druhým přijímačem)",True)
                self._update_counters()
            elif event_type == 'tx_cancelled':
                self.set_status(str(value),self.active)
            elif event_type == "tx_error":
                if isinstance(value,dict) and value.get('category')=='digi':
                    self.digi.mark_error()
                    self.state.update_digi(self.digi.snapshot())
                self.set_status("Chyba zápisu TX do USB: " + str(value.get('error') if isinstance(value,dict) else value))
            elif event_type == "control":
                self.control_count += 1
                self._update_counters()
            elif event_type == "invalid":
                self.invalid_count += 1
                self._update_counters()
            elif event_type == "error":
                self.set_status(f"Chyba spojení: {value}")
                self.state.update_status(radio="Chyba USB")
            elif event_type == "closed":
                if self.reader: self.reader.digi_allowed.clear()
                self.digi.stop()
                self.state.update_digi(self.digi.snapshot())
                self.active = False
                self.connecting = False
                self.closing = False
                self._widget_text(self.connect_btn, "Připojit"); self.connect_btn.configure( state="normal")
                if not self.status_var.get().startswith("Chyba"):
                    self.set_status("Odpojeno")
                self.state.update_status(radio="Odpojeno")
        self._digi_tick()
        if not self.root.winfo_exists():
            return
        self.root.after(80, self._pump)

    def _update_counters(self):
        gated = self.state.snapshot()["igate_sent"]
        digi_tx = self.digi.stats['tx_written']
        self.counters_var.set(f"RX: {self.frame_count}   TX: {self.tx_attempts}   DIGI: {digi_tx}"
                              f"   →IS: {gated}   KISS: {self.control_count}   {self.tr('Chybné')}: {self.invalid_count}")

    def _digi_tick(self):
        if not self.digi.enabled or not self.active or self.reader is None:
            return
        pending=self.digi.ready()
        if pending is not None:
            try:
                wire=encode_kiss_data(pending.raw)
            except ValueError:
                return
            if self.reader.send(wire, category='digi'):
                self.digi.mark_queued(pending.signature)
                self.state.update_digi(self.digi.snapshot())
                self._update_counters()

    def add_packet(self, packet: Packet):
        if not packet.simulated and self.digi.enabled and packet.raw_ax25:
            self.digi.receive(packet.raw_ax25)
            self.state.update_digi(self.digi.snapshot())
        self.state.add(packet)
        if not packet.simulated and self.igate_client is not None and self.igate_client.connected.is_set():
            line, reason = igate_tnc2(packet, self.igate_client.call)
            if line:
                now = time.monotonic()
                key = (packet.source, packet.destination, packet.raw_info)
                recent = self.gate_cache.get(key, 0.0)
                if now - recent > 30.0:
                    if self.igate_client.enqueue(line):
                        self.gate_cache[key] = now
                    else:
                        self.state.note_igate(False)
                # Avoid unbounded dictionary size after days of operation.
                if len(self.gate_cache) > 4000:
                    self.gate_cache = {k:t for k,t in self.gate_cache.items() if now-t < 60}
        self.frame_count += 1
        self._update_counters()
        self.records.append(packet)
        if len(self.records) > 20000:
            self.records.pop(0)
        self.seq += 1
        row_id = str(self.seq)
        self.packet_by_row[row_id] = packet
        timestamp = packet.timestamp[11:]
        if packet.simulated:
            timestamp = "DEMO " + timestamp
        self.table.insert("", "end", iid=row_id, tags=("sim" if packet.simulated else "normal",),
                          values=(timestamp, packet.source, packet.destination,
                                  packet.path, packet.kind, packet.summary))
        # Keep visible log responsive while retaining up to 20k records for CSV.
        if len(self.table.get_children()) > 1500:
            old_row = self.table.get_children()[0]
            self.table.delete(old_row)
            self.packet_by_row.pop(old_row, None)
        self.table.see(row_id)
        if not self.table.selection():
            self.table.selection_set(row_id)
            self.on_select()

    def on_select(self, _event=None):
        selection = self.table.selection()
        if not selection:
            return
        packet = self.packet_by_row.get(selection[0])
        if packet is None:
            return
        source = self.tr("SIMULACE – NEPŘIŠLO Z RÁDIA") if packet.simulated else "RADIO / KISS USB"
        text = (f"{packet.timestamp} | {source}\n"
                f"{packet.source} > {packet.destination}"
                f"{(',' + packet.path) if packet.path else ''}\n"
                f"{self.tr('Typ')}: {packet.kind}\n"
                f"{self.tr('Text')}: {packet.payload}\n"
                f"{self.tr('Dekódováno')}: {packet.summary}\n\n"
                f"{self.tr('AX.25 bez FCS (HEX)')}:\n{packet.hex_data}\n")
        self.set_detail(text)

    def demo(self):
        self.add_packet(decode_ax25(demo_ax25_packet(), simulated=True))
        self.set_status("Přidán ukázkový rámec (nejedná se o skutečný příjem)", self.active)

    def export_csv(self):
        if not self.records:
            self._message_box(messagebox.showinfo, APP_TITLE, "Zatím nejsou žádné rámce k exportu.")
            return
        filename = f"aprs_kiss_{datetime.now():%Y%m%d_%H%M%S}.csv"
        path = filedialog.asksaveasfilename(title="Uložit přijímané rámce", defaultextension=".csv",
                                            initialfile=filename, filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as file:
                writer = csv.writer(file, delimiter=";")
                writer.writerow(["Cas", "Zdroj", "Cil", "Cesta", "Typ", "Dekodovano", "Obsah", "HEX", "Simulace"])
                for packet in self.records:
                    writer.writerow([packet.timestamp, packet.source, packet.destination, packet.path,
                                     packet.kind, packet.summary, packet.payload,
                                     packet.hex_data, "ANO" if packet.simulated else "NE"])
        except OSError as exc:
            self._message_box(messagebox.showerror, APP_TITLE, f"Soubor se nepodařilo uložit:\n{exc}")
            return
        self.set_status(f"Exportováno {len(self.records)} rámců do {Path(path).name}", self.active)

    def open_map(self):
        if self.web.httpd is None:
            self._message_box(messagebox.showerror, APP_TITLE,"Webové rozhraní neběží.")
            return
        webbrowser.open(self.web.local_url())

    @staticmethod
    def _full_service_ready(conf):
        """Verify the authenticated headless service, never the read-only GUI server."""
        url = conf.links('127.0.0.1')['admin'].replace('/control?admin=', '/api/config?admin=', 1)
        try:
            with urlopen(url, timeout=0.6) as resp:
                return resp.status == 200
        except (OSError, ValueError):
            return False

    def open_service_page(self, page, section=''):
        """Switch safely to the full web app; only one process owns the USB COM port."""
        from service_config import ServiceConfig
        try:
            conf = ServiceConfig().load_or_create()
        except (OSError, ValueError) as exc:
            self._message_box(messagebox.showerror, APP_TITLE,
                              'Nelze načíst konfiguraci webové služby: ' + str(exc))
            return
        url = conf.links('127.0.0.1')[page] + ('#' + section if section else '')
        if self._full_service_ready(conf):
            webbrowser.open(url)
            return
        if not self._message_box(messagebox.askyesno, 'Spustit plnou APRS webovou službu',
                'Zprávy, objekty a diagnostika běží v plné webové službě.\n\n'
                'Přejít do ní? Klasický monitor ukončí příjem, vypne své DIGI/iGate, '
                'uvolní USB COM a spustí samostatnou webovou službu.\n\n'
                'Současný stav rádia není možné sdílet mezi oběma procesy.'):
            return
        chosen = self.port_choice.get().split(' | ', 1)[0].strip()
        if chosen:
            try:
                conf.update({'serial': {'port': chosen}})
            except (ValueError, OSError) as exc:
                self._message_box(messagebox.showerror, APP_TITLE, str(exc))
                return

        # Stop the old radio owner before starting the new one.
        self.digi.stop()
        if self.reader:
            self.reader.digi_allowed.clear()
        if self.stop_event:
            self.stop_event.set()
        if self.reader and self.reader.is_alive():
            self.reader.join(timeout=4.0)
        if self.reader and self.reader.is_alive():
            self._message_box(messagebox.showerror, APP_TITLE,
                              'Sériový port se nepodařilo uvolnit. Zkus nejprve Odpojit.')
            return
        if self.igate_client is not None:
            self.igate_client.stop.set()
        self.active = False
        self.connecting = False
        self.web.close()
        try:
            flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0) if sys.platform == 'win32' else 0
            process = subprocess.Popen([sys.executable, str(Path(__file__).resolve().with_name('aprs_service.py'))],
                                       cwd=str(Path(__file__).resolve().parent), creationflags=flags)
        except OSError as exc:
            self._message_box(messagebox.showerror, APP_TITLE, 'Webovou službu nelze spustit: ' + str(exc))
            try:
                self.web.start(lan=False)
            except OSError:
                pass
            return

        def check_start(attempt=0):
            if self._full_service_ready(conf):
                webbrowser.open(url)
                self.root.destroy()
            elif process.poll() is not None or attempt >= 40:
                self._message_box(messagebox.showerror, APP_TITLE,
                                  'Webová služba se nespustila. Zkontroluj okno konzole a nastavení portu.')
                try:
                    self.web.start(lan=False)
                except OSError:
                    pass
            else:
                self.root.after(250, lambda: check_start(attempt + 1))
        self.root.after(350, check_start)

    def tx_dialog(self):
        win = tk.Toplevel(self.root)
        self._window_title(win,"KISS TNC – ruční TX test")
        win.geometry("560x380")
        win.minsize(470, 320)
        win.configure(bg=self.BG)
        panel = tk.Frame(win,bg=self.BG,padx=22,pady=17)
        panel.pack(fill="both",expand=True)
        self._label(panel,"JEDNORÁZOVÝ TX TEST PŘES USB KISS",13,self.ACCENT,"bold").pack(anchor="w",pady=(0,11))
        self._label(panel,"Na UV-K1(8) přepni tlačítkem 3 z RX ONLY na TX.",10,self.WARNING).pack(anchor="w")
        self._label(panel,"Ověř 144,800 MHz FM, anténu, výkon a správnou značku.",9,self.SUB).pack(anchor="w",pady=(0,12))
        call = tk.StringVar(value="OK5TVR-9")
        path = tk.StringVar(value="")
        text = tk.StringVar(value="OK5TVR USB KISS test")
        def field(title,var):
            row=tk.Frame(panel,bg=self.BG);row.pack(fill="x",pady=4)
            self._label(row,title,10,self.SUB,width=13,anchor="w").pack(side="left")
            tk.Entry(row,textvariable=var,bg="#26384B",fg=self.TEXT,insertbackground=self.TEXT,
                     relief="flat",font=("Consolas",11)).pack(side="left",fill="x",expand=True,ipady=5)
        field("Zdroj / SSID",call)
        field("Cesta (vol.)",path)
        field("Text statusu",text)
        self._label(panel,"Test je APRS status: ZDROJ>APRS[,CESTA]:>TEXT. Cesta je bez WIDE (DIRECT).",
                    9,self.SUB).pack(anchor="w",pady=(10,4))
        msg=tk.StringVar(value="Žádný rámec nebyl odeslán.")
        self._label(panel,"",9,self.WARNING,textvariable=msg,wraplength=505,justify="left").pack(anchor="w",pady=5)
        def send():
            if self.digi.enabled:
                self._message_box(messagebox.showwarning, 'KISS TX','Nejprve vypni automatický digipeater, aby se nemísily TX rámce.',parent=win);return
            if not self.active or self.reader is None:
                self._message_box(messagebox.showwarning, "KISS TX", "Nejprve připoj COM port radiostanice.",parent=win);return
            if time.monotonic()-self.last_tx < 20:
                self._message_box(messagebox.showwarning, "KISS TX","Mezi dvěma ručními testy vyčkej alespoň 20 sekund.",parent=win);return
            try:
                ui=encode_ui_packet(call.get(),"APRS",path.get(),">"+text.get())
                wire=encode_kiss_data(ui)
            except (ValueError,UnicodeError) as exc:
                self._message_box(messagebox.showerror, "KISS TX",str(exc),parent=win);return
            if not self._message_box(messagebox.askyesno, "Potvrdit vysílání", 
                       "Program pošle JEDEN rámec do radiostanice. Pokud je KISS TNC v režimu TX, může se odvysílat na RF.\n\n"
                       + call.get().upper()+">APRS"+(" "+path.get() if path.get() else "")+":>"+text.get()
                       +"\n\nPokračovat?",parent=win):return
            if self.reader.send(wire):
                self.last_tx=time.monotonic()
                msg.set("Odeslání do USB fronty potvrzeno. Sleduj TX počítadlo a displej rádia; fyzický přenos tím ještě není prokázán.")
            else: msg.set("Rámec nebyl přijat do fronty (obsazeno nebo odpojování).")
        self._btn(panel,"Odeslat 1 APRS TX rámec",send,primary=True).pack(anchor="w",pady=(7,0))

    def igate_dialog(self):
        win=tk.Toplevel(self.root)
        self._window_title(win,"APRS-IS iGate – pouze RF → internet")
        win.geometry("575x440")
        win.configure(bg=self.BG)
        panel=tk.Frame(win,bg=self.BG,padx=22,pady=17);panel.pack(fill="both",expand=True)
        self._label(panel,"APRS iGATE – RF → APRS-IS",14,self.ACCENT,"bold").pack(anchor="w",pady=(0,7))
        self._label(panel,"Bez APRS-IS → RF. Program z internetu nikdy automaticky nevysílá.",9,self.SUB).pack(anchor="w",pady=(0,10))
        call=tk.StringVar(value=self.igate_client.call if self.igate_client else
                           str(self.settings.get('igate_call','OK5TVR-10')))
        passcode=tk.StringVar(value="")
        host=tk.StringVar(value="rotate.aprs2.net")
        port=tk.StringVar(value="14580")
        def field(title,var,mask=None):
            row=tk.Frame(panel,bg=self.BG);row.pack(fill="x",pady=4)
            self._label(row,title,10,self.SUB,width=14,anchor="w").pack(side="left")
            tk.Entry(row,textvariable=var,show=mask or "",bg="#26384B",fg=self.TEXT,insertbackground=self.TEXT,
                     relief="flat",font=("Consolas",11)).pack(side="left",fill="x",expand=True,ipady=5)
        field("Volací značka",call)
        field("APRS-IS passcode",passcode,"*")
        field("Server",host)
        field("TCP port",port)
        self._label(panel,"Passcode je potřeba pro ověřené přihlášení. Nikdy se neukládá do souboru.",9,self.WARNING).pack(anchor="w",pady=(12,4))
        self._btn(panel,'Nastavení vlastní GPS pozice / APRS-IS majáku...',self.position_dialog).pack(anchor='w',pady=(0,7))
        self._label(panel,"U přijatých RF paketů se přidá qAO,IGATECALL (receive-only iGate).",
                    9,self.SUB).pack(anchor="w",pady=(0,8))
        status=tk.StringVar(value="Aktivní" if self.igate_client else "Vypnuto")
        self._label(panel,"",10,self.ACCENT,textvariable=status).pack(anchor="w",pady=4)
        def stop():
            if self.igate_client is not None:
                self.igate_client.stop.set()
                self.igate_client=None
                self.state.update_status(igate="Vypnuto")
                self.web_var.set("iGate: vypnuto")
            status.set("Vypnuto")
        def start():
            if self.igate_client:
                self._message_box(messagebox.showinfo, "APRS-IS", "iGate už běží. Nejprve ji vypni.",parent=win);return
            c=call.get().strip().upper();pc=passcode.get().strip();h=host.get().strip()
            try:portno=int(port.get())
            except ValueError:portno=-1
            if (not IS_CALL_RE.fullmatch(c) or not pc.isdigit() or not 0<=int(pc)<=32767
                    or not h or len(h)>253 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for ch in h)
                    or not 1<=portno<=65535):
                self._message_box(messagebox.showerror, "APRS-IS","Oprav značku, numerický passcode (0–32767), server a port.",parent=win);return
            if not self._message_box(messagebox.askyesno, "Povolit RF→APRS-IS", "Odesílat reálně přijaté a povolené RF pakety do veřejné sítě APRS-IS?\n\n"
                                     + c+" @ "+h+":"+str(portno),parent=win):return
            self.igate_client=APRSISClient(c,pc,h,portno,self.events)
            try:
                self.igate_client.configure_position(self._position_beacon_line(c),
                    int(self.settings.get('beacon_interval',30)))
            except (ValueError,TypeError) as exc:
                self.igate_client=None
                self._message_box(messagebox.showerror, 'APRS-IS',f'Neplatné nastavení polohy: {exc}',parent=win);return
            self.settings['igate_call']=c
            try: save_settings(self.settings)
            except OSError: pass
            self.igate_client.start()
            status.set("Připojuji...")
        controls=tk.Frame(panel,bg=self.BG);controls.pack(anchor="w",pady=11)
        self._btn(controls,"Spustit iGate",start,primary=True).pack(side="left",padx=(0,10))
        self._btn(controls,"Vypnout iGate",stop).pack(side="left")


    def _position_beacon_line(self, call: str):
        """Return None unless publication is explicitly enabled and position set."""
        if not self.settings.get('beacon_enabled', False):
            return None
        lat=self.settings.get('latitude')
        lon=self.settings.get('longitude')
        if lat is None or lon is None:
            raise ValueError('Pro APRS-IS maják musíš zadat GPS šířku a délku.')
        return aprsis_position(call,lat,lon,
                               str(self.settings.get('comment','OK5TVR RX iGate')),
                               symbol='R&')

    def _publish_position_locally(self):
        lat=self.settings.get('latitude'); lon=self.settings.get('longitude')
        try:
            if lat is None or lon is None:
                self.state.set_own_position(None)
            else:
                self.state.set_own_position({
                    'call':str(self.settings.get('igate_call','OK5TVR-10')).upper(),
                    'lat':decimal_coordinate(lat,True),'lon':decimal_coordinate(lon,False),
                    'comment':str(self.settings.get('comment','')),
                    'beacon':bool(self.settings.get('beacon_enabled',False))})
        except ValueError:
            self.state.set_own_position(None)

    def position_dialog(self):
        win=tk.Toplevel(self.root);self._window_title(win,'Poloha GPS iGate a APRS-IS maják')
        win.geometry('640x565');win.minsize(560,500);win.configure(bg=self.BG)
        panel=tk.Frame(win,bg=self.BG,padx=22,pady=15);panel.pack(fill='both',expand=True)
        self._label(panel,'GPS POLOHA STANICE / APRS-IS',14,self.ACCENT,'bold').pack(anchor='w',pady=(0,8))
        self._label(panel,'Poloha se ukládá lokálně. Zveřejnění vyžaduje zapnutý APRS-IS maják.',
                    9,self.SUB).pack(anchor='w',pady=(0,12))
        lat=tk.StringVar(value=str(self.settings.get('latitude','')) if self.settings.get('latitude') is not None else '')
        lon=tk.StringVar(value=str(self.settings.get('longitude','')) if self.settings.get('longitude') is not None else '')
        locator=tk.StringVar(value=str(self.settings.get('locator','JN69PS')))
        comment=tk.StringVar(value=str(self.settings.get('comment','OK5TVR RX iGate')))
        beacon=tk.BooleanVar(value=bool(self.settings.get('beacon_enabled',False)))
        interval=tk.StringVar(value=str(self.settings.get('beacon_interval',30)))
        def field(label,var):
            row=tk.Frame(panel,bg=self.BG);row.pack(fill='x',pady=4)
            self._label(row,label,10,self.SUB,width=20,anchor='w').pack(side='left')
            tk.Entry(row,textvariable=var,bg='#26384B',fg=self.TEXT,insertbackground=self.TEXT,
                     relief='flat',font=('Consolas',11)).pack(side='left',fill='x',expand=True,ipady=5)
        field('Zeměpisná šířka',lat)
        field('Zeměpisná délka',lon)
        self._label(panel,'Desetinné stupně: N/E kladné, S/W záporné (např. 49.7384, 13.3736).',
                    9,self.SUB).pack(anchor='w',pady=(2,8))
        row=tk.Frame(panel,bg=self.BG);row.pack(fill='x',pady=3)
        self._label(row,'Lokátor (přibližně)',10,self.SUB,width=20,anchor='w').pack(side='left')
        tk.Entry(row,textvariable=locator,bg='#26384B',fg=self.TEXT,insertbackground=self.TEXT,
                 relief='flat',font=('Consolas',11),width=12).pack(side='left',ipady=5)
        def from_locator():
            try:
                lt,ln=maidenhead_center(locator.get());lat.set(f'{lt:.6f}');lon.set(f'{ln:.6f}')
            except ValueError as exc:self._message_box(messagebox.showerror, 'Lokátor',str(exc),parent=win)
        self._btn(row,'Použít střed lokátoru',from_locator).pack(side='left',padx=9)
        self._label(panel,'Střed lokátoru není přesná GPS poloha. Pro skutečnou polohu zadej souřadnice.',
                    9,self.WARNING).pack(anchor='w',pady=(2,9))
        field('Komentář APRS',comment)
        tk.Checkbutton(panel,text=self.tr('Posílat polohu do APRS-IS, pokud běží iGate (nikoli na RF)'),
                       variable=beacon,bg=self.BG,fg=self.TEXT,selectcolor='#26384B',
                       activebackground=self.BG,activeforeground=self.TEXT,
                       font=('Segoe UI',10)).pack(anchor='w',pady=(12,8))
        row=tk.Frame(panel,bg=self.BG);row.pack(anchor='w')
        self._label(row,'Interval majáku',10,self.SUB).pack(side='left',padx=(0,11))
        ttk.Combobox(row,values=['30','60','120'],textvariable=interval,width=8,
                     state='readonly',style='Dark.TCombobox').pack(side='left')
        self._label(row,'min. · symbol R& (receive-only iGate)',9,self.SUB).pack(side='left',padx=9)
        status=tk.StringVar(value='Poloha se na veřejnou mapu neodešle, dokud nezapneš APRS-IS maják.')
        self._label(panel,'',9,self.WARNING,textvariable=status,wraplength=575,justify='left').pack(anchor='w',pady=(10,5))
        def save():
            try:
                if not lat.get().strip() and not lon.get().strip():
                    if beacon.get():raise ValueError('Pro zapnutý maják vyplň obě GPS souřadnice.')
                    lt=ln=None
                else:
                    lt=decimal_coordinate(lat.get(),True)
                    ln=decimal_coordinate(lon.get(),False)
                it=int(interval.get())
                if it not in (30,60,120):raise ValueError('Interval pouze 30/60/120 minut')
                # Validate the station-originated APRS packet even when not published.
                if lt is not None:
                    aprsis_position(str(self.settings.get('igate_call','OK5TVR-10')),lt,ln,comment.get(),'R&')
                if beacon.get() and self.igate_client is not None:
                    if not self._message_box(messagebox.askyesno, 'Zveřejnění GPS na APRS-IS',
                       f'Zveřejnit na APRS-IS polohu {lt:.5f}, {ln:.5f} jako '+self.igate_client.call+
                       '? Maják je veřejný a může se zobrazit na aprs.fi.',parent=win):return
                self.settings.update({'latitude':lt,'longitude':ln,
                    'locator':locator.get().strip().upper(),'comment':comment.get().strip(),
                    'beacon_enabled':bool(beacon.get()),'beacon_interval':it})
                save_settings(self.settings)
                self._publish_position_locally()
                if self.igate_client is not None:
                    self.igate_client.configure_position(
                        self._position_beacon_line(self.igate_client.call),it)
            except (ValueError,OSError) as exc:
                self._message_box(messagebox.showerror, 'Nastavení GPS',str(exc),parent=win);return
            status.set('Nastavení uloženo. Veřejný maják: '+('povolen' if beacon.get() else 'vypnut'))
        self._btn(panel,'Uložit polohu / nastavení',save,primary=True).pack(anchor='w',pady=(7,0))

    def digi_dialog(self):
        win=tk.Toplevel(self.root);self._window_title(win,'APRS DIGI repeater přes USB KISS')
        win.geometry('680x610');win.minsize(590,550);win.configure(bg=self.BG)
        panel=tk.Frame(win,bg=self.BG,padx=22,pady=14);panel.pack(fill='both',expand=True)
        self._label(panel,'APRS DIGIPEATER – PC → USB KISS → RF',14,self.ACCENT,'bold').pack(anchor='w',pady=(0,6))
        self._label(panel,'Na rádiu spusť KISS TNC s povoleným TX. Interní APRS DIGI musí být vypnuté.',
                    10,self.WARNING).pack(anchor='w',pady=(0,7))
        cfg=self.digi.config
        call=tk.StringVar(value=cfg.call)
        mode=tk.StringVar(value=self.tr('Regionální WIDE1 + WIDE2') if cfg.mode=='regional' else 'Fill-in WIDE1-1')
        trace=tk.BooleanVar(value=cfg.trace)
        delay=tk.StringVar(value=str(cfg.delay_s))
        limit=tk.StringVar(value=str(cfg.max_per_min))
        gap=tk.StringVar(value=str(cfg.min_gap_s))
        def field(label,var):
            row=tk.Frame(panel,bg=self.BG);row.pack(fill='x',pady=3)
            self._label(row,label,10,self.SUB,width=24,anchor='w').pack(side='left')
            tk.Entry(row,textvariable=var,bg='#26384B',fg=self.TEXT,insertbackground=self.TEXT,
                     relief='flat',font=('Consolas',11)).pack(side='left',fill='x',expand=True,ipady=4)
        field('Vlastní značka DIGI',call)
        row=tk.Frame(panel,bg=self.BG);row.pack(fill='x',pady=4)
        self._label(row,'Režim',10,self.SUB,width=24,anchor='w').pack(side='left')
        ttk.Combobox(row,values=['Fill-in WIDE1-1',self.tr('Regionální WIDE1 + WIDE2')],
            state='readonly',style='Dark.TCombobox',textvariable=mode,width=32).pack(side='left')
        tk.Checkbutton(panel,text=self.tr('V regionálním režimu navíc TRACE2-1 / TRACE2-2'),variable=trace,
            bg=self.BG,fg=self.TEXT,selectcolor='#26384B',activebackground=self.BG,
            activeforeground=self.TEXT,font=('Segoe UI',10)).pack(anchor='w',pady=(5,8))
        field('Odklad / viscous (s)',delay)
        field('Maximum TX / min',limit)
        field('Min. odstup TX (s)',gap)
        self._label(panel,'Deduplikace 30 s · max. 8 AX.25 hops · první nevyužitý hop · bez preempce.',
                    9,self.SUB).pack(anchor='w',pady=(8,4))
        self._label(panel,'Ignoruje 3rd-party / TCPIP / TCPXX a obecné dotazy. NOGATE/RFONLY zůstává jen na RF.',
                    9,self.SUB).pack(anchor='w',pady=(0,8))
        status=tk.StringVar(value='Vypnuto')
        self._label(panel,'',10,self.ACCENT,textvariable=status,wraplength=625,justify='left').pack(anchor='w',pady=5)
        def config_read():
            try:
                c=DigiConfig(call=call.get().strip().upper(),
                    mode='regional' if mode.get().startswith('Region') else 'fill',
                    trace=trace.get(),delay_s=float(delay.get().replace(',','.')),
                    max_per_min=int(limit.get()),min_gap_s=float(gap.get().replace(',','.')))
                c.validate()
                return c
            except (ValueError,TypeError) as exc:
                self._message_box(messagebox.showerror, 'APRS DIGI','Oprav konfiguraci: '+str(exc),parent=win)
                return None
        def preview():
            c=config_read()
            if c is None:return
            from aprs_digi import rewrite_digi
            raw=encode_ui_packet('TEST-7','APRS','WIDE1-1,WIDE2-1','>TEST bez RF')
            result,reason=rewrite_digi(raw,c)
            if result:
                pkt=decode_ax25(result)
                status.set(f'BEZ RF: TEST-7>APRS,WIDE1-1,WIDE2-1 → TEST-7>APRS,{pkt.path}')
            else:status.set('Simulace: '+reason)
        def stop():
            if self.reader: self.reader.digi_allowed.clear()
            self.digi.stop();self.state.update_digi(self.digi.snapshot())
            status.set('DIGI vypnuté. Rozpracované čekající rámce zrušeny.')
            self._update_counters()
        def start():
            if self.digi.enabled:
                self._message_box(messagebox.showinfo, 'APRS DIGI','Nejprve vypni běžící DIGI.',parent=win);return
            if not self.active or self.reader is None:
                self._message_box(messagebox.showwarning, 'APRS DIGI','Nejprve připoj USB KISS TNC.',parent=win);return
            c=config_read()
            if c is None:return
            if not self._message_box(messagebox.askyesno, 'Povolit automatické RF vysílání',
                'Zapnout opakování APRS paketů prostřednictvím USB KISS TNC?\n\n'
                'UV-K1(8) musí být v KISS TX režimu a aplikace APRS DIGI na rádiu vypnutá.\n'
                'Software filtruje duplicitní pakety, ale neumí sám potvrdit fyzické odvysílání.\n\n'
                'Značka: '+c.call+'; režim: '+c.mode+'; maximum: '+str(c.max_per_min)+'/min.',
                parent=win):return
            self.digi=DigiRepeater(c)
            self.digi.start()
            if self.reader: self.reader.digi_allowed.set()
            self.settings.update({'digi_call':c.call,'digi_mode':c.mode,'digi_trace':c.trace})
            try:save_settings(self.settings)
            except OSError:pass
            self.state.update_digi(self.digi.snapshot())
            status.set('DIGI zapnuto · automatické retransmise povoleny')
            self._update_counters()
        buttons=tk.Frame(panel,bg=self.BG);buttons.pack(anchor='w',pady=(8,0))
        self._btn(buttons,'Spustit DIGI',start,primary=True).pack(side='left',padx=(0,7))
        self._btn(buttons,'Vypnout DIGI',stop).pack(side='left',padx=(0,7))
        self._btn(buttons,'Test pravidel (bez RF)',preview).pack(side='left')
        def refresh_status():
            if not win.winfo_exists():return
            snap=self.digi.snapshot()
            if snap['enabled']:
                status.set('Zapnuto · fronta '+str(snap['pending'])+
                    ' · TX přes USB: '+str(snap['tx_written'])+
                    ' · duplicity: '+str(snap['duplicates'])+
                    ' · blokované: '+str(snap['rejected'])+
                    '\n'+snap['last_action'])
            win.after(850,refresh_status)
        refresh_status()

    def lan_dialog(self):
        if self.web.httpd is None:
            self._message_box(messagebox.showerror, APP_TITLE,"Webové rozhraní není dostupné.")
            return
        if not self.web.lan:
            if not self._message_box(messagebox.askyesno, "Webový přístup v LAN", 
                    "Povolit přístup k READ-ONLY mapě z dalších zařízení ve stejné síti?\n\n"
                    "Připojení je HTTP bez TLS; používej jen důvěryhodnou domácí LAN. "
                    "Nedoporučuje se vystavovat port do internetu.\n\nPokračovat?"):
                return
            try:self.web.start(lan=True,port=self.web.port)
            except OSError as exc:
                self._message_box(messagebox.showerror, APP_TITLE, str(exc));return
            url=self.web.lan_url(local_ipv4())
            self.root.clipboard_clear();self.root.clipboard_append(url)
            self.web_var.set("LAN mapa aktivní · odkaz ve schránce")
            self._message_box(messagebox.showinfo, "Mapa v telefonu", 
                "Otevři na mobilu (ve stejné Wi-Fi):\n\n"+url+
                "\n\nOdkaz včetně přístupového klíče byl zkopírován do schránky. "
                "Pokud se stránka nenačte, ověř IP PC a firewall Windows.")
        else:
            if self._message_box(messagebox.askyesno, "Web v LAN","Vypnout přístup z LAN (web v tomto PC zůstane)?"):
                try:self.web.start(lan=False,port=self.web.port)
                except OSError as exc:self._message_box(messagebox.showerror, APP_TITLE,str(exc));return
                self.web_var.set("LAN web vypnut · pouze " + self.web.local_url())

    def exit_app(self):
        if self.reader: self.reader.digi_allowed.clear()
        self.digi.stop()
        if self.stop_event: self.stop_event.set()
        if self.igate_client: self.igate_client.stop.set()
        self.web.close()
        self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
