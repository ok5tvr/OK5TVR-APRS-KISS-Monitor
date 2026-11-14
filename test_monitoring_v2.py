"""Read-only monitoring extensions: bounded trails and Prometheus metrics."""
from __future__ import annotations

from urllib.error import HTTPError
from urllib.request import urlopen
import unittest

from aprs_features import MonitorState, encode_ui_packet
from aprs_protocol import decode_ax25
from web_panel import WebPanel, HTML


class MonitoringExtensionsTest(unittest.TestCase):
    @staticmethod
    def packet(lat_minutes: int, source: str = "OK1ABC-7"):
        info=f"!49{lat_minutes:02d}.00N/01322.00E>test"
        return decode_ax25(encode_ui_packet(source, "APRS", "", info))

    def test_bounded_position_trail_and_status_preservation(self):
        state=MonitorState()
        for m in range(40):
            # Keep valid minutes, unique positions, no external RF needed.
            p=decode_ax25(encode_ui_packet("OK1ABC-7","APRS","",
                         f"!4944.{m:02d}N/01322.00E>test"))
            state.add(p)
        station=state.snapshot()['stations'][0]
        self.assertEqual(len(station['trail']),32)
        self.assertEqual(station['trail'][0]['time'][:4],station['last'][:4])
        self.assertAlmostEqual(station['trail'][-1]['lat'],49+44.39/60,places=5)
        state.add(decode_ax25(encode_ui_packet("OK1ABC-7","APRS","",">QRV")))
        self.assertEqual(len(state.snapshot()['stations'][0]['trail']),32)

    def test_no_demo_or_nonposition_trails(self):
        state=MonitorState()
        pkt=self.packet(44)
        pkt.simulated=True
        state.add(pkt)
        self.assertEqual(state.snapshot()['stations'],[])
        state.add(decode_ax25(encode_ui_packet("OK1ABC-7","APRS","",">status")))
        self.assertEqual(state.snapshot()['stations'][0]['trail'],[])

    def test_no_trails_for_third_party_igate(self):
        state=MonitorState()
        # TX builder intentionally forbids third-party encapsulation. Craft
        # received AX.25 UI packet directly for this receive-only test.
        base=encode_ui_packet("OK1GAT","APRS","",">placeholder")
        p=decode_ax25(base[:-len(b'>placeholder')] +
            b"}OK1ABC-7>APRS:!4944.00N/01322.00E>test")
        state.add(p)
        rows={s['call']:s for s in state.snapshot()['stations']}
        self.assertEqual(rows["OK1ABC-7"]['trail'],[])

    def test_map_filter_and_trail_controls_are_present(self):
        for term in ('show-trails','direct-only','show-objects','activity-filter',
                     'drawTrails','filteredStations'):
            self.assertIn(term,HTML)

    def test_prometheus_metrics_requires_viewer_authorization_on_lan(self):
        state=MonitorState()
        state.add(self.packet(44))
        panel=WebPanel(state, viewer_token="view-token", admin_token="admin-token")
        try:
            port=panel.start(lan=True,port=0)
            base=f"http://127.0.0.1:{port}"
            with urlopen(base+"/metrics") as response:
                data=response.read().decode()
                self.assertIn("ok5tvr_aprs_rx_total 1",data)
                self.assertIn("ok5tvr_aprs_stations 1",data)
                self.assertEqual(response.headers['Content-Type'],
                                 "text/plain; version=0.0.4; charset=utf-8")
                self.assertNotIn("admin-token",data)
        finally:
            panel.close()


if __name__=="__main__":
    unittest.main()
