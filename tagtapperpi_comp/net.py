import asyncio
import subprocess
import logging
import re

log = logging.getLogger(__name__)

ETH = "eth0"

async def run_cmd(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        out, err = await proc.communicate()
        if err:
            log.error(err.decode())
        return proc.returncode, out.decode()
    except Exception as e:
        log.exception(e)
        return 1, ""

async def ensure_vlan(vlan_id: int) -> bool:
    iface = f"{ETH}.{vlan_id}"
    rc, _ = await run_cmd(["ip", "link", "show", iface])
    if rc == 0:
        return True

    await run_cmd([
        "ip", "link", "add", "link", ETH,
        "name", iface, "type", "vlan", "id", str(vlan_id)
    ])
    await run_cmd(["ip", "link", "set", iface, "up"])
    return True

async def get_ip_addresses() -> dict:
    rc, out = await run_cmd(["ip", "-4", "addr"])
    ips = {}
    current = None

    for line in out.splitlines():
        if ": " in line:
            current = line.split(":")[1].strip()
        elif "inet " in line and current:
            ip = line.split()[1].split("/")[0]
            ips[current] = ip

    return ips

async def ping(interface: str, target: str) -> bool:
    rc, _ = await run_cmd([
        "ping", "-I", interface,
        "-c", "1", "-W", "1", target
    ])
    return rc == 0

async def wifi_signal(interface: str) -> int | None:
    rc, out = await run_cmd(["iwconfig", interface])
    if rc != 0:
        return None

    m = re.search(r"Signal level=(-?\d+) dBm", out)
    return int(m.group(1)) if m else None
