#!/usr/bin/env python3
"""Touch screen calibration tool for tag-tapper-pi."""
import logging
import os
import struct
import threading
import yaml
from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Container

TOUCH_PATH = "/dev/input/by-path/platform-3f204000.spi-cs-1-event"
CONFIG_FILE = "/home/dietpi/tag-tapper-pi/config.yaml"

logging.basicConfig(filename='/tmp/touch_calibration.log', level=logging.INFO, format='%(asctime)s - %(message)s')

class TouchCalibrationApp(App):
    CSS = """
    Screen { 
        background: #000000; 
        layers: base overlay;
    }
    #container { 
        width: 100%; 
        height: 100%; 
        border: heavy #00ff00;
    }
    #alignment { 
        width: 70%; 
        height: 70%; 
        background: #00000099;
        content-align: center middle;
        text-align: center;
        color: #00ff00;
        offset: 15% 15%;
    }
    .target { 
        width: 8; 
        height: 4; 
        background: #ff0000; 
        color: #ffff00; 
        content-align: center middle; 
        text-align: center; 
        text-style: bold; 
        border: heavy #ffff00; 
        layer: overlay;
    }
    #instructions { 
        width: 90%; 
        height: 4;
        background: #001133; 
        color: #00ff00; 
        text-align: center;
        offset: 5% 90%;
        layer: overlay;
    }
    """
    
    def __init__(self):
        super().__init__()
        self.calibration_points = [(40,40,"1"), (440,40,"2"), (240,160,"3"), (40,280,"4"), (440,280,"5")]
        self.current_point = 0
        self.raw_touches = []
        self.touch_monitor = None
        self.alignment_mode = True
        
    def compose(self) -> ComposeResult:
        # Container with green border (full screen)
        yield Container(id="container")
        
        # Create 5 targets (positioned after mount based on screen size)
        for i, (_, _, label) in enumerate(self.calibration_points):
            target = Static(f"   {label}   ", classes="target", id=f"target_{i}")
            yield target
        
        # Alignment text in center (inside the bordered area)
        yield Static(
            "\n\nDISPLAY & POSITION CHECK\n\n"
            "Green border = full display\n"
            "Red boxes = 5 calibration points\n\n"
            "Touch to start calibration",
            id="alignment"
        )
        
        # Instructions near bottom (overlay)
        yield Static(
            "STEP 1: Visual Check - Touch to continue",
            id="instructions"
        )
    
    def on_mount(self) -> None:
        # Place targets precisely using current screen cell size
        self._place_targets()
        # Start touch monitor
        self.touch_monitor = threading.Thread(target=self._monitor_touch, daemon=True)
        self.touch_monitor.start()

    def _place_targets(self) -> None:
        """Place the 5 targets in the four corners and center based on screen size (cells)."""
        width = self.size.width
        height = self.size.height
        # Target cell size from CSS
        target_w = 8
        target_h = 4
        # Margin inside the green border
        mx = 2
        my = 1
        positions = [
            (mx, my),  # top-left
            (max(width - target_w - mx, mx), my),  # top-right
            ((width - target_w) // 2, (height - target_h) // 2),  # center
            (mx, max(height - target_h - my, my)),  # bottom-left
            (max(width - target_w - mx, mx), max(height - target_h - my, my))  # bottom-right
        ]
        for i, (ox, oy) in enumerate(positions):
            try:
                t = self.query_one(f"#target_{i}")
                t.styles.offset = (ox, oy)
            except Exception:
                pass
    
    def start_calibration(self):
        self.alignment_mode = False
        # Remove alignment text, keep targets
        try:
            alignment = self.query_one("#alignment")
            alignment.remove()
        except:
            pass
        # Update instructions
        instructions = self.query_one("#instructions")
        instructions.update(f"Touch target 1/5 (top-left)")
        # Highlight first target
        self.highlight_current_target()

    def highlight_current_target(self):
        """Make current target flash/stand out."""
        if self.current_point >= len(self.calibration_points):
            return
        # Make current target brighter
        for i in range(len(self.calibration_points)):
            try:
                target = self.query_one(f"#target_{i}")
                if i == self.current_point:
                    target.styles.background = "#ff0000"
                    target.styles.border = ("heavy", "#ffff00")
                else:
                    target.styles.background = "#660000"
                    target.styles.border = ("round", "#666600")
            except:
                pass
    
    def update_after_touch(self):
        """Update UI after a touch is recorded."""
        instructions = self.query_one("#instructions")
        instructions.update(f"Touch target {self.current_point+1}/5")
        self.highlight_current_target()
        
    def _monitor_touch(self):
        try:
            with open(TOUCH_PATH, 'rb') as f:
                logging.info("Touch monitor started")
                touch_x = touch_y = None
                while True:
                    data = f.read(24)
                    if data and len(data) >= 24:
                        try:
                            sec, usec, etype, code, value = struct.unpack("llHHi", data[:24])
                            if etype == 3:
                                if code == 0: touch_x = value
                                elif code == 1: touch_y = value
                            elif etype == 1 and code == 330 and value == 1:
                                if touch_x is not None and touch_y is not None:
                                    # First touch exits alignment mode
                                    if self.alignment_mode:
                                        logging.info("Starting calibration")
                                        self.call_from_thread(self.start_calibration)
                                        import time; time.sleep(0.5)
                                        continue
                                    # Otherwise record calibration point
                                    if self.current_point < len(self.calibration_points):
                                        sx, sy, lbl = self.calibration_points[self.current_point]
                                        self.raw_touches.append((touch_x, touch_y, sx, sy))
                                        logging.info(f"Point {self.current_point+1}: Raw=({touch_x},{touch_y}) -> Screen=({sx},{sy})")
                                        self.current_point += 1
                                        if self.current_point < len(self.calibration_points):
                                            self.call_from_thread(self.update_after_touch)
                                            import time; time.sleep(0.5)
                                        else:
                                            self.call_from_thread(self.complete_calibration)
                                            break
                        except Exception as e:
                            logging.error(f"Parse error: {e}")
        except Exception as e:
            logging.error(f"Monitor error: {e}")
    
    def complete_calibration(self):
        if len(self.raw_touches) < 5:
            return
        raw_x = [r[0] for r in self.raw_touches]
        raw_y = [r[1] for r in self.raw_touches]
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = yaml.safe_load(f) or {}
        except:
            config = {}
        config['touch_calibration'] = {
            'raw_x_min': int(min(raw_x)), 'raw_x_max': int(max(raw_x)),
            'raw_y_min': int(min(raw_y)), 'raw_y_max': int(max(raw_y)),
            'screen_width': 480, 'screen_height': 320,
            'calibration_points': [{'raw_x': int(r[0]), 'raw_y': int(r[1]), 'screen_x': int(r[2]), 'screen_y': int(r[3])} for r in self.raw_touches]
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            logging.info(f"Saved to {CONFIG_FILE}: X={min(raw_x)}-{max(raw_x)}, Y={min(raw_y)}-{max(raw_y)}")
        except Exception as e:
            logging.error(f"Save error: {e}")
        # Show all targets as green
        for i in range(len(self.calibration_points)):
            try:
                target = self.query_one(f"#target_{i}")
                target.styles.background = "#00ff00"
                target.styles.color = "#000000"
                target.styles.border = ("heavy", "#00ff00")
            except:
                pass
        instructions = self.query_one("#instructions")
        instructions.update(f"Calibration Complete!\n\nSaved to config.yaml | Press Ctrl+C to exit")

if __name__ == "__main__":
    TouchCalibrationApp().run()
