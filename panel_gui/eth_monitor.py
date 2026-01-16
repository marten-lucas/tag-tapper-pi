"""Ethernet Link Monitor with DHCP Renewal.

Monitors the carrier state of Ethernet interfaces (eth0) and triggers
DHCP renewal when the link goes down and comes back up.

This ensures that when moving the device between different VLAN switch ports,
the device requests a new IP address from the new network's DHCP server instead
of keeping the old IP from the previous network.
"""

import threading
import time
import logging
import subprocess
import os

logger = logging.getLogger(__name__)


class EthMonitor:
    """Monitor Ethernet link state and trigger DHCP renewal on link changes."""
    
    def __init__(self, interface='eth0', check_interval=0.5):
        """Initialize the Ethernet monitor.
        
        Args:
            interface: Network interface to monitor (default: eth0)
            check_interval: How often to check carrier state in seconds
        """
        self.interface = interface
        self.check_interval = check_interval
        self.carrier_path = f'/sys/class/net/{interface}/carrier'
        self.operstate_path = f'/sys/class/net/{interface}/operstate'
        
        # Track state
        self._lock = threading.Lock()
        self.current_carrier = None
        self.current_ip = None
        self.link_down_time = None
        self.renewal_in_progress = False
        
        # Start monitoring thread
        self.stop_event = threading.Event()
        try:
            t = threading.Thread(target=self._monitor_loop, daemon=True)
            t.start()
            logger.info(f"EthMonitor started for {interface}")
        except Exception as e:
            logger.error(f"Failed to start EthMonitor: {e}")
    
    def _read_carrier(self):
        """Read the carrier state from sysfs. Returns 1 if link up, 0 if down, None if error."""
        try:
            if not os.path.exists(self.carrier_path):
                return None
            with open(self.carrier_path, 'r') as f:
                return int(f.read().strip())
        except (OSError, ValueError):
            # Interface might not exist yet or be down
            return None
    
    def _read_operstate(self):
        """Read the operational state. Returns 'up', 'down', 'unknown', etc."""
        try:
            if not os.path.exists(self.operstate_path):
                return 'unknown'
            with open(self.operstate_path, 'r') as f:
                return f.read().strip().lower()
        except (OSError, ValueError):
            return 'unknown'
    
    def _get_current_ip(self):
        """Get the current IP address of the interface."""
        try:
            out = subprocess.check_output(
                ['ip', '-o', '-4', 'addr', 'show', 'dev', self.interface],
                stderr=subprocess.DEVNULL,
                timeout=2
            ).decode('utf-8')
            
            import re
            m = re.search(r'inet\s+(\S+)', out)
            if m:
                return m.group(1)
        except Exception:
            pass
        return None
    
    def _trigger_dhcp_renewal(self):
        """Trigger DHCP renewal by restarting dhclient for this interface.
        
        This releases the old lease and requests a new one, ensuring we get
        an IP appropriate for the current network/VLAN.
        """
        if self.renewal_in_progress:
            logger.info(f"DHCP renewal already in progress for {self.interface}")
            return
        
        self.renewal_in_progress = True
        try:
            logger.info(f"Triggering DHCP renewal for {self.interface}")
            
            # Kill existing dhclient process for this interface
            try:
                subprocess.run(
                    ['sudo', 'pkill', '-f', f'dhclient.*{self.interface}'],
                    timeout=5
                )
                time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Error killing dhclient: {e}")
            
            # Release the lease (best effort)
            try:
                subprocess.run(
                    ['sudo', 'dhclient', '-r', self.interface],
                    timeout=5,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                time.sleep(0.3)
            except Exception as e:
                logger.warning(f"Error releasing DHCP lease: {e}")
            
            # Request new lease
            try:
                subprocess.run(
                    ['sudo', 'dhclient', '-v', self.interface],
                    timeout=10,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                logger.info(f"DHCP renewal completed for {self.interface}")
            except Exception as e:
                logger.error(f"Error requesting new DHCP lease: {e}")
            
        finally:
            self.renewal_in_progress = False
    
    def _monitor_loop(self):
        """Background thread that monitors link state."""
        # Initial state
        self.current_carrier = self._read_carrier()
        self.current_ip = self._get_current_ip()
        
        if self.current_carrier == 1:
            logger.info(f"{self.interface}: Initial state is UP, IP: {self.current_ip}")
        else:
            logger.info(f"{self.interface}: Initial state is DOWN")
        
        while not self.stop_event.is_set():
            try:
                carrier = self._read_carrier()
                
                with self._lock:
                    prev_carrier = self.current_carrier
                    
                    # Detect state transitions
                    if prev_carrier != carrier:
                        if carrier == 1 and prev_carrier == 0:
                            # Link UP transition
                            operstate = self._read_operstate()
                            down_duration = None
                            if self.link_down_time:
                                down_duration = time.time() - self.link_down_time
                            
                            logger.info(f"{self.interface}: Link UP (was down for {down_duration:.1f}s)" if down_duration else f"{self.interface}: Link UP")
                            
                            # Trigger DHCP renewal when link comes back up
                            # This ensures we get a new IP from the current network/VLAN
                            if down_duration and down_duration > 0.5:  # Only if link was actually down
                                # Wait a moment for the interface to fully come up
                                time.sleep(1)
                                self._trigger_dhcp_renewal()
                            
                            self.link_down_time = None
                            
                        elif carrier == 0 and prev_carrier == 1:
                            # Link DOWN transition
                            prev_ip = self.current_ip
                            logger.info(f"{self.interface}: Link DOWN (had IP: {prev_ip})")
                            self.link_down_time = time.time()
                        
                        self.current_carrier = carrier
                    
                    # Update IP address periodically
                    if carrier == 1:
                        new_ip = self._get_current_ip()
                        if new_ip != self.current_ip:
                            logger.info(f"{self.interface}: IP changed from {self.current_ip} to {new_ip}")
                            self.current_ip = new_ip
                
            except Exception as e:
                logger.error(f"Error in EthMonitor loop: {e}")
            
            self.stop_event.wait(self.check_interval)
    
    def stop(self):
        """Stop the monitoring thread."""
        self.stop_event.set()
        logger.info(f"EthMonitor stopped for {self.interface}")


if __name__ == '__main__':
    # Test the monitor
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    monitor = EthMonitor('eth0')
    try:
        print("Monitoring eth0... (Press Ctrl+C to stop)")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        monitor.stop()
