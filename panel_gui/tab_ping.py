import os
import subprocess
import threading
import time
try:
    import pygame
except Exception:
    pygame = None
from config_loader import load_config


class TabPing:
    def __init__(self):
        self._lock = threading.Lock()
        self.ping_results = {}  # {(interface, host): bool}
        self.last_update = None
        self.interfaces = []
        self.ping_targets = []
        self.update_interval = 10  # seconds
        self.ping_timeout = 2  # seconds
        self.gateway_map = {}  # {interface: gateway_ip}
        
        # Load initial config
        self.refresh_config()
        
        # Start ping monitor thread
        self.stop_event = threading.Event()
        t = threading.Thread(target=self._ping_loop, daemon=True)
        t.start()

    def refresh_config(self):
        """Load interfaces and ping targets from config.yaml."""
        interfaces = []
        targets = []
        
        try:
            cfg = load_config()
            
            # Get ping monitor settings from pings section
            ping_cfg = cfg.get('pings', {})
            self.update_interval = ping_cfg.get('update_interval', 10)
            self.ping_timeout = ping_cfg.get('timeout', 2)
            
            # Build interface list: eth0, then wlan*
            interfaces.append('eth0')
            
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
            
            # Get ping targets from hosts list
            for p in ping_cfg.get('hosts', []):
                host = p.get('host')
                name = p.get('name', host)
                if host:
                    targets.append({'host': host, 'name': name})
        
        except Exception:
            pass
        
        # Get gateway IPs for each interface
        gateway_map = self._get_gateways(interfaces)
        
        with self._lock:
            self.interfaces = interfaces
            self.ping_targets = targets
            self.gateway_map = gateway_map

    def _get_gateways(self, interfaces):
        """Extract gateway IPs for each interface from ip route output."""
        gateway_map = {}
        try:
            out = subprocess.check_output(['ip', 'route']).decode('utf-8')
            for line in out.splitlines():
                parts = line.split()
                if 'dev' in parts:
                    dev_idx = parts.index('dev')
                    if dev_idx + 1 < len(parts):
                        iface = parts[dev_idx + 1]
                        if iface in interfaces:
                            # Look for 'via' keyword to get gateway IP
                            if 'via' in parts:
                                via_idx = parts.index('via')
                                if via_idx + 1 < len(parts):
                                    gateway = parts[via_idx + 1]
                                    gateway_map[iface] = gateway
        except Exception:
            pass
        return gateway_map

    def _ping_loop(self):
        """Background thread that periodically pings all targets from all interfaces."""
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        while not self.stop_event.is_set():
            self.refresh_config()
            results = {}
            
            # Collect all ping tasks
            ping_tasks = []
            for iface in self.interfaces:
                for target in self.ping_targets:
                    if self._interface_exists(iface):
                        ping_tasks.append((iface, target['host']))
                    else:
                        results.setdefault(iface, {})[target['host']] = False
            
            # Execute pings in parallel
            if ping_tasks:
                max_workers = min(20, len(ping_tasks))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(self._ping, iface, host): (iface, host)
                              for iface, host in ping_tasks}
                    
                    for future in as_completed(futures):
                        iface, host = futures[future]
                        reachable = future.result()
                        results.setdefault(iface, {})[host] = reachable
            
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
            gateway_map = dict(self.gateway_map)
        
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
                reachable = results.get(iface, {}).get(target['host'], False)
                
                # Check if this target is the gateway for this interface
                is_gateway = gateway_map.get(iface) == target['host']
                
                # Draw indicator dot
                dot_x = col_x + 15
                dot_y = y + row_h // 2
                radius = row_h // 4
                
                if reachable:
                    color = styles.OK_COLOR
                else:
                    color = styles.ERROR_COLOR
                
                try:
                    if is_gateway:
                        # Draw gateway with a ring/border style
                        pygame.draw.circle(surface, color, (dot_x, dot_y), radius)
                        pygame.draw.circle(surface, color, (dot_x, dot_y), radius + 2, 2)
                    else:
                        # Regular filled circle
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
