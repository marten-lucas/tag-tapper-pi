import re
import os
import subprocess
try:
    import yaml
except Exception:
    yaml = None


class TabIP:
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

    def draw(self, surface, rect, app, styles, fonts):
        # Title
        title = fonts['title'].render("Netzwerk", True, styles.TEXT_ACTIVE)
        surface.blit(title, title.get_rect(center=(rect.centerx, rect.top + 60)))

        # Load VLAN names from config.yaml
        vlan_names = self.load_vlan_names()

        # Build list: include untagged eth0, any VLANs (contain '.'), and wlan interfaces
        try:
            ifaces = self.get_all_interfaces()
        except Exception:
            ifaces = []

        candidates = []
        # ensure eth0 present first (if exists)
        if 'eth0' in ifaces:
            candidates.append('eth0')
        # add wlan* interfaces
        for n in sorted(ifaces):
            if n.startswith('wlan') or n.startswith('wl'):
                if n not in candidates:
                    candidates.append(n)
        # add VLAN-like interfaces (contain a dot)
        for n in sorted(ifaces):
            if '.' in n and n not in candidates:
                candidates.append(n)

        # Prepare drawing positions
        row_h = fonts['content'].get_height() + 8
        start_y = rect.top + 120
        name_x = rect.left + 40
        ip_x = rect.right - 260
        status_x = rect.right - 80

        # Header row for table
        hdr_name = fonts['content'].render('Schnittstelle', True, styles.TEXT_COLOR)
        hdr_ip = fonts['content'].render('IP', True, styles.TEXT_COLOR)
        surface.blit(hdr_name, (name_x, rect.top + 100))
        surface.blit(hdr_ip, (ip_x, rect.top + 100))

        # Rows
        for i, iface in enumerate(candidates):
            y = start_y + i * row_h
            ip = self.get_ip_for_iface(iface)
            # Name
            display_name = iface
            if '.' in iface:
                vid = iface.split('.')[-1]
                if vid in vlan_names:
                    display_name = f"{iface} — {vlan_names[vid]}"
            name_s = fonts['content'].render(display_name, True, styles.TEXT_COLOR)
            surface.blit(name_s, (name_x, y))
            # IP (or '-')</n+            ip_text = ip if ip else '-'
            ip_s = fonts['content'].render(ip_text, True, (200, 200, 200))
            surface.blit(ip_s, (ip_x, y))
            # Status symbol
            if ip:
                sym = '✓'
                color = styles.TEXT_ACTIVE
            else:
                sym = '✗'
                color = (200, 60, 60)
            sym_s = fonts['content'].render(sym, True, color)
            surface.blit(sym_s, sym_s.get_rect(center=(status_x, y + row_h // 2)))
