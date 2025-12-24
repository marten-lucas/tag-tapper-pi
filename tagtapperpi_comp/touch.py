import os
import time
import threading
import logging
import struct
import yaml

try:
    from textual.events import Click
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


def start_touch_monitor(app, device_path: str, poll_size: int = 24, debounce: float = 0.3):
    """Start a background thread that reads raw kernel input from `device_path`.
    
    Extracts touch coordinates and posts MouseDown events to the app.
    """

    def _monitor():
        logger = logging.getLogger("tagtapper.touch")
        
        # Load calibration
        calib = load_calibration()
        logger.info(f"Touch calibration loaded: raw_x={calib['raw_x_min']}-{calib['raw_x_max']}, raw_y={calib['raw_y_min']}-{calib['raw_y_max']}")
        
        try:
            if not os.path.exists(device_path):
                logger.error(f"Device nicht gefunden: {device_path}")
                return

            with open(device_path, "rb") as f:
                logger.info(f"Touch-Monitor verbunden mit {device_path}")
                
                # Track latest touch coordinates
                touch_x = None
                touch_y = None
                touch_pressed = False
                
                while True:
                    data = f.read(poll_size)
                    if data and len(data) >= 24:
                        try:
                            # Parse Linux input_event: sec, usec, type, code, value
                            sec, usec, etype, code, value = struct.unpack("llHHi", data[:24])
                            
                            # EV_ABS (type 3): Absolute coordinates
                            if etype == 3:
                                if code == 0:  # ABS_X
                                    # Apply calibration mapping
                                    raw_range = calib['raw_x_max'] - calib['raw_x_min']
                                    if raw_range > 0:
                                        normalized = (value - calib['raw_x_min']) / raw_range
                                        touch_x = int(max(0, min(1, normalized)) * (calib['screen_width'] - 1))
                                    else:
                                        touch_x = int((value / 4095.0) * (calib['screen_width'] - 1))
                                        
                                elif code == 1:  # ABS_Y
                                    # Apply calibration mapping
                                    raw_range = calib['raw_y_max'] - calib['raw_y_min']
                                    if raw_range > 0:
                                        normalized = (value - calib['raw_y_min']) / raw_range
                                        touch_y = int(max(0, min(1, normalized)) * (calib['screen_height'] - 1))
                                    else:
                                        touch_y = int((value / 4095.0) * (calib['screen_height'] - 1))
                            
                            # EV_KEY (type 1): Button press/release
                            elif etype == 1 and code == 330:  # BTN_TOUCH
                                if value == 1 and not touch_pressed:  # Press
                                    touch_pressed = True
                                    if touch_x is not None and touch_y is not None:
                                        # Post Click event with calibrated coordinates
                                        try:
                                            app.call_from_thread(_post_click, app, touch_x, touch_y)
                                            logger.info(f"Touch at X={touch_x} Y={touch_y}")
                                        except Exception as e:
                                            logger.error(f"Failed to post click event: {e}")
                                elif value == 0:  # Release
                                    touch_pressed = False
                            
                            # EV_SYN (type 0): Sync event marks end of event packet
                            elif etype == 0 and code == 0:
                                pass  # Sync - ignore
                                
                        except struct.error as e:
                            logger.debug(f"Parse error: {e}")
                            
                    # Small delay to avoid CPU overload
                    time.sleep(0.01)
                    
        except Exception as e:
            logger.error(f"Kritischer Fehler im Touch-Monitor: {e}")

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
