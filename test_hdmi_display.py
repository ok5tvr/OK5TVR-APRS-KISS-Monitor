"""Lightweight Raspberry HDMI panel unit tests (no display server or RF required)."""
from pathlib import Path
import json
import tempfile
import unittest

from local_display import frame_rows, service_port
from service_config import ServiceConfig, validate_config


class HdmiDisplayTests(unittest.TestCase):
    def test_disabled_on_fresh_install_and_validates_boolean(self):
        self.assertFalse(validate_config({})['display']['enabled'])
        self.assertTrue(validate_config({'display':{'enabled': True}})['display']['enabled'])
        with self.assertRaises(ValueError):
            validate_config({'display': {'enabled': 'yes'}})

    def test_serial_and_tokens_unchanged_by_display_update(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg=ServiceConfig(Path(directory)/'config.json').load_or_create()
            old_token=cfg.secrets['admin_token']
            cfg.update({'display':{'enabled': True}})
            again=ServiceConfig(cfg.path).load_or_create()
            self.assertTrue(again.data['display']['enabled'])
            self.assertEqual(old_token,again.secrets['admin_token'])
            self.assertFalse(again.data['digi']['autostart'])
            self.assertFalse(again.data['igate']['autostart'])

    def test_read_only_display_port_setting(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'config.json'
            self.assertEqual(service_port(path),8765)
            path.write_text(json.dumps({'web':{'port':9876}}),encoding='utf-8')
            self.assertEqual(service_port(path),9876)
            path.write_text(json.dumps({'web':{'port':'bad'}}),encoding='utf-8')
            self.assertEqual(service_port(path),8765)

    def test_last_received_frames_bounded(self):
        payload={'history':[
            {'time':'2026-11-09 06:31:25','source':'OK1ABC-7','kind':'Pozice',
             'path':'WIDE1-1','direct':True,'summary':'!position'},
            {'time':'2026-11-09 06:31:23','source':'OK5XYZ-2','kind':'APRS',
             'path':'WIDE1-1*','direct':False,'summary':'test\nnewline'},
        ]}
        rows=frame_rows(payload, count=1)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0][:2],('06:31:25','OK1ABC-7'))
        self.assertEqual(rows[0][3],'DIRECT')
        second=frame_rows(payload, count=2)[1]
        self.assertEqual(second[3],'VIA')
        self.assertNotIn('\n',second[4])


class ModeDisplayTests(unittest.TestCase):
    def test_bbs_waiting_connected_client_and_error_states(self):
        from local_display import bbs_view
        self.assertIn('server vypnut',bbs_view({'bbs':{}})['metrics'])
        waiting=bbs_view({'bbs':{'call':'OK5TVR-8','active':True,'mail_count':5}})
        self.assertIn('Čekám na AX.25',waiting['metrics']);self.assertIn('OK5TVR-8',waiting['metrics'])
        self.assertIn('Pošta: 5',waiting['metrics'])
        connected=bbs_view({'bbs':{'active':True,'connected':True,'remote':'OK1ABC-7','stats':{'received_i':12}}})
        self.assertIn('OK1ABC-7',connected['remote']);self.assertIn('RX I: 12',connected['metrics'])
        self.assertNotIn('Čekám na',connected['console'])
        client=bbs_view({'bbs':{'active':True,'role':'client','connecting':True,'console':'Welcome to remote BBS','remote':'OK2ABC-8','waiting_ack':True}})
        self.assertIn('Navazuji',client['metrics']);self.assertEqual(client['console'],'Welcome to remote BBS')
        self.assertIn('ACK: čekám',client['metrics']);self.assertTrue(client['remote'].startswith('Vzdálená BBS'))
        self.assertIn('KISS write failed',bbs_view({'bbs':{'last_error':'KISS write failed'}})['metrics'])

    def test_live_aprs_bbs_aprs_switch_rebuilds_widgets_and_clears_old_frames(self):
        from local_display import Panel
        class Widget:
            def __init__(self):self.values={};self.text='';self.destroyed=False
            def configure(self,**kwargs):self.values.update(kwargs)
            def destroy(self):self.destroyed=True
            def delete(self,*args):self.text=''
            def insert(self,*args,**kwargs):self.text=args[-1] if args else kwargs.get('values','')
            def see(self,*args):pass
            def get_children(self):return []
        class Root:
            def winfo_children(self):return widgets.copy()
            def title(self,title):self.name=title
        panel=Panel.__new__(Panel);panel.mode='aprs';panel.root=Root();panel.last_rows=None;panel.last_bbs_text=None
        widgets=[];builds=[]
        def build():
            builds.append(panel.mode)
            for name in ('brand','clock','usb','aprsis','digi','port','rf_last','last_updated','table','info','bbs_server','bbs_client','bbs_remote','bbs_metrics','bbs_text'):
                widget=Widget();setattr(panel,name,widget);widgets.append(widget)
            panel.metrics={k:Widget() for k in ('rx','tx','gate','digi','stations')}
        panel._build=build;build()
        panel._draw({'mode':'aprs','call':'OK5TVR','rx':50,'history':[]})
        old_brand=panel.brand
        panel._draw({'mode':'bbs','call':'OK5TVR','usb_connected':True,'bbs':{'active':True,'remote':'OK1ABC-7','connected':True,'mail_count':8}})
        self.assertTrue(old_brand.destroyed);self.assertEqual(panel.brand.values['text'],'OK5TVR / BBS')
        self.assertIn('Pošta: 8',panel.bbs_metrics.values['text']);self.assertEqual(panel.bbs_server.values['text'],'● ON')
        panel._draw({'mode':'aprs','call':'OK5TVR','rx':51,'history':[]})
        self.assertEqual(builds,['aprs','bbs','aprs']);self.assertEqual(panel.metrics['rx'].values['text'],'51')
        self.assertEqual(panel.brand.values['text'],'OK5TVR / APRS')

    def test_installer_refreshes_exact_existing_gui_and_preserves_session(self):
        import os
        from unittest.mock import patch
        import local_display
        with tempfile.TemporaryDirectory() as directory:
            proc=Path(directory);config=proc/'config.json';script=str(Path(local_display.__file__).resolve())
            for pid,args in [('123',['/usr/bin/python3',script,'--config',str(config)]),('124',['/usr/bin/python3','unrelated.py'])]:
                d=proc/pid;d.mkdir();(d/'cmdline').write_bytes(('\0'.join(args)+'\0').encode())
                (d/'environ').write_bytes(b'DISPLAY=:0\0XAUTHORITY=/home/pi/.Xauthority\0')
                (d/'stat').write_text(pid+' (python3) Z 0')
            with patch.object(local_display.os,'kill') as kill,patch.object(local_display.subprocess,'Popen') as popen:
                self.assertEqual(local_display.restart_running_panel(config,proc),1)
                kill.assert_called_once();self.assertEqual(kill.call_args.args[0],123)
                self.assertEqual(popen.call_args.kwargs['env']['DISPLAY'],':0')
                self.assertEqual(popen.call_args.args[0][-2:],['--config',str(config)])
            (proc/'123'/'environ').write_bytes(b'PATH=/usr/bin\0')
            with patch.object(local_display.os,'kill') as kill,patch.object(local_display.subprocess,'Popen') as popen:
                self.assertEqual(local_display.restart_running_panel(config,proc),0)
                kill.assert_not_called();popen.assert_not_called()

if __name__=='__main__':
    unittest.main()
