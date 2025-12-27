import os
import time
import threading
import logging
import struct
import yaml

try:
    from textual.events import Click
    try:
        from evdev import InputDevice, ecodes
    except Exception:
        InputDevice = None
        ecodes = None
except ImportError:
    Click = None


def load_calibration(config_file="/home/dietpi/tag-tapper-pi/config.yaml"):
    """Load touch calibration from config.yaml."""
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f)
            if config and 'touch_calibration' in config:
                calib = config['touch_calibration']
                return {
                    'raw_x_min': calib.get('raw_x_min', 0),
                    'raw_x_max': calib.get('raw_x_max', 4095),
                    'raw_y_min': calib.get('raw_y_min', 0),
                    'raw_y_max': calib.get('raw_y_max', 4095),
                    'screen_width': calib.get('screen_width', 480),
                    'screen_height': calib.get('screen_height', 320),
                }
    except Exception as e:
        logging.getLogger("tagtapper.touch").debug(f"No calibration found: {e}")
    
    # Default uncalibrated values
    return {
        'raw_x_min': 0,
        'raw_x_max': 4095,
        'raw_y_min': 0,
        'raw_y_max': 4095,
        'screen_width': 480,
        'screen_height': 320,
    }


def start_touch_monitor(q, device_path: str, stop_event=None):
    """Start a background thread that reads events from device_path using python-evdev.

    Emits to `q` the same tuples as the original implementation:
      - ('BTN', value)
      - ('POS', x, y, pressure)

    Returns the started Thread. `stop_event` may be a threading.Event to stop the loop.
    """

    def _monitor():
        logger = logging.getLogger("tagtapper.touch")
        calib = load_calibration()
        logger.info(f"Touch calibration loaded: raw_x={calib['raw_x_min']}-{calib['raw_x_max']}, raw_y={calib['raw_y_min']}-{calib['raw_y_max']}")

        if InputDevice is None:
            logger.error('python-evdev not available; cannot monitor touch device')
            return

        try:
            dev = InputDevice(device_path)
            logger.info(f"Opened touch device {device_path} ({dev.name})")
        except Exception as e:
            logger.error(f"Failed to open touch device {device_path}: {e}")
            return

        cur_x = None
        cur_y = None
        cur_pressure = 0

        try:
            for ev in dev.read_loop():
                if stop_event is not None and stop_event.is_set():
                    break
                try:
                    if ev.type == ecodes.EV_ABS:
                        if ev.code in (ecodes.ABS_X, ecodes.ABS_MT_POSITION_X):
                            cur_x = ev.value
                        elif ev.code in (ecodes.ABS_Y, ecodes.ABS_MT_POSITION_Y):
                            cur_y = ev.value
                        elif ev.code == ecodes.ABS_PRESSURE:
                            cur_pressure = ev.value
                    elif ev.type == ecodes.EV_KEY and ev.code == ecodes.BTN_TOUCH:
                        q.put(('BTN', ev.value))
                    elif ev.type == ecodes.EV_SYN:
                        # On SYN_REPORT, push current position
                        q.put(('POS', cur_x, cur_y, cur_pressure))
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"Touch monitor loop error: {e}")

    thread = threading.Thread(target=_monitor, daemon=True)
    thread.start()
    return thread


def _post_click(app, x: int, y: int):
    """Find and activate widget at touch coordinates."""
    logger = logging.getLogger("tagtapper.touch")
    try:
        # If Y < 80 (approximately tab area), try to activate a tab based on X position
        if y < 80:
            try:
                from textual.widgets import Tab, Tabs
                # Get all tabs
                tabs_widget = app.query_one(Tabs)
                all_tabs = list(app.query(Tab))
                
                if all_tabs:
                    # Log all tab IDs for debugging
                    tab_ids = [t.id for t in all_tabs]
                    logger.debug(f"Available tabs: {tab_ids}")
                    
                    # Display width is 480, but let's use more forgiving boundaries
                    # Tabs: IP (0), Ping (1), Range (2), Power (3)
                    # Adjusted boundaries to account for calibration issues
                    if x < 100:  # Far left
                        tab_index = 0  # IP
                    elif x < 220:  # Left-center
                        tab_index = 1  # Ping
                    elif x < 340:  # Right-center
                        tab_index = 2  # Range
                    else:  # Far right
                        tab_index = 3  # Power
                    
                    tab_index = min(tab_index, len(all_tabs) - 1)
                    selected_tab = all_tabs[tab_index]
                    logger.info(f"Touch at X={x} Y={y} -> Activating tab {tab_index}: {selected_tab.label}")
                    
                    # Activate the tab
                    tabs_widget.active = selected_tab.id
                    return
            except Exception as e:
                logger.error(f"Error activating tab: {e}")
        
        # For other areas, try to get widget at position
        try:
            widget, _ = app.screen.get_widget_at(x, y)
            if widget:
                logger.info(f"Touch at X={x} Y={y} -> Widget: {widget.__class__.__name__}")
                
                # Try to click/press the widget
                if hasattr(widget, 'press'):
                    widget.press()
                elif Click is not None:
                    event = Click(
                        widget=widget,
                        x=x,
                        y=y,
                        delta_x=0,
                        delta_y=0,
                        button=1,
                        shift=False,
                        meta=False,
                        ctrl=False
                    )
                    widget.post_message(event)
            else:
                logger.debug(f"No widget at X={x} Y={y}")
        except Exception as e:
            logger.debug(f"Error getting widget: {e}")
            
    except Exception as e:
        logger.error(f"Error in _post_click: {e}")
