"""Regression: locale switching must preserve nested input/select controls.

The previous unified web console replaced label.textContent on a translated
label, removing wx-source from the DOM and breaking APRS weather loading.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


class WeatherLocaleRegressionTests(unittest.TestCase):
    def test_weather_callsign_field_exists_in_source(self):
        html = (ROOT / "web_unified.html").read_text(encoding="utf-8")
        self.assertRegex(html, r'<label[^>]+for="wx-source"[^>]*>[^<]*<input\s+id="wx-source"')
        self.assertIn('const source=$("wx-source").value.trim()', html)

    @unittest.skipUnless(shutil.which("node"), "Node.js optional")
    def test_language_switch_preserves_live_input_and_value(self):
        js = r"""
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const source = fs.readFileSync(process.argv[1], 'utf8');
const start = source.indexOf('function setLanguage(value) {');
const end = source.indexOf('\nfunction showTab', start);
assert(start >= 0 && end > start, 'setLanguage must remain testable');
const functionSource = source.slice(start, end);

// Simulated browser DOM: setting label.textContent removes nested inputs.
function label(cs, en, before = true) {
  const input = {nodeType:1, value:'OK1ABC-7', tagName:'INPUT'};
  const text = {nodeType:3, nodeValue:cs + ' '};
  const obj = {
    dataset:{cs, en},
    children:[input],
    childNodes:before ? [text, input] : [input, text],
    insertBefore(node) {this.childNodes.unshift(node)},
    get textContent() {return this.childNodes.map(n=>n.nodeValue || '').join('')},
    set textContent(value) {
      this.childNodes=[{nodeType:3, nodeValue:value}];
      this.children=[];
    }
  };
  return {input, text, obj};
}
const wx = label('Značka','Callsign');
const chart = label('Graf','Chart');
const check = label('Zapnout','Enable', false);
const simple = {
  dataset:{cs:'Načíst počasí',en:'Load weather'},
  children:[], childNodes:[],
  textContent:'Načíst počasí'
};
const all=[wx.obj,chart.obj,check.obj,simple];
const languageSelect={value:'cs'};
const document = {
  documentElement:{lang:'cs'},
  querySelectorAll(q) {return q==='[data-cs][data-en]' ? all : []},
  querySelector() {return null},
  createTextNode(value){return {nodeType:3,nodeValue:value}}
};
const context = {
  document,Node:{TEXT_NODE:3},window:{OK5TVRLocale:{setLanguage(){}}},
  destinations:{},$:id=>id==='language' ? languageSelect : null,
  language:'cs'
};
vm.createContext(context);
vm.runInContext(functionSource + '\nsetLanguage("en");', context);
for(const item of [wx,chart,check]){
  assert(item.obj.children.includes(item.input),'Locale switch deleted a form control');
  assert(item.obj.childNodes.includes(item.input),'Locale switch removed control from DOM');
  assert.strictEqual(item.input.value,'OK1ABC-7','Locale switch lost form value');
}
assert.strictEqual(wx.text.nodeValue.trim(),'Callsign');
assert.strictEqual(chart.text.nodeValue.trim(),'Chart');
assert.strictEqual(check.text.nodeValue.trim(),'Enable');
assert.strictEqual(simple.textContent,'Load weather');
vm.runInContext('setLanguage("cs");',context);
assert.strictEqual(wx.text.nodeValue.trim(),'Značka');
assert.strictEqual(chart.text.nodeValue.trim(),'Graf');
assert.strictEqual(check.text.nodeValue.trim(),'Zapnout');
assert.strictEqual(wx.obj.children[0],wx.input);
assert.strictEqual(languageSelect.value,'cs');
"""
        completed = subprocess.run(
            ["node", "-e", js, str(ROOT / "web_unified.html")],
            text=True, capture_output=True, timeout=15,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
