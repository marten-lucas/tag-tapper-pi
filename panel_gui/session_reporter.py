import os
import time
import threading
from tagtapperpi_comp.config_loader import load_config


class SessionReporter:
    """Writes a session report on demand with current panel data.

    The report mirrors panel data: IP table and ping matrix.

    Config:
      - In config.yaml, set `report_path: /some/base/path`
        Reports will be saved under `<report_path>/tag-tapper-pi-reports/`.
    """

    def __init__(self, tab_ip, tab_ping):
        self.tab_ip = tab_ip
        self.tab_ping = tab_ping
        self.report_dir = None

        self._load_config()
        self._ensure_report_dir()

    def _load_config(self):
        cfg = load_config()
        base_path = cfg.get("report_path")
        # Fallback: repo root
        if not base_path:
            repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            base_path = repo_root
        self.report_dir = os.path.join(base_path, "tag-tapper-pi-reports")

    def _ensure_report_dir(self):
        try:
            os.makedirs(self.report_dir, exist_ok=True)
        except Exception:
            pass

    def write_report_now(self):
        """Write a report with current panel data."""
        try:
            self._write_report()
        except Exception:
            pass

    def _build_ip_rows(self):
        """Return list of tuples: (display_name, ip_text, status_text)"""
        rows = []
        try:
            with getattr(self.tab_ip, "_lock", threading.Lock()):
                ifaces = list(getattr(self.tab_ip, "cached_ifaces", []))
                vlan_names = dict(getattr(self.tab_ip, "cached_vlan_names", {}))
                ips = dict(getattr(self.tab_ip, "cached_ips", {}))
                ups = dict(getattr(self.tab_ip, "cached_up", {}))
        except Exception:
            ifaces, vlan_names, ips, ups = [], {}, {}, {}

        # Order: eth0, VLANs by id, then wlan*
        candidates = []
        if "eth0" in ifaces:
            candidates.append("eth0")
        vlans = [n for n in ifaces if "." in n]
        def vlan_key(name):
            try:
                return int(name.split(".")[-1])
            except Exception:
                return 0
        for n in sorted(vlans, key=vlan_key):
            candidates.append(n)
        for n in sorted(ifaces):
            if n.startswith("wlan") or n.startswith("wl"):
                if n not in candidates:
                    candidates.append(n)

        for iface in candidates:
            up = bool(ups.get(iface, False))
            ip = ips.get(iface)
            display_name = iface
            if "." in iface:
                vid = iface.split(".")[-1]
                if vid in vlan_names:
                    display_name = f"{iface} {vlan_names[vid]}"
            elif iface.startswith("wlan") or iface.startswith("wl"):
                # Try SSID for wifi
                try:
                    ssid = self.tab_ip.get_wifi_ssid(iface)
                except Exception:
                    ssid = None
                if ssid:
                    ssid_short = ssid[:16] + "…" if len(ssid) > 16 else ssid
                    display_name = f"{iface} ({ssid_short})"
            ip_text = ip if (ip and up) else "-"
            status_text = "UP" if up else "DOWN"
            rows.append((display_name, ip_text, status_text))
        return rows

    def _build_ping_matrix(self):
        """Return dict: {interface: [(target, ok_bool), ...]}"""
        matrix = {}
        try:
            targets = list(getattr(self.tab_ping, "ping_targets", []))
            results = dict(getattr(self.tab_ping, "ping_results", {}))
        except Exception:
            targets, results = [], {}

        # Collect interfaces present in results
        interfaces = set()
        for (iface, host), ok in results.items():
            interfaces.add(iface)
        # If results are empty, try to infer from TabIP
        if not interfaces:
            try:
                with getattr(self.tab_ip, "_lock", threading.Lock()):
                    ifaces = list(getattr(self.tab_ip, "cached_ifaces", []))
                for n in ifaces:
                    interfaces.add(n)
            except Exception:
                pass

        for iface in sorted(interfaces):
            row = []
            for target in targets:
                host = target.get("host") if isinstance(target, dict) else str(target)
                ok = bool(results.get((iface, host), False))
                row.append((host, ok))
            matrix[iface] = row
        return matrix

    def _write_report(self):
        # Filename: session-YYYYMMDD-HHMMSS.txt based on current time
        now_ts = time.time()
        now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now_ts))
        fname = time.strftime("session-%Y%m%d-%H%M%S.txt", time.localtime(now_ts))
        fpath = os.path.join(self.report_dir, fname)

        ip_rows = self._build_ip_rows()
        ping_matrix = self._build_ping_matrix()

        lines = []
        lines.append("Tag Tapper Pi Session Report")
        lines.append("")
        lines.append(f"Zeitpunkt: {now_str}")
        lines.append("")
        lines.append("IPs:")
        for name, ip, status in ip_rows:
            lines.append(f"  {name:25}  {status:4}  {ip}")
        lines.append("")
        lines.append("Pings:")
        if ping_matrix:
            for iface, items in ping_matrix.items():
                lines.append(f"  [{iface}]")
                for host, ok in items:
                    state = "OK" if ok else "FAIL"
                    lines.append(f"    {host:20} {state}")
        else:
            lines.append("  (keine Ping-Daten)")

        try:
            with open(fpath, "w") as f:
                f.write("\n".join(lines) + "\n")
        except Exception:
            pass
