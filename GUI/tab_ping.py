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


class TabPing:
    def __init__(self):
        self._lock = threading.Lock()
        self.ping_results = {}  # {(interface, host): bool}
        self.last_update = None
        self.interfaces = []
        self.ping_targets = []
        self.update_interval = 10  # seconds
        self.ping_timeout = 2  # seconds
        
        # Load initial config
        self.refresh_config()
        
        # Start ping monitor thread
        self.stop_event = threading.Event()
        t = threading.Thread(target=self._ping_loop, daemon=True)
        t.start()

    def refresh_config(self):
        """Load interfaces and ping targets from config.yaml."""
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_path = os.path.join(repo, 'config.yaml')
        
        interfaces = []
        targets = []
        
        if not yaml:
            return
        
        try:
            with open(cfg_path, 'r') as f:
                cfg = yaml.safe_load(f) or {}
            
            # Build interface list: eth0, VLANs, then wlan*
            interfaces.append('eth0')
            
            for v in cfg.get('vlans', []):
                vid = str(v.get('id'))
                interfaces.append(f"eth0.{vid}")
            
            # Add wlan interfaces dynamically (like in tab_ip.py)
            try:
                out = subprocess.check_output(['ip', '-o', 'link', 'show']).decode('utf-8')
                for line in out.splitlines():
                    parts = line.split(':', 2)
                    if len(parts) >= 2:
                        iface = parts[1].strip().split('@')[0]
                        if iface.startswith('wlan') or iface.startswith('wl'):
                            if iface not in interfaces:
                                interfaces.append(iface)
            except Exception:
                pass
            
            # Get ping targets
            for p in cfg.get('pings', []):
                host = p.get('host')
                name = p.get('name', host)
                if host:
                    targets.append({'host': host, 'name': name})
        
        except Exception:
            pass
        
        with self._lock:
            self.interfaces = interfaces
            self.ping_targets = targets

    def _ping_loop(self):
        """Background thread that periodically pings all targets from all interfaces."""
        while not self.stop_event.is_set():
            self.refresh_config()
            results = {}
            
            # Ping each target from each interface
            for iface in self.interfaces:
                for target in self.ping_targets:
                    host = target['host']
                    # Check if interface exists before pinging
                    if self._interface_exists(iface):
                        reachable = self._ping(iface, host)
                    else:
                        reachable = False
                    results[(iface, host)] = reachable
            
            # Update cache
            with self._lock:
                self.ping_results = results
                self.last_update = time.time()
            
            # Wait for next update cycle
            self.stop_event.wait(self.update_interval)

    def _interface_exists(self, iface):
        """Check if interface exists."""
        try:
            subprocess.check_output(['ip', 'link', 'show', 'dev', iface],
                                  stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            return False

    def _ping(self, interface, host):
        """Ping a host from a specific interface with timeout."""
        try:
            result = subprocess.run(
                ['ping', '-I', interface, '-c', '1', '-W', str(self.ping_timeout), host],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=self.ping_timeout + 1
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, Exception):
            return False

    def draw(self, surface, rect, app, styles, fonts):
        """Draw ping matrix table."""
        with self._lock:
            results = dict(self.ping_results)
            targets = list(self.ping_targets)
            interfaces = list(self.interfaces)
            last_update = self.last_update
        
        if not targets:
            # No ping targets configured
            msg = fonts['content'].render("Keine Ping-Ziele konfiguriert", True, styles.MUTED_TEXT)
            surface.blit(msg, msg.get_rect(center=(rect.centerx, rect.centery)))
            return
        
        # Use smaller font for table
        table_font = fonts.get('tab_title', fonts['content'])
        row_h = table_font.get_height() + 6
        
        # Calculate column widths dynamically to fit all interfaces on screen
        name_col_width = 190
        start_x = rect.left + 10
        name_x = start_x
        iface_start_x = name_x + name_col_width
        
        # Calculate interface column width based on available space and number of interfaces
        available_width = rect.width - name_col_width - 40  # Leave margin
        num_ifaces = len(interfaces)
        iface_col_width = min(70, available_width // num_ifaces) if num_ifaces > 0 else 70
        
        # Header background
        header_y = rect.top + 12
        header_h = row_h + 6
        header_bg_rect = pygame.Rect(start_x - 10, header_y, rect.width - 20, header_h)
        try:
            pygame.draw.rect(surface, styles.TAB_BG, header_bg_rect)
        except Exception:
            pass
        
        # Header row: "Ziel" + interface names
        hdr_y = header_y + 6
        hdr_target = table_font.render('Ziel', True, styles.TEXT_COLOR)
        surface.blit(hdr_target, (name_x, hdr_y))
        
        # Interface column headers (abbreviated)
        for i, iface in enumerate(interfaces):
            # Abbreviate interface names for header
            if iface == 'eth0':
                iface_abbr = 'eth0'
            elif iface.startswith('eth0.'):
                iface_abbr = iface.replace('eth0.', '')
            elif iface.startswith('wlan'):
                iface_abbr = 'wlan'
            else:
                iface_abbr = iface[:4]
            
            col_x = iface_start_x + i * iface_col_width
            hdr_if = table_font.render(iface_abbr, True, styles.TEXT_COLOR)
            surface.blit(hdr_if, (col_x, hdr_y))
        
        # Data rows
        start_y = rect.top + 50
        for row_idx, target in enumerate(targets):
            y = start_y + row_idx * row_h
            
            # Target name
            name_s = table_font.render(target['name'], True, styles.TEXT_COLOR)
            surface.blit(name_s, (name_x, y))
            
            # Ping results for each interface
            for col_idx, iface in enumerate(interfaces):
                col_x = iface_start_x + col_idx * iface_col_width
                key = (iface, target['host'])
                reachable = results.get(key, False)
                
                # Draw indicator dot
                dot_x = col_x + 15
                dot_y = y + row_h // 2
                radius = row_h // 4
                
                if reachable:
                    color = styles.OK_COLOR
                else:
                    color = styles.ERROR_COLOR
                
                try:
                    pygame.draw.circle(surface, color, (dot_x, dot_y), radius)
                except Exception:
                    pass
        
        # Show last update time
        if last_update:
            elapsed = time.time() - last_update
            if elapsed < 3:
                # Show toast for 3 seconds after update (IP-style)
                try:
                    styles.draw_toast(surface, rect, fonts, "Aktualisiert")
                except Exception:
                    pass
