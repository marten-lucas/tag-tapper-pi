"""
Shared config loader that merges base config with user overrides.
Used by all services to ensure consistency.
"""
import os
import yaml
from pathlib import Path

# Determine repo root (directory of this file)
# config.yaml lives in the same repository root alongside this config_loader.py
REPO_ROOT = Path(__file__).parent
BASE_CONFIG_PATH = REPO_ROOT / "config.yaml"
OVERRIDE_CONFIG_PATH = Path("/mnt/dietpi_userdata/config_overrides.yaml")


def load_base_config():
    """Load the base configuration."""
    if not BASE_CONFIG_PATH.exists():
        raise FileNotFoundError(f"Base config not found: {BASE_CONFIG_PATH}")
    
    with open(BASE_CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f) or {}


def load_user_overrides():
    """Load user-specific configuration overrides."""
    if not OVERRIDE_CONFIG_PATH.exists():
        return {}
    
    try:
        with open(OVERRIDE_CONFIG_PATH, 'r') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Warning: Could not load overrides: {e}")
        return {}


def merge_configs(base, overrides):
    """
    Recursively merge override config into base config.
    Override values take precedence.
    """
    if not isinstance(base, dict) or not isinstance(overrides, dict):
        return overrides if overrides is not None else base
    
    result = base.copy()
    for key, value in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_configs(result[key], value)
        else:
            result[key] = value
    
    return result


def load_config():
    """Load and merge config with overrides. Returns merged config."""
    base = load_base_config()
    overrides = load_user_overrides()
    return merge_configs(base, overrides)
