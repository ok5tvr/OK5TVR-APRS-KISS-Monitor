"""UI regressions runnable without a browser, radio or network services."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest
from urllib.request import urlopen
from aprs_features import MonitorState
from web_panel import WebPanel

ROOT = Path(__file__).parent


class ModernWebTests(unittest.TestCase):
    def test_theme_available_to_login_and_read_only_clients(self):
        panel = WebPanel(MonitorState())
        panel.start(port=0)
        try:
            with urlopen(f'http://127.0.0.1:{panel.port}/assets/web_theme.css?v=28', timeout=3) as response:
                self.assertEqual(response.headers.get_content_type(), 'text/css')
                self.assertIn('--sidebar:', response.read().decode())
            for name in ('web_unified.html', 'web_dashboard.html', 'web_control.html',
                         'web_messages.html', 'web_bbs.html', 'web_operations.html', 'web_login.html'):
                self.assertIn('/assets/web_theme.css?v=28', (ROOT/name).read_text())
            for installer in ('install_raspberry.sh', 'sestavit_EXE_windows.bat'):
                self.assertIn('web_theme.css', (ROOT/installer).read_text())
        finally:
            panel.close()

    @unittest.skipUnless(shutil.which('node'), 'Node.js needed for DOM behavior checks')
    def test_iframe_height_does_not_grow_with_polling(self):
        html = (ROOT/'web_unified.html').read_text()
        function = html.split('function resizeFrame(frame) {', 1)[1].split(
            'document.querySelectorAll("nav.tabs button")', 1)[0]
        script = '''const assert = require('node:assert/strict');
        const frame = {style:{height:'720px'}, contentDocument:{
          body:{offsetHeight:960},documentElement:{}},contentWindow:{
          getComputedStyle:()=>({marginTop:'0',marginBottom:'0'}),dispatchEvent:()=>{}}};
        Object.defineProperty(frame.contentDocument.documentElement,'scrollHeight',{
          get:()=>parseFloat(frame.style.height)});
        ''' + 'function resizeFrame(frame) {' + function + '''
        for(let i=0;i<50;i++)resizeFrame(frame);
        assert.equal(frame.style.height,'984px');
        frame.contentDocument.body.offsetHeight=200;
        resizeFrame(frame);
        assert.equal(frame.style.height,'720px');'''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    @unittest.skipUnless(shutil.which('node'), 'Node.js needed for DOM behavior checks')
    def test_navigation_title_mobile_and_history_stay_synchronized(self):
        html = (ROOT/'web_unified.html').read_text()
        functions = 'function syncNavigation() {' + html.split('function syncNavigation() {', 1)[1].split('function trimEmbedded(', 1)[0]
        tabs = re.findall(r'<button[^>]*data-tab="([^"]+)"', html)
        script = '''const assert=require('node:assert/strict');
        const tabIds=TABS;
        let currentTab='home',configLoaded=true;const params=new URLSearchParams();
        const destinations={},location={hash:'#home'},visits=[];
        const history={pushState:(a,b,hash)=>{visits.push(hash);location.hash=hash;}};
        const buttons=tabIds.map(tab=>({dataset:{tab},textContent:tab,
          setAttribute(name,value){this[name]=value;}}));
        const nodes={'page-select':{replaceChildren(...options){this.options=options;}},'page-title':{}};
        for(const tab of tabIds)nodes['tab-'+tab]={hidden:tab!=='home'};
        const $=id=>nodes[id];
        const document={querySelectorAll:()=>buttons,
          querySelector:selector=>buttons.find(b=>selector.includes('"'+b.dataset.tab+'"')),
          createElement:()=>({})};
        '''.replace('TABS', json.dumps(tabs)) + functions + '''
        showTab('rx');
        assert.equal(nodes['tab-rx'].hidden,false);
        assert.equal(nodes['tab-home'].hidden,true);
        assert.equal(buttons[1]['aria-selected'],'true');
        assert.equal(nodes['page-select'].value,'rx');
        assert.equal(nodes['page-title'].textContent,'rx');
        assert.equal(nodes['page-select'].options.length,15);
        showTab('rx');assert.deepEqual(visits,['#rx']);
        buttons[1].textContent='Receive / TX';syncNavigation();
        assert.equal(nodes['page-title'].textContent,'Receive / TX');
        assert.equal(nodes['page-select'].options[1].textContent,'Receive / TX');
        location.hash='#home';showTab('home');
        assert.equal(visits.length,1);
        assert.equal(nodes['tab-home'].hidden,false);
        showTab('invalid');assert.equal(nodes['page-select'].value,'home');
        '''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
