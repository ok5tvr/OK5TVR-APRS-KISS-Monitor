#!/usr/bin/env python3
"""Read-only APRS status panel for a Raspberry Pi graphical HDMI desktop.

This program never opens the serial port, controls RF, or reads admin credentials.
It is launched by the user's desktop session, separately from the systemd service.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from urllib.error import URLError
from urllib.request import urlopen


DEFAULT_CONFIG = Path.home() / ".config" / "ok5tvr-aprs" / "config.json"
POLL_MS = 1800
BG = "#0c1727"
PANEL = "#17283c"
INK = "#e8f4ff"
MUTED = "#9ab6c9"
GREEN = "#63e4b6"
ORANGE = "#ffc574"
RED = "#ff818b"


def service_port(config_path: Path) -> int:
    """Read only the web port from the private, non-secret config file."""
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        port = data.get("web", {}).get("port", 8765)
        if type(port) is int and 1024 <= port <= 65535:
            return port
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    return 8765


def fetch_status(port: int) -> dict:
    # This endpoint is available ONLY via loopback; no token appears in a URL.
    url = f"http://127.0.0.1:{port}/api/local-display"
    with urlopen(url, timeout=1.0) as response:
        if response.status != 200:
            raise OSError(f"HTTP {response.status}")
        data = json.load(response)
    if not isinstance(data, dict):
        raise ValueError("Invalid display status response")
    return data


def frame_rows(data: dict, count: int = 7) -> list[tuple[str, str, str, str, str]]:
    """Format received AX.25 frames for a compact 800x480 display."""
    result = []
    history = data.get("history")
    for item in (history if isinstance(history, list) else [])[:count]:
        if not isinstance(item, dict):
            continue
        time_text = str(item.get("time") or "").split(" ")[-1][:8]
        call = str(item.get("source") or "")[:13]
        kind = str(item.get("kind") or "")[:16]
        route = "DIRECT" if item.get("direct") is True else (
            "VIA" if item.get("direct") is False else str(item.get("path") or "-")[:12])
        description = str(item.get("summary") or "").replace("\n", " ").replace("\r", " ")[:90]
        result.append((time_text, call, kind, route, description))
    return result


class Panel:
    def __init__(self, root: tk.Tk, config_path: Path):
        self.root = root
        self.config_path = config_path
        self.visible = False
        self.last_rows = None

        root.withdraw()
        root.title("OK5TVR APRS KISS | Raspberry HDMI")
        root.configure(background=BG)
        root.geometry("800x480+0+0")
        root.minsize(640, 380)
        try:
            root.attributes("-fullscreen", True)
        except tk.TclError:
            pass
        root.bind("<F11>", self.toggle_fullscreen)
        root.bind("<Escape>", self.window_mode)
        root.protocol("WM_DELETE_WINDOW", self.hide_temporarily)
        self._build()
        self.poll()

    def toggle_fullscreen(self, _event=None):
        try:
            current = bool(self.root.attributes("-fullscreen"))
            self.root.attributes("-fullscreen", not current)
        except tk.TclError:
            pass

    def window_mode(self, _event=None):
        try:
            self.root.attributes("-fullscreen", False)
        except tk.TclError:
            pass

    def hide_temporarily(self):
        # Web toggle is the persistent control: closing the GUI merely hides it.
        self.visible = False
        self.root.withdraw()

    def _label(self, parent, text, size=11, color=INK, bold=False, **kwargs):
        return tk.Label(parent, text=text, fg=color, bg=kwargs.pop("bg", BG),
                        font=("DejaVu Sans", size, "bold" if bold else "normal"),
                        **kwargs)

    def _build(self):
        header = tk.Frame(self.root, bg=BG, padx=14, pady=7)
        header.pack(fill="x")
        self._label(header, "OK5TVR  /  APRS KISS", size=18, bold=True, color=GREEN).pack(side="left")
        self.clock = self._label(header, "--:--:--", size=15, color=MUTED)
        self.clock.pack(side="right")

        status = tk.Frame(self.root, bg=BG, padx=14, pady=4)
        status.pack(fill="x")
        self.usb = self._status(status, "USB KISS")
        self.aprsis = self._status(status, "APRS-IS")
        self.digi = self._status(status, "DIGI")

        portbar = tk.Frame(self.root, bg=PANEL, padx=12, pady=7)
        portbar.pack(fill="x", padx=12, pady=(3, 6))
        self.port = self._label(portbar, "TNC: --", size=11, color=INK, bg=PANEL)
        self.port.pack(side="left")
        self.rf_last = self._label(portbar, "RF: --", size=10, color=MUTED, bg=PANEL)
        self.rf_last.pack(side="right")

        cards = tk.Frame(self.root, bg=BG, padx=10)
        cards.pack(fill="x")
        self.metrics = {}
        for name, title in (
            ("rx", "RX rámce"),
            ("tx", "TX USB"),
            ("gate", "APRS-IS"),
            ("digi", "DIGI TX"),
            ("stations", "Stanice"),
        ):
            card = tk.Frame(cards, bg=PANEL, padx=8, pady=5,
                            highlightbackground="#31516a", highlightthickness=1)
            card.pack(side="left", expand=True, fill="x", padx=3)
            self._label(card, title, 10, MUTED, bg=PANEL).pack()
            value = self._label(card, "0", 20, GREEN, bold=True, bg=PANEL)
            value.pack()
            self.metrics[name] = value

        table_heading = tk.Frame(self.root, bg=BG, padx=14, pady=8)
        table_heading.pack(fill="x")
        self._label(table_heading, "POSLEDNÍ PŘIJATÉ RÁMCE", 12, INK, bold=True).pack(side="left")
        self.last_updated = self._label(table_heading, "", 10, MUTED)
        self.last_updated.pack(side="right")

        self._style = ttk.Style(self.root)
        self._style.theme_use("clam")
        self._style.configure("Aprs.Treeview", background=PANEL, fieldbackground=PANEL,
                              foreground=INK, rowheight=26, borderwidth=0,
                              font=("DejaVu Sans", 10))
        self._style.configure("Aprs.Treeview.Heading", background="#25435a",
                              foreground=INK, padding=(4, 6),
                              font=("DejaVu Sans", 10, "bold"), borderwidth=0)
        self._style.map("Aprs.Treeview", background=[("selected", "#176b68")])
        self._style.map("Aprs.Treeview.Heading", background=[("active", "#25435a")])
        columns = ("time", "source", "kind", "route", "text")
        self.table = ttk.Treeview(self.root, columns=columns, show="headings",
                                  style="Aprs.Treeview", height=7, selectmode="browse")
        for field, title, width in (
            ("time", "Čas", 75), ("source", "Značka", 118),
            ("kind", "Typ", 95), ("route", "Cesta", 82), ("text", "Dekódovaný obsah", 398),
        ):
            self.table.heading(field, text=title)
            self.table.column(field, width=width, minwidth=50, anchor="w", stretch=(field == "text"))
        self.table.tag_configure("direct", foreground=GREEN)
        self.table.pack(fill="both", expand=True, padx=12, pady=(0, 5))

        footer = tk.Frame(self.root, bg=BG, padx=14, pady=5)
        footer.pack(fill="x")
        self.info = self._label(footer, "Čekám na APRS službu…", 10, MUTED)
        self.info.pack(side="left")
        self._label(footer, "F11: celá obrazovka  •  Esc: okno", 9, MUTED).pack(side="right")

    def _status(self, parent, name):
        box = tk.Frame(parent, bg=PANEL, padx=9, pady=5)
        box.pack(side="left", fill="x", expand=True, padx=(0, 7))
        self._label(box, name, 10, MUTED, bg=PANEL).pack(side="left")
        value = self._label(box, "● —", 11, MUTED, bold=True, bg=PANEL)
        value.pack(side="right", padx=8)
        return value

    def _set_status(self, field, enabled, text_on="ON", text_off="OFF"):
        field.configure(text=("● " + (text_on if enabled else text_off)),
                        fg=GREEN if enabled else RED)

    def _draw(self, data):
        self.clock.configure(text=datetime.now().strftime("%H:%M:%S"))
        self._set_status(self.usb, bool(data.get("usb_connected")),
                         "PŘIPOJENO", "ODPOJENO")
        self._set_status(self.aprsis, bool(data.get("igate_connected")))
        self._set_status(self.digi, bool(data.get("digi_enabled")))
        configured = str(data.get("port_configured") or "auto")
        actual = str(data.get("port_actual") or "—")
        self.port.configure(text=f"TNC: {actual}   /   nastaveno: {configured}")
        self.rf_last.configure(text="Poslední RF: " + str(data.get("last_rf_frame_utc") or "—")[-19:])
        for name, source in (
            ("rx", "rx"),
            ("tx", "tx_usb"),
            ("gate", "igate_sent"),
            ("digi", "digi_tx"),
            ("stations", "station_count"),
        ):
            self.metrics[name].configure(text=str(data.get(source, 0)))
        rows = frame_rows(data)
        if rows != self.last_rows:
            self.last_rows = rows
            for item in self.table.get_children():
                self.table.delete(item)
            for values in rows:
                tags = ("direct",) if values[3] == "DIRECT" else ()
                self.table.insert("", "end", values=values, tags=tags)
        self.info.configure(text="USB spojení: " + str(data.get("usb_connections", 0)) +
                            "    |    APRS KISS Monitor – pouze čtení")
        self.last_updated.configure(text="Aktualizace: " + datetime.now().strftime("%H:%M:%S"))

    def poll(self):
        try:
            status = fetch_status(service_port(self.config_path))
            enabled = status.get("enabled") is True
            if enabled:
                if not self.visible:
                    self.root.deiconify()
                    self.root.lift()
                    self.visible = True
                self._draw(status)
            elif self.visible:
                self.root.withdraw()
                self.visible = False
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            if self.visible:
                self.clock.configure(text=datetime.now().strftime("%H:%M:%S"))
                self.usb.configure(text="● SLUŽBA OFFLINE", fg=RED)
                self.info.configure(text="Webová APRS služba neodpovídá: " + str(exc)[:70])
        finally:
            self.root.after(POLL_MS, self.poll)


def main():
    parser = argparse.ArgumentParser(description="OK5TVR read-only Raspberry HDMI panel")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args()
    root = tk.Tk()
    Panel(root, args.config)
    root.mainloop()


if __name__ == "__main__":
    main()
