/* Shared full-page navigation. Navigation never changes radio state. */
"use strict";
(() => {
const key=new URLSearchParams(location.search).get('admin')||'';
const tr=(cs,en)=>window.OK5TVRLocale?.language==='en'?en:cs;
function route(path){const url=new URL(path,location.origin);if(key)url.searchParams.set('admin',key);return url.pathname+url.search+url.hash;}
document.querySelectorAll('[data-route]').forEach(a=>a.href=route(a.dataset.route));
function currentRoute(){
 const p=location.pathname,q=new URLSearchParams(location.search);
 if(p==='/aprs'||p==='/unified'){const hash=location.hash.slice(1);return '/aprs#'+(['station-content','main-content'].includes(hash)?(document.body.dataset.activeTab||q.get('tab')||'home'):(hash||q.get('tab')||'home'));}
 if(p==='/settings/advanced')return p+'?tab='+(q.get('tab')||'tnc');
 if(p==='/bbs')return p+(location.hash||'#bbs-status');
 if(p==='/control')return '/settings/aprs';
 if(p==='/')return '/map';
 return p;
}
function navigation(){
 const current=currentRoute();
 if(current.startsWith('/aprs#'))document.body.dataset.activeTab=current.split('#')[1];
 document.querySelectorAll('#station-sidebar [data-route]').forEach(a=>{
  const active=a.dataset.route===current;
  if(active){a.setAttribute('aria-current','page');const group=a.closest('details');if(group)group.open=true;const title=document.getElementById('page-title');if(title)title.textContent=a.textContent;}
  else a.removeAttribute('aria-current');
 });
 const section=current.startsWith('/settings')?'/settings':current.startsWith('/bbs')?'/bbs':current==='/app'?'/app':'/aprs';
 document.querySelectorAll('.global-links [data-route]').forEach(a=>{if(a.dataset.route===section)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
}
const toggle=document.getElementById('navigation-toggle');
function closeMenu(){document.body.classList.remove('navigation-open');toggle.setAttribute('aria-expanded','false');}
toggle.addEventListener('click',()=>{const open=document.body.classList.toggle('navigation-open');toggle.setAttribute('aria-expanded',String(open));});
document.querySelectorAll('#station-sidebar a').forEach(a=>a.addEventListener('click',closeMenu));
window.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.body.classList.contains('navigation-open')){closeMenu();toggle.focus();}});
window.addEventListener('hashchange',navigation);window.addEventListener('popstate',navigation);window.addEventListener('station:navigation',navigation);
document.getElementById('global-logout').addEventListener('click',async()=>{
 try{const response=await fetch('/api/logout',{method:'POST',headers:{'X-APRS-CSRF':'1'}});if(!response.ok)throw Error('HTTP '+response.status);location.replace('/login');}
 catch(e){document.getElementById('global-logout').textContent=tr('Odhlášení selhalo','Logout failed');}
});
function language(){document.querySelectorAll('[data-cs][data-en]').forEach(el=>{if(!el.children.length)el.textContent=el.dataset[window.OK5TVRLocale?.language||'cs'];});}
async function refresh(){try{
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
 let response;try{response=await fetch(route('/api/station'),{cache:'no-store',signal:controller.signal});if(!response.ok)return;response=await response.json();}finally{clearTimeout(timer);}
 const s=response;
 document.getElementById('global-call').textContent=s.call||'Radio Station';
 const active=document.querySelector('#station-sidebar [aria-current]');
 document.title=(s.call||'Radio Station')+' · '+(active?.textContent||tr('Stanice','Station'));
 document.getElementById('global-call').dataset.call=s.call||'Radio Station';
 const tnc=document.getElementById('global-tnc');tnc.textContent='TNC: '+tr(s.tnc_connected?'PŘIPOJENO':'ODPOJENO',s.tnc_connected?'CONNECTED':'DISCONNECTED');tnc.className=s.tnc_connected?'good':'bad';
 document.getElementById('global-ip').textContent='IP: '+s.ip;
 document.getElementById('global-mode').textContent=tr('Režim: ','Mode: ')+(s.mode==='off'?tr('VYPNUTO','OFF'):s.mode.toUpperCase());
 const mode=document.getElementById('settings-mode-state');if(mode)mode.textContent=s.mode.toUpperCase();
 document.querySelectorAll('[data-mode]').forEach(btn=>{btn.classList.toggle('on',btn.dataset.mode===s.mode);btn.setAttribute('aria-pressed',String(btn.dataset.mode===s.mode));});
 }catch(_){document.getElementById('global-tnc').textContent=tr('SLUŽBA NEDOSTUPNÁ','SERVICE OFFLINE');}}
let modeBusy=false;
document.querySelectorAll('[data-mode]').forEach(btn=>btn.addEventListener('click',async()=>{
 if(modeBusy)return;const mode=btn.dataset.mode;
 if(!confirm(tr('Přepnout režim na '+mode.toUpperCase()+'? Předchozí funkce a čekající přenosy se zastaví.','Switch mode to '+mode.toUpperCase()+'? Previous functions and queued transmissions will stop.')))return;
 modeBusy=true;document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=true);
 try{const r=await fetch('/api/control',{method:'POST',headers:{'Content-Type':'application/json','X-APRS-Admin':key,'X-APRS-CSRF':'1'},body:JSON.stringify({action:'mode_set',mode,confirm:true})});const j=await r.json();if(!r.ok||!j.ok)throw Error(j.error||'HTTP '+r.status);document.getElementById('mode-result').textContent=tr('Režim změněn.','Mode changed.');await refresh();}catch(e){document.getElementById('mode-result').textContent=e.message;}finally{modeBusy=false;document.querySelectorAll('[data-mode]').forEach(b=>b.disabled=false);}
}));
function clock(){document.getElementById('global-clock').textContent=new Date().toLocaleString(window.OK5TVRLocale?.language==='en'?'en-GB':'cs-CZ');document.documentElement.style.setProperty('--shell-height',document.getElementById('global-navigation').offsetHeight+'px');}
window.addEventListener('ok5tvr:language',()=>{language();navigation();refresh();});window.addEventListener('station:refresh',refresh);
navigation();language();clock();refresh();setInterval(clock,1000);setInterval(refresh,3000);
})();
