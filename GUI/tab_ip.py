import re
import os
import subprocess
import threading
import time
try:
    import pygame
except Exception:
    pygame = None
try:
    import yaml
except Exception:
    yaml = None


class TabIP:
    def __init__(self):
        self._lock = threading.Lock()
        self.cached_ifaces = []
        self.cached_ips = {}
        self.cached_up = {}
        self.cached_vlan_names = {}
        self.poll_interval = 2  # seconds between refreshes
        # Track previous state for change detection
        self.prev_up = {}
        self.prev_ips = {}
        # Toast message system
        self.toast_message = None
        self.toast_time = 0
        # populate initial cache
        self.refresh_cache()
        # start polling thread for reliable updates
        p = threading.Thread(target=self._poll_loop, daemon=True)
        p.start()

    def _poll_loop(self):
        """Periodic fallback refresh to catch state changes if monitor misses events."""
        while True:
            try:
                self.refresh_cache()
            except Exception:
                pass
            time.sleep(self.poll_interval)

    def refresh_cache(self):
        try:
            ifaces = self.get_all_interfaces()
        except Exception:
            ifaces = []
        vlan_names = self.load_vlan_names()
        ips = {}
        ups = {}
        for iface in ifaces:
            ips[iface] = self.get_ip_for_iface(iface)
            ups[iface] = self.iface_is_up(iface)
        
        # Detect state changes and generate toast messages
        for iface in ups:
            if iface not in self.prev_up:
                # New interface detected (first time)
                self.prev_up[iface] = ups[iface]
                self.prev_ips[iface] = ips.get(iface)
            else:
                # Check for UP→DOWN or DOWN→UP transition
                if self.prev_up[iface] != ups[iface]:
                    if ups[iface]:
                        # Interface came UP
                        self.toast_message = f"{iface} verbunden"
                        self.toast_time = time.time()
                    else:
                        # Interface went DOWN
                        self.toast_message = f"{iface} getrennt"
                        self.toast_time = time.time()
                    self.prev_up[iface] = ups[iface]
                
                # Check for IP changes (gained IP or lost IP)
                curr_ip = ips.get(iface)
                prev_ip = self.prev_ips.get(iface)
                if curr_ip != prev_ip:
                    if curr_ip and not prev_ip:
                        # Interface got an IP
                        self.toast_message = f"{iface} verbunden"
                        self.toast_time = time.time()
                    elif not curr_ip and prev_ip:
                        # Interface lost its IP
                        self.toast_message = f"{iface} getrennt"
                        self.toast_time = time.time()
                    self.prev_ips[iface] = curr_ip
        
        with self._lock:
            self.cached_ifaces = ifaces
            self.cached_ips = ips
            self.cached_up = ups
            self.cached_vlan_names = vlan_names
    def load_vlan_names(self):
        # repo root is parent of GUI folder
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_path = os.path.join(repo, 'config.yaml')
        names = {}
        if not yaml:
            return names
        try:
            with open(cfg_path, 'r') as f:
                cfg = yaml.safe_load(f) or {}
            for v in cfg.get('vlans', []):
                vid = str(v.get('id'))
                name = v.get('name') or v.get('name', '')
                if name:
                    names[vid] = name
        except Exception:
            pass
        return names

    def get_all_interfaces(self):
        out = subprocess.check_output(['ip', '-o', 'link', 'show']).decode('utf-8')
        names = []
        for line in out.splitlines():
            parts = line.split(':', 2)
            if len(parts) >= 2:
                names.append(parts[1].strip().split('@')[0])
        return names

    def get_ip_for_iface(self, iface):
        try:
            out = subprocess.check_output(['ip', '-o', '-4', 'addr', 'show', 'dev', iface]).decode('utf-8')
            m = re.search(r'\binet (\S+)', out)
            if m:
                return m.group(1)
        except subprocess.CalledProcessError:
            return None
        return None

    def iface_is_up(self, iface):
        # Returns True if the interface operational state is UP
        try:
            out = subprocess.check_output(['ip', '-o', 'link', 'show', 'dev', iface]).decode('utf-8')
            # example: '2: eth0: <BROADCAST,...> mtu 1500 qdisc ... state DOWN mode DEFAULT group ...'
            m = re.search(r'\bstate\s+(\w+)', out)
            if m:
                return m.group(1).upper() == 'UP'
        except subprocess.CalledProcessError:
            return False
        return False

    def get_wifi_ssid(self, iface):
        """Get the SSID for a wifi interface. Returns None if not connected or error."""
        try:
            out = subprocess.check_output(['iwgetid', iface, '-r'], stderr=subprocess.DEVNULL).decode('utf-8').strip()
            return out if out else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def draw(self, surface, rect, app, styles, fonts):
        # Use cached data updated by monitor thread for quick redraws
        with self._lock:
            ifaces = list(self.cached_ifaces)
            vlan_names = dict(self.cached_vlan_names)
            ips = dict(self.cached_ips)
            ups = dict(self.cached_up)

        # Build ordered candidate list: eth0, VLANs (by id), then wlan*
        candidates = []
        if 'eth0' in ifaces:
            candidates.append('eth0')

        vlans = [n for n in ifaces if '.' in n]
        def vlan_key(name):
            try:
                return int(name.split('.')[-1])
            except Exception:
                return 0
        for n in sorted(vlans, key=vlan_key):
            candidates.append(n)

        for n in sorted(ifaces):
            if n.startswith('wlan') or n.startswith('wl'):
                if n not in candidates:
                    candidates.append(n)

        # Use a smaller font for the table to fit more rows and reduce top spacing
        table_font = fonts.get('tab_title', fonts['content'])
        # Prepare drawing positions
        row_h = table_font.get_height() + 6
        start_y = rect.top + 40
        name_x = rect.left + 28
        ip_x = rect.right - 220
        status_x = rect.right - 60

        # Header background to visually separate header from content
        header_bg_rect = pygame.Rect(name_x - 16, rect.top + 12, rect.width - 40, row_h + 6)
        try:
            pygame.draw.rect(surface, styles.TAB_BG, header_bg_rect)
        except Exception:
            try:
                pygame.draw.rect(surface, styles.NEUTRAL_RING, header_bg_rect)
            except Exception:
                pass

        # Header row (no 'OK' label per request)
        hdr_name = table_font.render('Schnittstelle', True, styles.TEXT_COLOR)
        hdr_ip = table_font.render('IP', True, styles.TEXT_COLOR)
        surface.blit(hdr_name, (name_x, rect.top + 18))
        surface.blit(hdr_ip, (ip_x, rect.top + 18))

        # Rows
        for i, iface in enumerate(candidates):
            y = start_y + i * row_h
            ip = ips.get(iface)
            up = ups.get(iface, False)

            display_name = iface
            if '.' in iface:
                vid = iface.split('.')[-1]
                if vid in vlan_names:
                    display_name = f"{iface} {vlan_names[vid]}"
            elif iface.startswith('wlan') or iface.startswith('wl'):
                # Add SSID for wifi interfaces if available
                ssid = self.get_wifi_ssid(iface)
                if ssid:
                    # Truncate SSID if too long (max 16 chars)
                    ssid_short = ssid[:16] + '…' if len(ssid) > 16 else ssid
                    display_name = f"{iface} ({ssid_short})"

            name_s = table_font.render(display_name, True, styles.TEXT_COLOR)
            surface.blit(name_s, (name_x, y))
            # Only show IP if interface is UP and has an IP
            ip_text = ip if (ip and up) else '-'
            ip_s = table_font.render(ip_text, True, styles.MUTED_TEXT)
            surface.blit(ip_s, (ip_x, y))
            # Draw status icon: green filled circle if up+ip, otherwise red X
            if up and ip:
                # green dot
                try:
                    pygame.draw.circle(surface, styles.OK_COLOR, (status_x, y + row_h // 2), row_h // 3)
                except Exception:
                    try:
                        pygame.draw.circle(surface, styles.OK_COLOR, (status_x, y + row_h // 2), row_h // 3)
                    except Exception:
                        pass
            else:
                # red 'X'
                cx = status_x
                cy = y + row_h // 2
                s = row_h // 3
                try:
                    color = styles.ERROR_COLOR
                    pygame.draw.line(surface, color, (cx - s, cy - s), (cx + s, cy + s), 2)
                    pygame.draw.line(surface, color, (cx - s, cy + s), (cx + s, cy - s), 2)
                except Exception:
                    pass

        # Render toast message if active
        if self.toast_message:
            elapsed = time.time() - self.toast_time
            if elapsed < 3:  # Show for 3 seconds
                try:
                    toast_font = fonts.get('content', table_font)
                    toast_text = toast_font.render(self.toast_message, True, styles.OK_COLOR)
                    toast_rect = toast_text.get_rect()
                    toast_x = rect.centerx - toast_rect.width // 2
                    toast_y = rect.bottom - 60
                    # Draw semi-transparent background
                    bg_rect = pygame.Rect(toast_x - 12, toast_y - 4, toast_rect.width + 24, toast_rect.height + 8)
                    toast_surface = pygame.Surface((bg_rect.width, bg_rect.height))
                    toast_surface.set_alpha(200)
                    toast_surface.fill((20, 20, 20))
                    surface.blit(toast_surface, bg_rect.topleft)
                    # Draw text
                    surface.blit(toast_text, (toast_x, toast_y))
                except Exception:
                    pass
            else:
                self.toast_message = None
