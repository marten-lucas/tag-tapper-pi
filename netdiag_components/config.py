import yaml
from pathlib import Path

CONFIG_PATH = Path("config.yaml")

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError("config.yaml nicht gefunden")

    with CONFIG_PATH.open() as f:
        cfg = yaml.safe_load(f) or {}

    cfg.setdefault("vlans", [])
    cfg.setdefault("external_pings", [])
    cfg.setdefault("wifi", {})

    return cfg
