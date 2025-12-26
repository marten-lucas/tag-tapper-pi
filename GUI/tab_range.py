import os
import re
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


class TabRange:
    def __init__(self):
        self._lock = threading.Lock()
        self.signal_strengths = {}  # {ssid: signal_percent}
        self.connected_ssid = None
        self.last_update = None
        self.interface = 'wlan0'
        self.update_interval = 5
        self.target_ssids = []
        
        # Load initial config
        self.refresh_config()
        
        # Start scanning thread
        self.stop_event = threading.Event()
        self.is_active = False  # Only scan when tab is visible
        t = threading.Thread(target=self._scan_loop, daemon=True)
        t.start()
    
    def set_active(self, active):
        """Called when tab becomes visible/hidden."""
        self.is_active = active
    
    def refresh_config(self):
        """Load scanning config from config.yaml."""
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg_path = os.path.join(repo, 'config.yaml')
        
        if not yaml:
            return
        
        try:
            with open(cfg_path, 'r') as f:
                cfg = yaml.safe_load(f) or {}
            
            scanner_cfg = cfg.get('range_scanner', {})
            self.interface = scanner_cfg.get('interface', 'wlan0')
            self.update_interval = scanner_cfg.get('update_interval', 5)
            
            # Get target SSIDs
            ssids = []
            for s in scanner_cfg.get('ssid', []):
                name = s.get('name')
                if name:
                    ssids.append(name)
            
            with self._lock:
                self.target_ssids = ssids
        
        except Exception:
            pass
    
    def _scan_loop(self):
        """Background thread that periodically scans for WiFi networks."""
        while not self.stop_event.is_set():
            # Only scan when tab is active to save resources
            if self.is_active:
                self.refresh_config()
                signals = {}
                
                # Get currently connected SSID
                connected = self._get_connected_ssid()
                
                # Scan for networks
                networks = self._scan_networks()
                
                # Extract signal strength for target SSIDs
                for ssid in self.target_ssids:
                    if ssid in networks:
                        signals[ssid] = networks[ssid]
                    else:
                        signals[ssid] = 0  # Not visible
                
                # Update cache
                with self._lock:
                    self.signal_strengths = signals
                    self.connected_ssid = connected
                    self.last_update = time.time()
            
            # Wait for next update cycle
            self.stop_event.wait(self.update_interval)
    
    def _get_connected_ssid(self):
        """Get the SSID of currently connected network."""
        try:
            out = subprocess.check_output(['iwgetid', self.interface, '-r'],
                                        stderr=subprocess.DEVNULL).decode('utf-8').strip()
            return out if out else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None
    
    def _scan_networks(self):
        """Scan for WiFi networks and return {ssid: signal_percent}."""
        networks = {}
        
        try:
            # Use iwlist scan to get network information
            out = subprocess.check_output(['sudo', 'iwlist', self.interface, 'scan'],
                                        stderr=subprocess.DEVNULL,
                                        timeout=10).decode('utf-8')
            
            # Parse iwlist output
            current_ssid = None
            current_quality = None
            
            for line in out.splitlines():
                line = line.strip()
                
                # Extract SSID
                if 'ESSID:' in line:
                    match = re.search(r'ESSID:"([^"]+)"', line)
                    if match:
                        current_ssid = match.group(1)
                
                # Extract signal quality
                elif 'Quality=' in line:
                    # Format: Quality=70/100  Signal level=-40 dBm
                    match = re.search(r'Quality=(\d+)/(\d+)', line)
                    if match:
                        quality = int(match.group(1))
                        max_quality = int(match.group(2))
                        current_quality = int((quality / max_quality) * 100)
                    else:
                        # Alternative: parse signal level in dBm
                        match = re.search(r'Signal level[=:](-?\d+)', line)
                        if match:
                            signal_dbm = int(match.group(1))
                            current_quality = self._dbm_to_percent(signal_dbm)
                
                # Store when we have both SSID and quality
                if current_ssid and current_quality is not None:
                    networks[current_ssid] = current_quality
                    current_ssid = None
                    current_quality = None
        
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return networks
    
    def _dbm_to_percent(self, dbm):
        """Convert dBm signal strength to percentage (0-100)."""
        # Typical WiFi signal range: -90 dBm (weak) to -30 dBm (strong)
        if dbm >= -30:
            return 100
        elif dbm <= -90:
            return 0
        else:
            # Linear interpolation
            return int(((dbm + 90) / 60) * 100)
    
    def draw(self, surface, rect, app, styles, fonts):
        """Draw WiFi signal strength bars."""
        with self._lock:
            signals = dict(self.signal_strengths)
            connected = self.connected_ssid
            ssids = list(self.target_ssids)
            last_update = self.last_update
        
        if not ssids:
            # No SSIDs configured
            msg = fonts['content'].render("Keine SSIDs konfiguriert", True, styles.MUTED_TEXT)
            surface.blit(msg, msg.get_rect(center=(rect.centerx, rect.centery)))
            return
        
        # Use content font for SSID names
        ssid_font = fonts.get('tab_title', fonts['content'])
        label_font = fonts.get('header', fonts['content'])
        
        # Calculate layout
        bar_height = 30
        bar_spacing = 50
        bar_width = rect.width - 80
        start_x = rect.left + 20
        start_y = rect.top + 30
        
        # Draw each SSID with signal bar
        for i, ssid in enumerate(ssids):
            y = start_y + i * bar_spacing
            signal = signals.get(ssid, 0)
            is_connected = (ssid == connected)
            
            # Draw SSID name with connection indicator
            ssid_display = ssid
            if is_connected:
                ssid_display = f"* {ssid}"
            
            ssid_color = styles.TEXT_ACTIVE if is_connected else styles.TEXT_COLOR
            ssid_s = ssid_font.render(ssid_display, True, ssid_color)
            surface.blit(ssid_s, (start_x, y))
            
            # Draw signal strength bar
            bar_y = y + ssid_font.get_height() + 4
            
            # Background bar (gray)
            bar_bg_rect = pygame.Rect(start_x, bar_y, bar_width, bar_height)
            try:
                pygame.draw.rect(surface, styles.NEUTRAL_RING, bar_bg_rect)
            except Exception:
                pass
            
            # Foreground bar (colored based on signal strength)
            # Always draw at least a 1px fill so 0% is visible
            fill_width = max(1, int((signal / 100.0) * bar_width))
            bar_fill_rect = pygame.Rect(start_x, bar_y, fill_width, bar_height)

            # Color gradient: red (weak) -> yellow (medium) -> green (strong)
            if signal >= 70:
                bar_color = styles.OK_COLOR
            elif signal >= 40:
                bar_color = styles.ACCENT_COLOR  # Yellow
            else:
                bar_color = styles.ERROR_COLOR  # Red

            try:
                pygame.draw.rect(surface, bar_color, bar_fill_rect)
            except Exception:
                pass
            
            # Draw signal percentage text on bar
            percent_text = f"{signal}%"
            percent_s = label_font.render(percent_text, True, styles.TEXT_COLOR)
            percent_x = start_x + bar_width + 10
            percent_y = bar_y + (bar_height - label_font.get_height()) // 2
            surface.blit(percent_s, (percent_x, percent_y))
        
        # Show last update time
        if last_update:
            elapsed = time.time() - last_update
            if elapsed < 3:
                # Show "Updated" message for 3 seconds after scan
                try:
                    update_msg = label_font.render("* Gescannt", True, styles.OK_COLOR)
                    update_rect = update_msg.get_rect(bottomright=(rect.right - 20, rect.bottom - 10))
                    surface.blit(update_msg, update_rect)
                except Exception:
                    pass
