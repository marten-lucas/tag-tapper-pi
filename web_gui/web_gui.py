#!/usr/bin/env python3
"""
Simple Flask-based web GUI for editing config.yaml
User-specific changes are saved to /mnt/dietpi_userdata/config_overrides.yaml
"""

import os
import sys
import logging
from pathlib import Path
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# Add parent to path for imports
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from config_loader import load_base_config, load_user_overrides, merge_configs, load_config, OVERRIDE_CONFIG_PATH

# Configuration paths
CONFIG_PATH = os.path.join(REPO_ROOT, "config.yaml")
USERDATA_DIR = "/mnt/dietpi_userdata"
REPORT_DIR_NAME = "tag-tapper-pi-reports"

# Ensure userdata directory exists
os.makedirs(USERDATA_DIR, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
def get_effective_config():
    """Get the merged config (base + user overrides)."""
    return load_config()


def save_user_config(config):
    """Save user config to overrides file."""
    try:
        import yaml
        with open(OVERRIDE_CONFIG_PATH, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.info(f"Saved user overrides to {OVERRIDE_CONFIG_PATH}")
        return True
    except Exception as e:
        logger.error(f"Failed to save user config: {e}")
        return False


def deep_update(target, source):
    """Recursively update target dict with source dict values."""
    for key, value in source.items():
        if isinstance(value, dict) and key in target and isinstance(target[key], dict):
            deep_update(target[key], value)
        else:
            target[key] = value
    return target


def get_report_dir():
    """Resolve report directory using config.report_path or repo root."""
    try:
        cfg = load_config()
        base_path = cfg.get("report_path")
    except Exception:
        base_path = None
    if not base_path:
        base_path = REPO_ROOT
    return os.path.join(base_path, REPORT_DIR_NAME)


def ensure_report_dir():
    """Create report directory if missing and return its path."""
    report_dir = get_report_dir()
    try:
        os.makedirs(report_dir, exist_ok=True)
    except Exception:
        pass
    return report_dir


@app.route('/')
def index():
    """Main config editor page."""
    config = get_effective_config()
    return render_template('config_editor.html', config=config)


@app.route('/api/config', methods=['GET'])
def get_config():
    """Get effective config as JSON."""
    config = get_effective_config()
    return jsonify(config)


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update config with user changes."""
    try:
        new_config = request.get_json()
        if not new_config:
            return jsonify({'error': 'No config provided'}), 400
        
        # Load current overrides
        current_overrides = load_user_overrides()
        
        # Merge new changes into overrides
        updated_overrides = deep_update(current_overrides, new_config)
        
        # Save to overrides file
        if save_user_config(updated_overrides):
            return jsonify({'success': True, 'message': 'Config saved successfully'})
        else:
            return jsonify({'error': 'Failed to save config'}), 500
    except Exception as e:
        logger.error(f"Error updating config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/config/reset', methods=['POST'])
def reset_config():
    """Reset user config to base (delete overrides)."""
    try:
        if os.path.exists(OVERRIDE_CONFIG_PATH):
            os.remove(OVERRIDE_CONFIG_PATH)
            logger.info("User config reset to base")
            return jsonify({'success': True, 'message': 'Config reset to base'})
        return jsonify({'success': True, 'message': 'No overrides to reset'})
    except Exception as e:
        logger.error(f"Error resetting config: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({'status': 'ok'}), 200


@app.route('/api/live/ip', methods=['GET'])
def live_ip():
    """Return current interface states and IPs, similar to panel IP tab."""
    import re
    import subprocess
    try:
        cfg = get_effective_config()
    except Exception:
        cfg = {}

    # VLAN name mapping
    vlan_names = {}
    for v in cfg.get('vlans', []):
        try:
            vid = str(v.get('id'))
            name = v.get('name') or ''
            if vid:
                vlan_names[vid] = name
        except Exception:
            pass

    # Enumerate interfaces
    def get_all_interfaces():
        try:
            out = subprocess.check_output(['ip', '-o', 'link', 'show']).decode('utf-8')
            names = []
            for line in out.splitlines():
                parts = line.split(':', 2)
                if len(parts) >= 2:
                    names.append(parts[1].strip().split('@')[0])
            return names
        except Exception:
            return []

    def get_ip_for_iface(iface):
        try:
            out = subprocess.check_output(['ip', '-o', '-4', 'addr', 'show', 'dev', iface]).decode('utf-8')
            m = re.search(r'\binet (\S+)', out)
            if m:
                return m.group(1)
        except subprocess.CalledProcessError:
            return None
        return None

    def iface_is_up(iface):
        try:
            out = subprocess.check_output(['ip', '-o', 'link', 'show', 'dev', iface]).decode('utf-8')
            m = re.search(r'\bstate\s+(\w+)', out)
            if m:
                return m.group(1).upper() == 'UP'
        except subprocess.CalledProcessError:
            return False
        return False

    def get_wifi_ssid(iface):
        try:
            out = subprocess.check_output(['iwgetid', iface, '-r'], stderr=subprocess.DEVNULL).decode('utf-8').strip()
            return out if out else None
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    ifaces = get_all_interfaces()

    # Order: eth0, VLANs by id, then wlan*
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

    items = []
    for iface in candidates:
        ip = get_ip_for_iface(iface)
        up = iface_is_up(iface)
        display_name = iface
        if '.' in iface:
            vid = iface.split('.')[-1]
            if vid in vlan_names and vlan_names[vid]:
                display_name = f"{iface} {vlan_names[vid]}"
        elif iface.startswith('wlan') or iface.startswith('wl'):
            ssid = get_wifi_ssid(iface)
            if ssid:
                ssid_short = ssid[:16] + '…' if len(ssid) > 16 else ssid
                display_name = f"{iface} ({ssid_short})"
        items.append({
            'iface': iface,
            'display_name': display_name,
            'ip': ip if (ip and up) else None,
            'up': up,
        })

    return jsonify({'interfaces': items, 'vlan_names': vlan_names})


@app.route('/api/live/ping', methods=['GET'])
def live_ping():
    """Return ping matrix similar to panel ping tab. Uses parallel ping execution."""
    import subprocess
    import time
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    try:
        cfg = get_effective_config()
    except Exception:
        cfg = {}

    # Build interfaces
    interfaces = []
    if 'eth0' in subprocess.getoutput('ip -o link show'):
        interfaces.append('eth0')
    for v in cfg.get('vlans', []):
        try:
            vid = str(v.get('id'))
            interfaces.append(f"eth0.{vid}")
        except Exception:
            pass
    # Add wlan* interfaces
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

    # Targets
    targets = []
    ping_cfg = cfg.get('pings', {})
    timeout = int(ping_cfg.get('timeout', 2))
    for p in ping_cfg.get('hosts', []):
        host = p.get('host')
        name = p.get('name', host)
        if host:
            targets.append({'host': host, 'name': name})

    def interface_exists(iface):
        try:
            subprocess.check_output(['ip', 'link', 'show', 'dev', iface], stderr=subprocess.DEVNULL)
            return True
        except subprocess.CalledProcessError:
            return False

    def ping_single(iface, host):
        """Ping single host from single interface. Returns (iface, host, reachable)."""
        if not interface_exists(iface):
            return (iface, host, False)
        try:
            result = subprocess.run(
                ['ping', '-I', iface, '-c', '1', '-W', str(timeout), host],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout + 1
            )
            return (iface, host, result.returncode == 0)
        except (subprocess.TimeoutExpired, Exception):
            return (iface, host, False)

    # Collect all ping tasks
    ping_tasks = []
    for iface in interfaces:
        for t in targets:
            ping_tasks.append((iface, t['host']))

    # Execute pings in parallel
    results = {iface: {} for iface in interfaces}
    max_workers = min(20, len(ping_tasks)) if ping_tasks else 1
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(ping_single, iface, host): (iface, host) 
                   for iface, host in ping_tasks}
        
        for future in as_completed(futures):
            iface, host, reachable = future.result()
            results[iface][host] = reachable

    return jsonify({
        'interfaces': interfaces,
        'targets': targets,
        'results': results,
        'timestamp': time.time()
    })


@app.route('/api/reports', methods=['GET'])
def list_reports():
    """List available report files and return their content."""
    report_dir = ensure_report_dir()
    items = []
    try:
        if not os.path.isdir(report_dir):
            return jsonify({'reports': []})

        for entry in os.scandir(report_dir):
            if entry.is_file() and entry.name.endswith('.txt'):
                try:
                    stat = entry.stat()
                    created_ts = stat.st_mtime
                    created_iso = datetime.fromtimestamp(created_ts).isoformat()
                    with open(entry.path, 'r') as f:
                        content = f.read()
                    items.append({
                        'name': entry.name,
                        'created_ts': created_ts,
                        'created_iso': created_iso,
                        'size': stat.st_size,
                        'content': content,
                    })
                except Exception as e:
                    logger.error(f"Failed to read report {entry.name}: {e}")

        items.sort(key=lambda x: x.get('created_ts', 0), reverse=True)
        return jsonify({'reports': items})
    except Exception as e:
        logger.error(f"Error listing reports: {e}")
        return jsonify({'error': 'Failed to list reports'}), 500


@app.route('/api/reports/<path:report_name>', methods=['DELETE'])
def delete_report(report_name):
    """Delete a single report by name."""
    report_dir = ensure_report_dir()
    base = os.path.abspath(report_dir) + os.sep
    target = os.path.abspath(os.path.join(report_dir, report_name))
    if not target.startswith(base):
        return jsonify({'error': 'Invalid report path'}), 400
    if not os.path.isfile(target):
        return jsonify({'error': 'Report not found'}), 404
    try:
        os.remove(target)
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Error deleting report {report_name}: {e}")
        return jsonify({'error': 'Failed to delete report'}), 500


@app.route('/api/reports', methods=['DELETE'])
def delete_all_reports():
    """Delete all report text files."""
    report_dir = ensure_report_dir()
    removed = 0
    try:
        if os.path.isdir(report_dir):
            for entry in os.scandir(report_dir):
                if entry.is_file() and entry.name.endswith('.txt'):
                    try:
                        os.remove(entry.path)
                        removed += 1
                    except Exception as e:
                        logger.error(f"Error deleting report {entry.name}: {e}")
        return jsonify({'success': True, 'removed': removed})
    except Exception as e:
        logger.error(f"Error deleting all reports: {e}")
        return jsonify({'error': 'Failed to delete reports'}), 500


if __name__ == '__main__':
    logger.info(f"Starting Web Config Editor")
    logger.info(f"Base config: {CONFIG_PATH}")
    logger.info(f"User overrides: {OVERRIDE_CONFIG_PATH}")
    # Run on all interfaces, port 5000
    app.run(host='0.0.0.0', port=5000, debug=False)
