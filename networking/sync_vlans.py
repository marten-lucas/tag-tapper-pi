#!/usr/bin/env python3
"""
Sync VLAN interfaces with config.yaml.
Creates subinterfaces named <base_if>.<vlan_id> with the configured IP (assumes /24 if no prefix).
Deletes existing <base_if>.* interfaces that don't exist in config.

Usage: run as root.
"""
import os
import sys
import subprocess
import yaml

# Determine repository/config paths. Allow overrides via environment variables
# Priority:
# 1) VLAN_CONFIG - full path to config.yaml
# 2) REPO_DIR or TAGTAPPER_REPO - base repo directory containing config.yaml
# 3) fallback: infer REPO_DIR relative to this script (works when running from repo)
env_repo = os.environ.get('REPO_DIR') or os.environ.get('TAGTAPPER_REPO')
if env_repo:
    REPO_DIR = env_repo
else:
    REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG = os.environ.get('VLAN_CONFIG') or os.path.join(REPO_DIR, 'config.yaml')
print('VLAN sync: using config file:', CONFIG)

DEFAULT_PREFIX = 24


def run(cmd):
    print('RUN:', ' '.join(cmd))
    try:
        subprocess.check_call(cmd)
        return 0
    except subprocess.CalledProcessError as e:
        print('Command failed:', e)
        return e.returncode


def iface_exists(name):
    try:
        subprocess.check_output(['ip', 'link', 'show', name], stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False
    except FileNotFoundError:
        print('ip command not found')
        sys.exit(1)


def get_all_interfaces():
    out = subprocess.check_output(['ip', '-o', 'link', 'show']).decode('utf-8')
    names = []
    for line in out.splitlines():
        parts = line.split(':', 2)
        if len(parts) >= 2:
            names.append(parts[1].strip().split('@')[0])
    return names


def choose_base_interface():
    # Prefer eth0, then first non-loopback non-wlan
    if iface_exists('eth0'):
        return 'eth0'
    names = get_all_interfaces()
    for n in names:
        if n == 'lo':
            continue
        if n.startswith('wlan') or n.startswith('wl'):
            continue
        return n
    # fallback
    return 'eth0'


def load_config():
    with open(CONFIG, 'r') as f:
        return yaml.safe_load(f) or {}


def parse_ip_cidr(ip):
    # If already contains '/', return as-is
    if '/' in ip:
        return ip
    return f"{ip}/{DEFAULT_PREFIX}"


def main():
    cfg = load_config()
    vlans = cfg.get('vlans', [])
    desired_ids = set()
    desired_map = {}
    for v in vlans:
        vid = str(v.get('id'))
        desired_ids.add(vid)
        desired_map[vid] = v

    base_if = os.environ.get('VLAN_BASE_IF') or choose_base_interface()
    print('Using base interface:', base_if)

    # Ensure base interface exists
    if not iface_exists(base_if):
        print(f'Base interface {base_if} does not exist. Aborting.')
        sys.exit(1)

    # Create or update desired VLANs
    for vid in sorted(desired_ids, key=int):
        name = f"{base_if}.{vid}"
        if iface_exists(name):
            print(f'Interface {name} exists, skipping creation')
        else:
            print(f'Creating VLAN interface {name} on {base_if} (id {vid})')
            run(['ip', 'link', 'add', 'link', base_if, 'name', name, 'type', 'vlan', 'id', vid])
            run(['ip', 'link', 'set', name, 'up'])
        # Assign IP if provided in config (static IP). If missing, interface will use DHCP
        ip = desired_map[vid].get('ip')
        if ip:
            print(f'Assigning static IP {ip} to {name}')
            cidr = parse_ip_cidr(ip)
            # Remove existing addresses on this interface first
            try:
                run(['ip', 'addr', 'flush', 'dev', name])
            except Exception:
                pass
            run(['ip', 'addr', 'add', cidr, 'dev', name])
        else:
            print(f'No static IP configured for {name}, will use DHCP if available')

    # Delete interfaces that match base_if.* but not desired
    existing = get_all_interfaces()
    for ifname in existing:
        if ifname.startswith(base_if + '.'):
            parts = ifname.split('.')
            if len(parts) >= 2:
                vid = parts[-1]
                if vid not in desired_ids:
                    print(f'Deleting interface {ifname} (no config entry)')
                    try:
                        run(['ip', 'link', 'delete', ifname])
                    except Exception as e:
                        print('Failed to delete', ifname, e)

    print('VLAN sync complete')


if __name__ == '__main__':
    main()
