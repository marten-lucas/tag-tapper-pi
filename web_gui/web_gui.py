#!/usr/bin/env python3
"""
Simple Flask-based web GUI for editing config.yaml
User-specific changes are saved to /mnt/dietpi_userdata/config_overrides.yaml
"""

import os
import sys
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify

# Add parent to path for imports
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from config_loader import load_base_config, load_user_overrides, merge_configs, load_config, OVERRIDE_CONFIG_PATH

# Configuration paths
CONFIG_PATH = os.path.join(REPO_ROOT, "config.yaml")
USERDATA_DIR = "/mnt/dietpi_userdata"

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


if __name__ == '__main__':
    logger.info(f"Starting Web Config Editor")
    logger.info(f"Base config: {CONFIG_PATH}")
    logger.info(f"User overrides: {OVERRIDE_CONFIG_PATH}")
    # Run on all interfaces, port 5000
    app.run(host='0.0.0.0', port=5000, debug=False)
