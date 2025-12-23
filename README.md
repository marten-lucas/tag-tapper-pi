# Tag Tapper - Netzwerk-Dashboard

Textual-basiertes Dashboard für Raspberry Pi mit LCD-Display.

## Installation auf DietPi/Raspberry Pi

1. **Abhängigkeiten installieren:**
```bash
cd /home/dietpi/tag-tapper-pi
pip3 install -r requirements.txt
```

2. **Start-Skript ausführbar machen:**
```bash
chmod +x start.sh
```

3. **Manueller Start:**
```bash
sudo ./start.sh
```

## Autostart beim Booten

**Option 1: Systemd Service (empfohlen)**

Erstelle `/etc/systemd/system/tag-tapper.service`:
```ini
[Unit]
Description=Tag Tapper Network Dashboard
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/home/dietpi/tag-tapper-pi
Environment="TERM=linux"
Environment="COLORTERM=truecolor"
Environment="TEXTUAL_DRIVER=linux"
Environment="TEXTUAL_COLOR_SYSTEM=truecolor"
ExecStart=/usr/bin/python3 /home/dietpi/tag-tapper-pi/app.py
StandardInput=tty
TTYPath=/dev/tty1
TTYReset=yes
TTYVHangup=yes
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Aktiviere den Service:
```bash
sudo systemctl daemon-reload
sudo systemctl enable tag-tapper
sudo systemctl start tag-tapper
```

Status prüfen:
```bash
sudo systemctl status tag-tapper
```

**Option 2: rc.local**

Füge vor `exit 0` in `/etc/rc.local` hinzu:
```bash
su - dietpi -c "cd /home/dietpi/tag-tapper-pi && TERM=linux COLORTERM=truecolor ./start.sh" &
```

## Troubleshooting

### App zeigt auf LCD falsche Farben

- Stelle sicher, dass `TERM=linux` gesetzt ist (nicht `xterm-256color`)
- Verwende das `start.sh` Skript statt direktem `python3 app.py`

### App startet nicht

- Prüfe Logs: `tail -f /home/dietpi/error.log`
- Prüfe systemd: `sudo journalctl -u tag-tapper -f`

### SSH-Zugriff während App läuft

Die App läuft auf TTY1 (physisches Display). SSH-Verbindungen nutzen separate TTYs.

## Entwicklung

**Test auf dem lokalen Rechner:**
```bash
export TERM=xterm-256color
python app.py
```

**Test via SSH auf dem Pi:**
```bash
export TERM=xterm-256color
python app.py
```

**Auf dem physischen Display (Keyboard am Pi):**
```bash
sudo ./start.sh
```
