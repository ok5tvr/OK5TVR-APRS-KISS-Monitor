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
                self.assertEqual(len(tabs),9)
                self.assertIn('BBS',tabs)
                self.assertTrue(app.bbs_sessions.winfo_exists())
                self.assertTrue(app.object_list.winfo_exists())
                self.assertTrue(any(t in tabs for t in ('Zprávy','Messages')))
                self.assertTrue(any(t in tabs for t in ('Objekty','Objects')))
                self.assertIsNone(svc.web.httpd)
                app.notebook.select(app.messages_tab);root.update()
                self.assertTrue(app.in_tree.winfo_exists())
                app.language.set('EN');app.switch_language();root.update()
                translated=[app.notebook.tab(tab,'text') for tab in app.notebook.tabs()]
                self.assertIn('Messages',translated)
                self.assertIn('Objects',translated)
                calls=[]
                def action(name,payload=None,callback=None,**kwargs):
                    calls.append((name,payload or {}))
                    result=svc._execute(name,payload or {})
                    if callback:callback(result)
                app._act=action;app._confirm=lambda *args:True
                app.desktop_mode('bbs');self.assertEqual(svc.operating_mode,'bbs')
                self.assertEqual(calls[-1][0],'mode_set')
                app.notebook.select(app.objects_tab);root.update()
                for i in range(6):app.desktop_object_add()
                self.assertEqual(len(app.object_entries),5)
                app.object_fields['name'].set('FIFTH')
                app.object_fields['transport'].set('inet')
                app.object_fields['schedule'].set('times')
                app.object_fields['times'].set('08:00, 18:30')
                app.desktop_objects_save()
                self.assertEqual(calls[-1][0],'objects_save')
                self.assertEqual(svc.config.data['object_slots']['entries'][4]['times'],['08:00','18:30'])
                self.assertEqual(svc.config.data['object_slots']['entries'][4]['transport'],'inet')
                self.assertFalse(svc.objects.active)
                previous=len(calls)
                app.object_entries[0]['name']='FIFTH'
                with patch('desktop_station.messagebox.showerror') as error:
                    app.desktop_objects_save();error.assert_called_once()
                self.assertEqual(len(calls),previous)
                app.object_entries[0]['name']=svc.config.data['object_slots']['entries'][0]['name']
                app._confirm=lambda *args:False
                app.desktop_mode('aprs');self.assertEqual(len(calls),previous)
                app._confirm=lambda *args:True
                app.desktop_mode('aprs');app.desktop_objects_start()
                self.assertTrue(svc.objects.active)
                app.desktop_mode('bbs');self.assertFalse(svc.objects.active)
                app.bbs_config['max_clients'].set('3');app.desktop_bbs_save()
                self.assertEqual(svc.config.data['bbs']['max_clients'],3)
                app._refresh(force=True);root.update()
                self.assertIn('BBS',root.title())
                app.bbs_to.set('ALL');app.bbs_subject.set('Native BBS test')
                app.bbs_message.insert('1.0','Stored from the native window')
                app.desktop_bbs_post();app._refresh_bbs();root.update()
                ident=app.bbs_mail.get_children()[0];app.bbs_mail.selection_set(ident)
                app.desktop_bbs_read();self.assertIn('Stored from',app.bbs_body.get('1.0','end'))
                app.desktop_bbs_reply();self.assertEqual(app.bbs_to.get(),'ALL')
                app.desktop_bbs_delete();self.assertEqual(svc.bbs_snapshot()['mail_count'],0)


            finally:
                root.destroy()
                for name in ('bbs','secondary','alerts','archive','messages','journal'):getattr(svc,name).close()


if __name__=='__main__':unittest.main()
