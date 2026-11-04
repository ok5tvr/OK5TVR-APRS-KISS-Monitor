"""Regression tests for unified v1.8 desktop (no RF hardware required)."""
import os
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aprs_features import encode_ui_packet
from aprs_protocol import decode_ax25
from aprs_service import APRSService
from service_config import ServiceConfig


class DesktopBackendTests(unittest.TestCase):
    def test_desktop_backend_runs_without_opening_http_or_multiple_serial_ports(self):
        with tempfile.TemporaryDirectory() as directory:
            svc=APRSService(ServiceConfig(Path(directory)/'config.json').load_or_create())
            with patch.object(svc.web,'start',side_effect=AssertionError('Desktop must not open HTTP')):
                with patch.object(svc,'_connect_tick') as connect:
                    runner=threading.Thread(target=svc.run,kwargs={'with_web':False},daemon=True)
                    runner.start()
                    try:
                        deadline=time.monotonic()+3
                        while not svc.running and time.monotonic()<deadline:time.sleep(.02)
                        self.assertTrue(svc.running)
                        self.assertIsNone(svc.web.httpd)
                        self.assertIsNone(svc.reader)
                        svc.command('serial_disconnect',{})
                        self.assertFalse(svc.serial_enabled)
                        svc.command('serial_connect',{})
                        self.assertTrue(svc.serial_enabled)
                        connect.assert_called()
                    finally:
                        svc.stop.set();runner.join(timeout=3)
                        self.assertFalse(runner.is_alive())

    def test_incoming_ax25_message_shares_the_backend_and_inbox(self):
        with tempfile.TemporaryDirectory() as directory:
            svc=APRSService(ServiceConfig(Path(directory)/'config.json').load_or_create())
            svc.serial_enabled=False
            runner=threading.Thread(target=svc.run,kwargs={'with_web':False},daemon=True)
            runner.start()
            try:
                deadline=time.monotonic()+2
                while not svc.running and time.monotonic()<deadline:time.sleep(.02)
                raw=encode_ui_packet('OK1ABC-7','APRS','WIDE1-1',
                                     ':OK5TVR   :AHOJ OD OK1ABC{321')
                svc.events.put((svc.session,'frame',decode_ax25(raw)))
                deadline=time.monotonic()+3
                while not svc.messages_snapshot()['inbox'] and time.monotonic()<deadline:time.sleep(.04)
                inbox=svc.messages_snapshot()['inbox']
                self.assertEqual(len(inbox),1)
                self.assertEqual(inbox[0]['recipient'],'OK5TVR')
                self.assertEqual(inbox[0]['sender'],'OK1ABC-7')
                self.assertEqual(inbox[0]['text'],'AHOJ OD OK1ABC')
                self.assertEqual(svc.state.snapshot()['rx'],1)
                self.assertEqual(svc.state.snapshot()['history'][0]['hex_data'],raw.hex(' ').upper())
            finally:
                svc.stop.set();runner.join(timeout=3)

    def test_local_gui_has_all_native_tabs_when_display_available(self):
        try:
            import tkinter as tk
            root=tk.Tk()
        except tk.TclError:
            self.skipTest('GUI display unavailable (run under xvfb-run on CI)')
        from aprs_desktop import DesktopApp
        with tempfile.TemporaryDirectory() as directory:
            svc=APRSService(ServiceConfig(Path(directory)/'config.json').load_or_create())
            try:
                app=DesktopApp(root,service=svc,start_service=False)
                root.update()
                tabs=[app.notebook.tab(tab,'text') for tab in app.notebook.tabs()]
                self.assertEqual(len(tabs),7)
                self.assertTrue(any(t in tabs for t in ('Zprávy','Messages')))
                self.assertTrue(any(t in tabs for t in ('Objekty','Objects')))
                self.assertIsNone(svc.web.httpd)
                app.notebook.select(app.messages_tab);root.update()
                self.assertTrue(app.in_tree.winfo_exists())
                app.language.set('EN');app.switch_language();root.update()
                translated=[app.notebook.tab(tab,'text') for tab in app.notebook.tabs()]
                self.assertIn('Messages',translated)
                self.assertIn('Objects',translated)
            finally:
                root.destroy()
                svc.messages.close();svc.journal.close()


if __name__=='__main__':unittest.main()
