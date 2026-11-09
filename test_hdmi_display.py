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


if __name__=='__main__':
    unittest.main()
