/* Shared full-page navigation. Navigation never changes radio state. */
"use strict";
(() => {
const key=new URLSearchParams(location.search).get('admin')||'';
const tr=(cs,en)=>window.OK5TVRLocale?.language==='en'?en:cs;
function route(path){const url=new URL(path,location.origin);if(key)url.searchParams.set('admin',key);return url.pathname+url.search+url.hash;}
document.querySelectorAll('[data-route]').forEach(a=>a.href=route(a.dataset.route));
function language(){document.querySelectorAll('[data-cs][data-en]').forEach(el=>{if(!el.children.length)el.textContent=el.dataset[window.OK5TVRLocale?.language||'cs'];});}
async function refresh(){try{
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);
 let response;try{response=await fetch(route('/api/station'),{cache:'no-store',signal:controller.signal});if(!response.ok)return;response=await response.json();}finally{clearTimeout(timer);}
 const s=response;
 document.getElementById('global-call').textContent=s.call||'Radio Station';
 document.title=(s.call||'Radio Station')+' · '+(document.body.dataset.pageKind==='settings'?tr('Nastavení','Settings'):document.body.dataset.viewRole.toUpperCase());
 const tnc=document.getElementById('global-tnc');tnc.textContent='TNC: '+tr(s.tnc_connected?'PŘIPOJENO':'ODPOJENO',s.tnc_connected?'CONNECTED':'DISCONNECTED');tnc.className=s.tnc_connected?'good':'bad';
 document.getElementById('global-ip').textContent='IP: '+s.ip;
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
window.addEventListener('ok5tvr:language',()=>{language();refresh();});window.addEventListener('station:refresh',refresh);
language();clock();refresh();setInterval(clock,1000);setInterval(refresh,3000);
})();
