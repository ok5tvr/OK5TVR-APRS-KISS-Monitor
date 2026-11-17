"""Native station, PBBS and persistent object controls; no additional TNC or HTTP server."""
import copy
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from aprs_objects import validate_entries

FONT='Segoe UI' if sys.platform=='win32' else 'DejaVu Sans'
FONT_BOLD='Segoe UI Semibold' if sys.platform=='win32' else 'DejaVu Sans'
MONO='Consolas' if sys.platform=='win32' else 'DejaVu Sans Mono'

BG='#101925'; PANEL='#1a293a'; FG='#eaf2f9'; MUTED='#aac1d1'; GREEN='#35d1b6'


class StationDesktop:
    def desktop_scroll(self,parent):
        outer=tk.Frame(parent,bg=BG);outer.pack(fill='both',expand=True)
        canvas=tk.Canvas(outer,bg=BG,highlightthickness=0)
        bar=ttk.Scrollbar(outer,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        content=tk.Frame(canvas,bg=BG);window=canvas.create_window((0,0),window=content,anchor='nw')
        content.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(window,width=event.width))
        def wheel(event):
            if not canvas.winfo_viewable():return
            x,y=canvas.winfo_pointerxy()
            if canvas.winfo_rootx()<=x<canvas.winfo_rootx()+canvas.winfo_width() and canvas.winfo_rooty()<=y<canvas.winfo_rooty()+canvas.winfo_height():
                widget=canvas.winfo_containing(x,y)
                if widget and widget.winfo_class() in ('Listbox','Text','Treeview'):return
                canvas.yview_scroll(-1 if event.delta>0 or getattr(event,'num',0)==4 else 1,'units')
                return 'break'
        for event in ('<MouseWheel>','<Button-4>','<Button-5>'):self.root.bind_all(event,wheel,add='+')
        return content

    def _build_station(self):
        row=tk.Frame(self.desktop_scroll(self.station_tab),bg=BG);row.pack(fill='both',expand=True,padx=8,pady=8)
        identity=self.pane(row,'Stanice a provozní režim','Station and operating mode');identity.pack(side='left',fill='both',expand=True,padx=(0,8))
        self.station_mode=tk.StringVar();self.label(identity,'','',textvariable=self.station_mode,bg=PANEL,fg=GREEN).pack(anchor='w')
        buttons=tk.Frame(identity,bg=PANEL);buttons.pack(fill='x',pady=8)
        self.mode_buttons={}
        for mode,title in [('aprs','APRS'),('bbs','BBS'),('off','OFF')]:
            self.mode_buttons[mode]=self.button(buttons,title,title,lambda mode=mode:self.desktop_mode(mode));self.mode_buttons[mode].pack(side='left',padx=3)
        self.station_call=self.field(identity,'CALL bez SSID','Base CALL')
        self.station_ssids={role:self.field(identity,title,title) for role,title in [('igate','iGate SSID'),('digi','DIGI SSID'),('bbs','BBS SSID'),('client','BBS client SSID')]}
        self.station_transport=self.combo(identity,'TNC transport','TNC transport',('serial','tcp'),'serial')
        self.station_baud=self.field(identity,'USB baud','USB baud','115200')
        self.station_tcp_host=self.field(identity,'TCP KISS host','TCP KISS host','127.0.0.1')
        self.station_tcp_port=self.field(identity,'TCP KISS port','TCP KISS port','8001')
        self.button(identity,'Uložit CALL / SSID / TNC','Save CALL / SSID / TNC',self.desktop_identity_save,kind='primary').pack(anchor='w',pady=8)
        settings=self.pane(row,'Nastavení BBS serveru','BBS server settings');settings.pack(side='left',fill='both',expand=True)
        self.bbs_config={}
        for key,cs,en in [('welcome','Uvítání (ASCII)','Welcome (ASCII)'),('max_clients','Klienti (1–10)','Clients (1–10)'),('idle_seconds','Nečinnost (s)','Idle timeout (s)'),('max_tx_per_minute','BBS TX / min (2–24)','BBS TX / min (2–24)'),('max_messages','Maximum zpráv','Maximum messages')]:
            self.bbs_config[key]=self.field(settings,cs,en)
        self.bbs_posts=self.check(settings,'Povolit zprávy z RF','Allow RF posts')
        self.button(settings,'Uložit BBS (server se vypne)','Save BBS (stops server)',self.desktop_bbs_save,kind='primary').pack(anchor='w',pady=10)
        self.button(settings,'Zapnout BBS server','Start BBS server',self.desktop_bbs_start,kind='primary').pack(anchor='w',pady=4)
        self.button(settings,'Vypnout BBS server','Stop BBS server',lambda:self._act('bbs_off'),kind='warn').pack(anchor='w',pady=4)
        self.label(settings,'APRS a BBS nemohou běžet současně. BBS používej na vhodném packetovém kanálu, ne na 144,800 MHz APRS.',
                   'APRS and BBS cannot run together. Use a suitable packet channel for BBS, not 144.800 MHz APRS.',bg=PANEL,fg=MUTED,wraplength=390,justify='left').pack(anchor='w',pady=10)

    def _load_station_config(self):
        c=self.config.data;identity=c['station'];self.station_call.set(identity['call'])
        for role,var in self.station_ssids.items():var.set(identity[role+'_ssid'])
        self.station_transport.set(c['tnc']['transport']);self.station_baud.set(c['serial']['baud'])
        self.station_tcp_host.set(c['tnc']['tcp_host']);self.station_tcp_port.set(c['tnc']['tcp_port'])
        for key,var in self.bbs_config.items():var.set(c['bbs'][key])
        self.bbs_posts.set(c['bbs']['allow_posts'])

    def desktop_mode(self,mode):
        if self._confirm('Přepnout na '+mode.upper()+'? Dosavadní funkce a spojení se zastaví.',
                         'Switch to '+mode.upper()+'? Existing functions and connections will stop.'):
            self._act('mode_set',{'mode':mode,'confirm':True},callback=lambda _:self._refresh(force=True))

    def desktop_identity_save(self):
        try:
            station={'call':self.station_call.get().strip().upper()}
            station.update({role+'_ssid':int(var.get()) for role,var in self.station_ssids.items()})
            data={'station':station,'serial':{'baud':int(self.station_baud.get()),'port':self.port.get().strip()},
                  'tnc':{'transport':self.station_transport.get(),'tcp_host':self.station_tcp_host.get().strip(),'tcp_port':int(self.station_tcp_port.get())}}
        except ValueError as exc:messagebox.showerror('Station',str(exc));return
        if self._confirm('Uložit identitu a TNC? Aktuální přenosy se zastaví.','Save identity and TNC? Current transmissions will stop.'):
            self._act('station_save',data,callback=lambda _:self._load_config())

    def desktop_bbs_save(self):
        try:config={key:(var.get() if key=='welcome' else int(var.get())) for key,var in self.bbs_config.items()}
        except ValueError as exc:messagebox.showerror('BBS',str(exc));return
        config['allow_posts']=self.bbs_posts.get()
        if self._confirm('Uložit BBS a ukončit její spojení?','Save BBS settings and stop its connections?'):
            self._act('bbs_save',{'bbs':config},callback=lambda _:self._load_station_config())

    def desktop_bbs_start(self):
        if self._confirm('Zapnout BBS RF vysílání? Ověř vhodný packetový kanál mimo 144,800 MHz APRS.',
                         'Enable BBS RF transmissions? Verify a suitable packet channel outside 144.800 MHz APRS.'):
            self._act('bbs_on',{'confirm':True,'confirm_channel':True})

    def _build_bbs(self):
        frame=tk.Frame(self.bbs_tab,bg=BG);frame.pack(fill='both',expand=True,padx=8,pady=8)
        self.bbs_summary=tk.StringVar();self.label(frame,'','',textvariable=self.bbs_summary,fg=GREEN).pack(anchor='w',pady=5)
        inner=ttk.Notebook(frame,style='APRS.TNotebook');inner.pack(fill='both',expand=True)
        operations=tk.Frame(inner,bg=BG);mail=tk.Frame(inner,bg=BG)
        inner.add(operations,text='AX.25 / Terminal');inner.add(mail,text='BBS Mail')
        upper=self.pane(operations,'Připojené stanice','Connected stations');upper.pack(fill='x',pady=5)
        grid,self.bbs_sessions=self._tree(upper,('CALL','State','ACK','Queue','Retry','Idle s'),(140,120,65,75,65,90),height=4);grid.pack(fill='x')
        self.button(upper,'Odpojit vybranou','Disconnect selected',self.desktop_bbs_disconnect).pack(anchor='w',pady=4)
        client=self.pane(operations,'Klient vzdálené BBS','Remote BBS client');client.pack(fill='both',expand=True)
        controls=tk.Frame(client,bg=PANEL);controls.pack(fill='x')
        self.bbs_target=self.field(client,'Vzdálená CALL / SSID','Remote CALL / SSID')
        self.button(controls,'Připojit','Connect',self.desktop_bbs_connect,kind='primary').pack(side='left')
        self.button(controls,'Odpojit klienta','Disconnect client',lambda:self.desktop_bbs_disconnect(client=True)).pack(side='left',padx=8)
        self.bbs_console=tk.Text(client,height=6,bg=BG,fg=FG,font=(MONO,10),wrap='word',state='disabled');self.bbs_console.pack(fill='both',expand=True,pady=5)
        self.bbs_line=self.field(client,'ASCII příkaz','ASCII command')
        self.button(client,'Odeslat řádek','Send line',self.desktop_bbs_send,kind='primary').pack(anchor='w')
        left=self.pane(mail,'Uložené zprávy','Stored messages');left.pack(side='left',fill='both',expand=True,padx=(0,8))
        tools=tk.Frame(left,bg=PANEL);tools.pack(fill='x')
        self.bbs_offset=0
        self.button(tools,'Předchozí','Previous',lambda:self.desktop_bbs_page(-50)).pack(side='left')
        self.button(tools,'Další','Next',lambda:self.desktop_bbs_page(50)).pack(side='left',padx=6)
        self.bbs_page=tk.StringVar();self.label(left,'','',textvariable=self.bbs_page,bg=PANEL).pack(anchor='w')
        grid,self.bbs_mail=self._tree(left,('ID','From','To','Subject'),(50,100,100,200),height=8);grid.pack(fill='both',expand=True)
        self.bbs_mail.bind('<<TreeviewSelect>>',self.desktop_bbs_read)
        self.bbs_body=tk.Text(left,height=6,bg=BG,fg=FG,wrap='word',state='disabled');self.bbs_body.pack(fill='both',expand=True,pady=5)
        self.button(left,'Smazat vybranou zprávu','Delete selected message',self.desktop_bbs_delete,kind='warn').pack(anchor='w')
        compose=self.pane(mail,'Nová zpráva / odpověď','New message / reply');compose.pack(side='left',fill='both',expand=True)
        self.bbs_to=self.field(compose,'Komu (ALL = veřejná)','To (ALL = public)','ALL')
        self.bbs_subject=self.field(compose,'Předmět ASCII','ASCII subject')
        self.bbs_message=tk.Text(compose,bg=BG,fg=FG,insertbackground=FG,height=12,wrap='word');self.bbs_message.pack(fill='both',expand=True,pady=8)
        self.button(compose,'Odpovědět vybrané','Reply to selected',self.desktop_bbs_reply).pack(anchor='w',pady=3)
        self.button(compose,'Uložit do BBS','Store in BBS',self.desktop_bbs_post,kind='primary').pack(anchor='w',pady=3)
        self._bbs_signature=None;self._bbs_console_last=None;self._bbs_mail_items={}

    @staticmethod
    def _set_text(widget,text):
        widget.configure(state='normal');widget.delete('1.0','end');widget.insert('1.0',text);widget.configure(state='disabled')

    def _refresh_bbs(self):
        data=self.service.bbs_snapshot(self.bbs_offset)
        self.bbs_summary.set(f"{data['call']} · {data['role'].upper()} {'ON' if data['active'] else 'OFF'} · "+self.t('Klienti','Clients')+f" {data['client_count']}/{data['max_clients']} · "+str(data.get('last_error') or ''))
        rows=[(s['remote'],'CONNECTING' if s['connecting'] else 'CLOSING' if s['closing'] else 'CONNECTED',str(s['waiting_ack']),s['queued_chars'],s['retries'],s['idle_seconds']) for s in data['sessions']]
        selected=self.bbs_sessions.selection();selected=selected[0] if selected else None
        self.bbs_sessions.delete(*self.bbs_sessions.get_children())
        for row in rows:self.bbs_sessions.insert('','end',iid=row[0],values=row)
        if selected in self.bbs_sessions.get_children():self.bbs_sessions.selection_set(selected)
        if data['console']!=self._bbs_console_last:
            self._bbs_console_last=data['console'];self._set_text(self.bbs_console,data['console']);self.bbs_console.see('end')
        self.bbs_page.set(f"{self.bbs_offset+1 if data['mail_count'] else 0}–{min(self.bbs_offset+50,data['mail_count'])} / {data['mail_count']}")
        signature=[(r['id'],r['sender'],r['recipient'],r['subject']) for r in data['messages']]
        if signature!=self._bbs_signature:
            self._bbs_signature=signature;self._bbs_mail_items={str(r['id']):r for r in data['messages']}
            self.bbs_mail.delete(*self.bbs_mail.get_children())
            for row in signature:self.bbs_mail.insert('','end',iid=str(row[0]),values=row)

    def desktop_bbs_page(self,step):
        count=self.service.bbs_snapshot()['mail_count'];self.bbs_offset=max(0,min(max(0,((count-1)//50)*50),self.bbs_offset+step));self._refresh_bbs()

    def desktop_bbs_disconnect(self,client=False):
        selection=self.bbs_sessions.selection()
        remote=self.service.bbs_snapshot().get('remote') if client else selection[0] if selection else None
        if not remote:return
        if self._confirm('Odpojit '+remote+'?','Disconnect '+remote+'?'):self._act('bbs_disconnect',{'remote':remote,'confirm':True})

    def desktop_bbs_connect(self):
        if self._confirm('Připojit vzdálenou BBS přes RF? Místní server se vypne.','Connect to remote BBS via RF? The local server will stop.'):
            self._act('bbs_client_connect',{'remote':self.bbs_target.get().strip().upper(),'confirm':True,'confirm_channel':True})

    def desktop_bbs_send(self):
        self._act('bbs_client_send',{'text':self.bbs_line.get()},callback=lambda _:self.bbs_line.set(''))

    def desktop_bbs_read(self,_event=None):
        selected=self.bbs_mail.selection()
        if not selected:return
        # Snapshot contains the sysop-visible message body, without issuing RF commands.
        row=self._bbs_mail_items.get(selected[0],{})
        self._set_text(self.bbs_body,str(row.get('body','')))

    def desktop_bbs_reply(self):
        selected=self.bbs_mail.selection()
        if not selected:return
        row=self._bbs_mail_items[selected[0]];own=self.config.data['bbs']['call']
        self.bbs_to.set(row['recipient'] if row['sender']==own else row['sender'])
        subject=row['subject'];self.bbs_subject.set(subject if subject.upper().startswith('RE:') else 'Re: '+subject)

    def desktop_bbs_post(self):
        if self._confirm('Uložit zprávu do BBS?','Store message in BBS?'):
            self._act('bbs_post',{'recipient':self.bbs_to.get().strip().upper(),'subject':self.bbs_subject.get(),'body':self.bbs_message.get('1.0','end-1c'),'confirm':True},callback=lambda _:self.bbs_message.delete('1.0','end'))

    def desktop_bbs_delete(self):
        selected=self.bbs_mail.selection()
        if selected and self._confirm('Smazat zprávu #'+selected[0]+'?','Delete message #'+selected[0]+'?'):
            self._act('bbs_delete',{'id':int(selected[0]),'confirm':True})

    def _build_objects(self):
        self.object_entries=copy.deepcopy(self.config.data['object_slots']['entries']);self.object_index=None;self.object_dirty=False
        content=tk.Frame(self.desktop_scroll(self.objects_tab),bg=BG);content.pack(fill='both',expand=True,padx=8,pady=8)
        listing=self.pane(content,'Uložené objekty (max. 5)','Saved objects (max. 5)');listing.pack(side='left',fill='y',padx=(0,8))
        self.object_list=tk.Listbox(listing,bg=BG,fg=FG,exportselection=False,width=20);self.object_list.pack(fill='both',expand=True)
        self.object_list.bind('<<ListboxSelect>>',self.desktop_object_select)
        for cs,en,command in [('Přidat','Add',self.desktop_object_add),('Odebrat','Remove',self.desktop_object_remove),('Uložit objekty','Save objects',self.desktop_objects_save),('Načíst uložené','Reload saved',self.desktop_objects_reload),('Odeslat uložený','Send saved',self.desktop_object_send),('Zapnout plán','Start schedules',self.desktop_objects_start),('Vypnout plán','Stop schedules',lambda:self._act('objects_stop'))]:
            self.button(listing,cs,en,command).pack(fill='x',pady=3)
        editor=self.pane(content,'Definice vybraného objektu','Selected object definition');editor.pack(side='left',fill='both',expand=True)
        self.object_state=tk.StringVar();self.label(editor,'','',textvariable=self.object_state,bg=PANEL,fg=GREEN).pack(anchor='w')
        fields=tk.Frame(editor,bg=PANEL);fields.pack(fill='x');left=tk.Frame(fields,bg=PANEL);left.pack(side='left',fill='x',expand=True,padx=(0,8));right=tk.Frame(fields,bg=PANEL);right.pack(side='left',fill='x',expand=True)
        self.object_fields={}
        for key,cs,en in [('name','Název (9 ASCII)','Name (9 ASCII)'),('lat','GPS šířka','Latitude'),('lon','GPS délka','Longitude'),('comment','Komentář ASCII','ASCII comment'),('path','RF cesta','RF path'),('symbol','Znak symbolu','Symbol character')]:self.object_fields[key]=self.field(left,cs,en,width=14)
        for key,cs,en,choices in [('transport','Výstup','Transport',('rf','inet')),('schedule','Plán','Schedule',('manual','interval','times')),('symbol_table','Tabulka symbolů','Symbol table',('/','\\'))]:self.object_fields[key]=self.combo(right,cs,en,choices,choices[0])
        self.object_fields['interval_minutes']=self.field(right,'Interval (min)','Interval (min)',30,width=8)
        self.object_fields['times']=self.field(right,'Časy HH:MM, HH:MM','Times HH:MM, HH:MM',width=14)
        self.object_fields['alive']=self.check(right,'LIVE (vypnuto = KILL)','LIVE (off = KILL)',True)
        self.object_fields['enabled']=self.check(right,'Zařadit do plánu','Include in schedule',True)
        for var in self.object_fields.values():var.trace_add('write',lambda *_:setattr(self,'object_dirty',True))
        self.label(editor,'Časy jsou místní časy počítače. Po úpravě nejprve Uložit objekty; plánování se zapíná samostatně.',
                   'Times use the computer local clock. Save objects after editing; scheduling is started separately.',bg=PANEL,fg=MUTED,wraplength=650,justify='left').pack(anchor='w',pady=12)
        self.o_status=self.field(editor,'APRS stavový text','APRS status text')
        self.o_status_path=self.combo(editor,'RF cesta statusu','Status RF path',('DIRECT','WIDE1-1','WIDE1-1,WIDE2-1'),'DIRECT')
        tools=tk.Frame(editor,bg=PANEL);tools.pack(fill='x')
        self.button(tools,'Odeslat status','Send status',self.send_status).pack(side='left')
        self.button(tools,'Odeslat GPS','Send GPS',self.send_position).pack(side='left',padx=8)
        self.desktop_object_list()

    def desktop_object_commit(self):
        if self.object_index is None:return
        row={key:var.get() for key,var in self.object_fields.items()}
        try:
            row['lat']=float(row['lat']);row['lon']=float(row['lon']);row['interval_minutes']=float(row['interval_minutes'])
            row['times']=[t.strip() for t in row['times'].split(',') if t.strip()]
            validated=validate_entries([row])[0]
        except (ValueError,TypeError) as exc:messagebox.showerror('APRS objects',str(exc));raise ValueError(str(exc))
        self.object_entries[self.object_index]=validated

    def desktop_object_list(self):
        self.object_list.delete(0,'end')
        for i,row in enumerate(self.object_entries):self.object_list.insert('end',f"{i+1} · {row['name']} · {row['transport'].upper()}")

    def desktop_object_select(self,_event=None):
        selection=self.object_list.curselection()
        if not selection:return
        try:self.desktop_object_commit()
        except ValueError:
            self.object_list.selection_clear(0,'end')
            if self.object_index is not None:self.object_list.selection_set(self.object_index)
            return
        self.object_index=selection[0];row=self.object_entries[self.object_index];dirty=self.object_dirty
        for key,var in self.object_fields.items():var.set(', '.join(row[key]) if key=='times' else row[key])
        self.object_dirty=dirty

    def desktop_object_add(self):
        if len(self.object_entries)>=5:return
        try:self.desktop_object_commit()
        except ValueError:return
        names={row['name'] for row in self.object_entries};name=next('OBJ'+str(i) for i in range(1,7) if 'OBJ'+str(i) not in names)
        row=validate_entries([{'name':name}])[0];self.object_entries.append(row);self.object_dirty=True
        self.object_index=None;self.desktop_object_list();self.object_list.selection_set(len(self.object_entries)-1);self.desktop_object_select()

    def desktop_object_remove(self):
        if self.object_index is None:return
        del self.object_entries[self.object_index];self.object_index=None;self.object_dirty=True;self.desktop_object_list()

    def desktop_objects_reload(self):
        if self.object_dirty and not self._confirm('Zahodit neuložené změny objektů?','Discard unsaved object changes?'):return
        self.object_entries=copy.deepcopy(self.config.data['object_slots']['entries'])
        self.object_index=None;self.object_dirty=False;self.desktop_object_list()

    def desktop_objects_save(self):
        try:self.desktop_object_commit()
        except ValueError:return
        try:entries=validate_entries(self.object_entries)
        except ValueError as exc:messagebox.showerror('APRS objects',str(exc));return
        def saved(_):self.object_entries=copy.deepcopy(entries);self.object_dirty=False;self.desktop_object_list()
        self._act('objects_save',{'entries':entries},callback=saved)

    def _saved_object_ready(self):
        try:self.desktop_object_commit()
        except ValueError:return False
        if self.object_entries!=self.config.data['object_slots']['entries']:
            messagebox.showwarning('APRS objects',self.t('Nejdříve ulož změny.','Save changes first.'));return False
        return True

    def desktop_object_send(self):
        if self.object_index is None or not self._saved_object_ready():return
        row=self.object_entries[self.object_index]
        if self._confirm('Odeslat '+row['name']+' přes '+row['transport'].upper()+'?','Send '+row['name']+' via '+row['transport'].upper()+'?'):
            self._act('object_slot_send',{'index':self.object_index,'confirm':True})

    def desktop_objects_start(self):
        if self._saved_object_ready() and self._confirm('Zapnout plánované odesílání objektů?','Start scheduled object transmissions?'):
            self._act('objects_start',{'confirm':True})

    def _refresh_objects(self,diag):
        data=self.service.objects_snapshot()
        state=self.t('Plán ZAPNUTÝ','Scheduling ON') if data['active'] else self.t('Plán VYPNUTÝ','Scheduling OFF')
        last=data['status'].get(str(self.object_index),'')
        self.object_state.set(state+' · '+data['device_time']+'\n'+last)
