import re
import os
import subprocess
import threading
import time
from config_loader import load_config
try:
    import pygame
except Exception:
    pygame = None


class TabIP:
    def __init__(self):
        self._lock = threading.Lock()
        self.cached_ifaces = []
        self.cached_ips = {}
        self.cached_up = {}
        self.cached_gateways = {}
        self.poll_interval = 2  # seconds between refreshes
        # Track previous state for change detection
        self.prev_up = {}
        self.prev_ips = {}
        # Gateway label lookup from config
        self.gateway_labels = self._load_gateway_labels()
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
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        try:
            ifaces = self.get_all_interfaces()
        except Exception:
            ifaces = []
        
        # Query interface info in parallel
        ips = {}
        ups = {}
        gateways = {}
        
        if ifaces:
            def query_interface(iface):
                return (
                    iface,
                    self.get_ip_for_iface(iface),
                    self.iface_is_up(iface),
                    self.get_gateway_for_iface(iface),
                )
            
            max_workers = min(10, len(ifaces))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(query_interface, iface): iface for iface in ifaces}
                
                for future in as_completed(futures):
                    try:
                        iface, ip, up, gw = future.result()
                        ips[iface] = ip
                        ups[iface] = up
                        gateways[iface] = gw
                    except Exception:
                        iface = futures[future]
                        ips[iface] = None
                        ups[iface] = False
                        gateways[iface] = None
        
        # Detect state changes and generate toast messages
        for iface in ups:
            # Skip VLAN interfaces (eth0.x) - only show toasts for physical interfaces
            if '.' in iface:
                continue
                
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
            self.cached_gateways = gateways

    def _load_gateway_labels(self):
        labels = {}
        try:
            cfg = load_config()
            hosts = cfg.get('pings', {}).get('hosts', [])
            for h in hosts:
                try:
                    if h.get('isgateway'):
                        ip = str(h.get('host')).strip()
                        name = h.get('name') or ip
                        labels[ip] = name
                except Exception:
                    pass
        except Exception:
            pass
        return labels
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

    def get_gateway_for_iface(self, iface):
        """Return the IPv4 gateway IP for the given interface if a default route exists."""
        try:
            out = subprocess.check_output(
                ['ip', '-4', 'route', 'show', 'dev', iface, 'default'],
                stderr=subprocess.DEVNULL,
            ).decode('utf-8')
            m = re.search(r'default\s+via\s+(\S+)', out)
            if m:
                return m.group(1)
        except subprocess.CalledProcessError:
            return None
        except Exception:
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
            ips = dict(self.cached_ips)
            ups = dict(self.cached_up)
            gateways = dict(self.cached_gateways)
            gateway_labels = dict(self.gateway_labels)

        # Build ordered candidate list: eth0, then wlan*
        candidates = []
        if 'eth0' in ifaces:
            candidates.append('eth0')

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
            if iface.startswith('wlan') or iface.startswith('wl'):
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

        # Current VLAN / gateway info block under the table
        section_top = start_y + len(candidates) * row_h + 24
        section_rect = pygame.Rect(name_x - 16, section_top, rect.width - 40, (row_h * 2) + 12)
        try:
            pygame.draw.rect(surface, styles.TAB_BG, section_rect)
        except Exception:
            try:
                pygame.draw.rect(surface, styles.NEUTRAL_RING, section_rect)
            except Exception:
                pass

        info_font = fonts.get('content', table_font)
        label_text = None
        vlan_text = None
        active_iface = None

        for iface in candidates:
            if ups.get(iface) and ips.get(iface):
                active_iface = iface
                break

        if active_iface:
            # Build interface label (with SSID if wifi)
            iface_label = active_iface
            if active_iface.startswith('wlan') or active_iface.startswith('wl'):
                ssid = self.get_wifi_ssid(active_iface)
                if ssid:
                    ssid_short = ssid[:16] + '…' if len(ssid) > 16 else ssid
                    iface_label = f"{active_iface} ({ssid_short})"

            label_text = f"Verbunden über: {iface_label}"

            gw_ip = gateways.get(active_iface)
            if gw_ip:
                gw_name = gateway_labels.get(gw_ip)
                if gw_name:
                    vlan_text = f"{gw_name} ({gw_ip})"
                else:
                    vlan_text = f"Gateway unbekannt ({gw_ip})"
            else:
                vlan_text = "Gateway unbekannt"
        else:
            label_text = "Keine Netzwerkverbindung"
            vlan_text = None

        line1_y = section_top + 6
        line2_y = line1_y + row_h

        if label_text:
            lbl_surface = info_font.render(label_text, True, styles.TEXT_COLOR)
            surface.blit(lbl_surface, (name_x, line1_y))
        if vlan_text:
            vlan_surface = info_font.render(vlan_text, True, styles.ACCENT_COLOR)
            surface.blit(vlan_surface, (name_x, line2_y))

        # Render toast message if active
        if self.toast_message:
            elapsed = time.time() - self.toast_time
            if elapsed < 3:  # Show for 3 seconds
                try:
                    styles.draw_toast(surface, rect, fonts, self.toast_message)
                except Exception:
                    pass
            else:
                self.toast_message = None
