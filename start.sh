#!/bin/bash
cd /home/dietpi/tag-tapper-pi || exit 1

# Map console to framebuffer 1
/usr/bin/con2fbmap 1 1 || true
clear

# Environment for pygame with framebuffer
export TERM=linux
export LANG=de_DE.UTF-8

# SDL configuration for framebuffer 1
export SDL_VIDEODRIVER=fbcon
export SDL_FBDEV=/dev/fb1
export SDL_AUDIODRIVER=dummy

# Hide cursor on tty1
if [ -w /dev/tty1 ]; then
    echo -ne '\e[?25l' > /dev/tty1 || true
fi

# Run the pygame app
/usr/bin/python3 /home/dietpi/tag-tapper-pi/app.py

# Restore cursor when finished
if [ -w /dev/tty1 ]; then
    echo -ne '\e[?25h' > /dev/tty1 || true
fi

exit $?