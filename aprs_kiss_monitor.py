#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Compatibility entrypoint for OK5TVR APRS v1.8 native tabbed desktop.

All desktop modules now run inside a single Tkinter window; the legacy GUI
and its separate read-only web map are not started by this entrypoint.
"""
from aprs_protocol import (KissDecoder, Packet, decode_ax25, demo_ax25_packet,
                           display_bytes, parse_address, position_summary,
                           classify_aprs)
from aprs_desktop import DesktopApp, main

App = DesktopApp

if __name__ == '__main__':
    main()
