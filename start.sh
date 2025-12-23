#!/bin/bash
# Start-Skript für Tag Tapper auf dem Raspberry Pi LCD-Display

# Setze Terminal-Typ für beste Kompatibilität mit Framebuffer
export TERM=linux
export COLORTERM=truecolor

# Textual-spezifische Einstellungen für Framebuffer
export TEXTUAL_DRIVER=linux
export TEXTUAL_COLOR_SYSTEM=truecolor

# Wechsle ins App-Verzeichnis
cd "$(dirname "$0")"

# Starte die App
sudo -E python3 app.py
