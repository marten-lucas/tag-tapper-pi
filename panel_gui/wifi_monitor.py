"""WiFi Band Steering and Fast Roaming Monitor.

Tracks:
  - Current connected SSID
  - Frequency band (2.4 GHz, 5 GHz, 6 GHz)
  - Access point MAC address
  - Band/AP transitions (for bandsteering and roaming detection)
"""

import subprocess
import threading
import time
import re
from collections import deque


class WiFiMonitor:
    def __init__(self, interface='wlan0', history_size=20):
        self._lock = threading.Lock()
        self.interface = interface
        self.history_size = history_size
        
        # Current state
        self.connected_ssid = None
        self.frequency_ghz = None  # e.g., 2.4, 5.0, 6.0
        self.ap_mac = None
        self.signal_dbm = None
        self.link_speed = None  # Mbps
        
        # History for detecting transitions
        self.state_history = deque(maxlen=history_size)
        self.last_transition = None  # time of last band/AP change
        self.transition_count = 0
        
        # Monitor thread
        self.stop_event = threading.Event()
        self.update_interval = 3
        t = threading.Thread(target=self._monitor_loop, daemon=True)
        t.start()
    
    def _monitor_loop(self):
        """Background thread monitoring WiFi state."""
        while not self.stop_event.is_set():
            self._update_wifi_state()
            self.stop_event.wait(self.update_interval)
    
    def _update_wifi_state(self):
        """Query current WiFi connection state."""
        try:
            # Get connection info using iw/iwconfig
            ssid = self._get_ssid()
            freq_ghz = self._get_frequency()
            ap_mac = self._get_ap_mac()
            signal_dbm = self._get_signal_level()
            link_speed = self._get_link_speed()
            
            now = time.time()
            
            with self._lock:
                # Track transitions
                old_state = (self.connected_ssid, self.frequency_ghz, self.ap_mac)
                new_state = (ssid, freq_ghz, ap_mac)
                
                # Check if band or AP changed
                band_changed = (self.frequency_ghz != freq_ghz and freq_ghz is not None)
                ap_changed = (self.ap_mac != ap_mac and ap_mac is not None)
                
                if band_changed or ap_changed:
                    self.last_transition = now
                    self.transition_count += 1
                
                # Update current state
                self.connected_ssid = ssid
                self.frequency_ghz = freq_ghz
                self.ap_mac = ap_mac
                self.signal_dbm = signal_dbm
                self.link_speed = link_speed
                
                # Record in history
                self.state_history.append({
                    'timestamp': now,
                    'ssid': ssid,
                    'freq_ghz': freq_ghz,
                    'ap_mac': ap_mac,
                    'signal_dbm': signal_dbm,
                    'band_changed': band_changed,
                    'ap_changed': ap_changed
                })
        except Exception:
            pass
    
    def _get_ssid(self):
        """Get connected SSID via iwgetid."""
        try:
            out = subprocess.check_output(
                ['iwgetid', self.interface, '-r'],
                stderr=subprocess.DEVNULL,
                timeout=2
            ).decode('utf-8').strip()
            return out if out else None
        except Exception:
            return None
    
    def _get_frequency(self):
        """Get current frequency in GHz via iw link."""
        try:
            out = subprocess.check_output(
                ['iw', self.interface, 'link'],
                stderr=subprocess.DEVNULL,
                timeout=2
            ).decode('utf-8')
            
            # Look for "freq: 2437 MHz" or similar
            match = re.search(r'freq: (\d+)\s*MHz', out)
            if match:
                freq_mhz = int(match.group(1))
                # Convert MHz to GHz and determine band
                if 2400 <= freq_mhz < 2500:
                    return 2.4
                elif 5000 <= freq_mhz < 6000:
                    return 5.0
                elif 6000 <= freq_mhz < 7000:
                    return 6.0
            return None
        except Exception:
            return None
    
    def _get_ap_mac(self):
        """Get AP MAC address via iw link."""
        try:
            out = subprocess.check_output(
                ['iw', self.interface, 'link'],
                stderr=subprocess.DEVNULL,
                timeout=2
            ).decode('utf-8')
            
            # Look for "Connected to XX:XX:XX:XX:XX:XX"
            match = re.search(r'Connected to ([0-9a-fA-F:]{17})', out)
            if match:
                return match.group(1)
            return None
        except Exception:
            return None
    
    def _get_signal_level(self):
        """Get signal level in dBm via iw link."""
        try:
            out = subprocess.check_output(
                ['iw', self.interface, 'link'],
                stderr=subprocess.DEVNULL,
                timeout=2
            ).decode('utf-8')
            
            # Look for "signal: -50 dBm" or similar
            match = re.search(r'signal:\s*(-?\d+)\s*dBm', out)
            if match:
                return int(match.group(1))
            return None
        except Exception:
            return None
    
    def _get_link_speed(self):
        """Get link speed in Mbps via iw link."""
        try:
            out = subprocess.check_output(
                ['iw', self.interface, 'link'],
                stderr=subprocess.DEVNULL,
                timeout=2
            ).decode('utf-8')
            
            # Look for "tx bitrate: 65.0 MBit/s" or similar
            match = re.search(r'tx bitrate:\s*([\d.]+)\s*MBit/s', out)
            if match:
                return float(match.group(1))
            return None
        except Exception:
            return None
    
    def get_state(self):
        """Get current WiFi state as dict."""
        with self._lock:
            return {
                'ssid': self.connected_ssid,
                'frequency_ghz': self.frequency_ghz,
                'ap_mac': self.ap_mac,
                'signal_dbm': self.signal_dbm,
                'link_speed': self.link_speed,
                'last_transition': self.last_transition,
                'transition_count': self.transition_count
            }
    
    def get_history(self, limit=10):
        """Get recent state transitions."""
        with self._lock:
            history = list(self.state_history)
        
        # Filter to transitions only
        transitions = [h for h in history if h['band_changed'] or h['ap_changed']]
        return transitions[-limit:]
    
    def get_summary(self):
        """Get human-readable summary of current state."""
        state = self.get_state()
        
        lines = []
        if state['ssid']:
            lines.append(f"SSID: {state['ssid']}")
        else:
            lines.append("Nicht verbunden")
            return lines
        
        # Band info
        if state['frequency_ghz']:
            band_str = f"{state['frequency_ghz']:.1f} GHz"
            lines.append(f"Band: {band_str}")
        
        # AP info
        if state['ap_mac']:
            lines.append(f"AP: {state['ap_mac']}")
        
        # Signal info
        if state['signal_dbm'] is not None:
            lines.append(f"Signal: {state['signal_dbm']} dBm")
        
        # Speed info
        if state['link_speed'] is not None:
            lines.append(f"Speed: {state['link_speed']:.0f} Mbps")
        
        # Roaming info
        if state['last_transition'] is not None:
            elapsed = time.time() - state['last_transition']
            if elapsed < 30:
                if elapsed < 5:
                    lines.append(f"🔄 Kürzlich gewechselt")
                else:
                    lines.append(f"Letzter Wechsel: {int(elapsed)}s")
        
        if state['transition_count'] > 0:
            lines.append(f"Wechsel: {state['transition_count']}x")
        
        return lines
