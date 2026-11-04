# OK5TVR APRS KISS Monitor v1.5.0-rc1 (CZ)

Tato verze přidává **česko-anglické ovládání**. Jde o kandidáta na vydání; provoz iGate/DIGI a APRS zpráv potřebuje další ověření na skutečné radiostanici.

## Přepnutí jazyka

- **Webová mapa, nastavení a APRS Zprávy:** v horní části stránky vyber `CZ` nebo `EN`. Přepnutí je okamžité, bez restartu aplikace. Volba se uchovává v daném prohlížeči pro všechny tři stránky.
- **Windows desktopové okno:** vpravo nahoře vyber `CZ` nebo `EN`. Jazyk se uloží do uživatelského nastavení a zůstane zachován po restartu programu.
- Volací značky, AX.25/APRS cesty, přijatý text zpráv a surová data se nikdy automaticky nepřekládají. Některé technické chyby z protokolových knihoven mohou zůstat v původním znění.

## Instalace na Raspberry Pi

Aktualizace probíhá stejně jako u v1.4, **z adresáře nové verze**:

```sh
sh install_raspberry.sh --lan
sudo systemctl status ok5tvr-aprs
python3 /opt/ok5tvr-aprs/aprs_service.py --links
```

Skript kopíruje také nový soubor `web_locale.js`. Stávající konfigurace, passcode a přístupové klíče nejsou nahrazovány. `--lan` používej pouze v důvěryhodné síti.

## Windows

- `spustit.bat` pro klasické okno.
- `spustit_sluzbu_windows.bat` pro webovou službu.
- `zobrazit_odkazy_windows.bat` zobrazí přístupové URL.

Nespouštěj okno a službu současně na stejném COM portu. Automatické RF vysílání je při první instalaci vypnuté.

## Před stabilním v1.5

Ještě je vhodné ověřit nepřetržitý provoz na Raspberry Pi, reálné retransmise DIGI, obousměrné potvrzování zpráv, obnovu spojení po výpadcích a kvalitu RF modulace. Teprve potom verzi označit jako stabilní.

[English guide](README_EN.md) · [Návod pro v1.4](README_v1.4_CZ.md)
