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
                if n not in candidates:
                    candidates.append(n)
        # add VLAN-like interfaces (contain a dot)
        for n in sorted(ifaces):
            if '.' in n and n not in candidates:
                candidates.append(n)

        # Prepare drawing positions
        row_h = fonts['content'].get_height() + 8
            candidates = []
            # ensure eth0 present first (if exists)
            if 'eth0' in ifaces:
                candidates.append('eth0')
            # add VLAN-like interfaces (contain a dot) in numeric order by VLAN id
            vlans = [n for n in ifaces if '.' in n]
            # sort by numeric VLAN id if possible
            def vlan_key(name):
                try:
                    return int(name.split('.')[-1])
                except Exception:
                    return 0
            for n in sorted(vlans, key=vlan_key):
                candidates.append(n)
            # add wlan* interfaces at the end
            for n in sorted(ifaces):
                if n.startswith('wlan') or n.startswith('wl'):
                    if n not in candidates:
                        candidates.append(n)
            y = start_y + i * row_h
            ip = self.get_ip_for_iface(iface)
            # Name
            display_name = iface
            if '.' in iface:
                vid = iface.split('.')[-1]
                if vid in vlan_names:
                    display_name = f"{iface} — {vlan_names[vid]}"
            name_s = fonts['content'].render(display_name, True, styles.TEXT_COLOR)
            hdr_name = fonts['content'].render('Schnittstelle', True, styles.TEXT_COLOR)
            hdr_ip = fonts['content'].render('IP', True, styles.TEXT_COLOR)
            hdr_status = fonts['content'].render('OK', True, styles.TEXT_COLOR)
            surface.blit(hdr_name, (name_x, rect.top + 100))
            surface.blit(hdr_ip, (ip_x, rect.top + 100))
            surface.blit(hdr_status, (status_x - 10, rect.top + 100))
            # Status symbol
            if ip:
                sym = '✓'
                color = styles.TEXT_ACTIVE
            else:
                sym = '✗'
                color = (200, 60, 60)
            sym_s = fonts['content'].render(sym, True, color)
            surface.blit(sym_s, sym_s.get_rect(center=(status_x, y + row_h // 2)))

                        display_name = f"{iface} {vlan_names[vid]}"
