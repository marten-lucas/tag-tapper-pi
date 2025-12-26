import logging
import os
import sys
import time
import threading
import queue
import mmap
import struct
import yaml
import numpy as np
from collections import deque
from GUI import styles
from GUI import tabs as tabs_module
import subprocess

try:
    import pygame
except Exception as e:
    print("pygame is required. Install with: pip3 install pygame")
    sys.exit(1)

# Touch handling delegated to tagtapperpi_comp/touch.py which uses python-evdev

TOUCH_PATH = "/dev/input/by-path/platform-3f204000.spi-cs-1-event"
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag-tapper-pi.log")

# Configure logging to file only
try:
    logdir = os.path.dirname(LOG_PATH)
    if logdir and not os.path.exists(logdir):
        os.makedirs(logdir, exist_ok=True)
    logging.basicConfig(
        filename=LOG_PATH,
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
except PermissionError:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='%(asctime)s - %(message)s')


def get_fb_size(fbdev='/dev/fb1'):
    """Get framebuffer size from sysfs."""
    try:
        base = '/sys/class/graphics/' + os.path.basename(fbdev)
        vs = os.path.join(base, 'virtual_size')
        if os.path.exists(vs):
            with open(vs, 'r') as f:
                s = f.read().strip()
            w, h = s.split(',') if ',' in s else s.split('x')
            return int(w), int(h)
        modes = os.path.join(base, 'modes')
        if os.path.exists(modes):
            with open(modes, 'r') as f:
                line = f.readline().strip()
            if line and 'x' in line:
                w, h = line.split('x')[:2]
                return int(w), int(h)
    except Exception as e:
        logging.info(f"Couldn't read fb size: {e}")
    return 800, 480


class FramebufferWriter:
    """Minimal direct framebuffer writer for 16bpp (RGB565) devices."""
    def __init__(self, fbdev='/dev/fb1'):
        self.fbdev = fbdev
        self.width, self.height = get_fb_size(fbdev)
        self.bpp = 16
        self.line_length = self.width * (self.bpp // 8)
        self.fb = open(self.fbdev, 'r+b', buffering=0)
        self.size_bytes = self.line_length * self.height
        self.mm = mmap.mmap(self.fb.fileno(), self.size_bytes, access=mmap.ACCESS_WRITE)
        logging.info(f"Opened framebuffer {self.fbdev} for direct writing")
        logging.info(f"Framebuffer BPP: {self.bpp}")

    def close(self):
        try:
            if self.mm:
                self.mm.flush()
                self.mm.close()
        finally:
            try:
                self.fb.close()
            except Exception:
                pass

    def blit_surface(self, surface):
        """Copy a pygame Surface to the framebuffer as RGB565.

        Assumes surface size matches framebuffer size.
        """
        if surface.get_width() != self.width or surface.get_height() != self.height:
            # Scale to framebuffer size if needed
            surface = pygame.transform.smoothscale(surface, (self.width, self.height))

        # Get RGB bytes (24bpp, row-major)
        rgb_bytes = pygame.image.tostring(surface, 'RGB')
        # Convert to RGB565 (little-endian) using NumPy - vectorized, 10-50x faster
        rgb = np.frombuffer(rgb_bytes, dtype=np.uint8).reshape(self.height, self.width, 3)
        # Extract channels
        r = rgb[:, :, 0].astype(np.uint16)
        g = rgb[:, :, 1].astype(np.uint16)
        b = rgb[:, :, 2].astype(np.uint16)
        # Combine to RGB565: RRRRR GGGGGG BBBBB
        rgb565 = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
        # Convert to little-endian bytes
        rgb565_le = rgb565.astype('<u2')
        
        # Write to framebuffer mmap
        self.mm.seek(0)
        self.mm.write(rgb565_le.tobytes())
        # No need to flush every frame; keep performance reasonable


def load_touch_calibration(config_file="/home/dietpi/tag-tapper-pi/config.yaml"):
    """Load calibration values (raw min/max) from YAML config.
    Falls back to defaults if not present.
    """
    try:
        with open(config_file, 'r') as f:
            config = yaml.safe_load(f) or {}
            calib = config.get('touch_calibration')
            if calib:
                return {
                    'raw_x_min': int(calib.get('raw_x_min', 0)),
                    'raw_x_max': int(calib.get('raw_x_max', 4095)),
                    'raw_y_min': int(calib.get('raw_y_min', 0)),
                    'raw_y_max': int(calib.get('raw_y_max', 4095)),
                }
    except Exception as e:
        logging.info(f"No touch calibration found: {e}")
    return {
        'raw_x_min': 0,
        'raw_x_max': 4095,
        'raw_y_min': 0,
        'raw_y_max': 4095,
    }


def map_raw_to_screen(x, y, size, calib):
    """Map raw touch values to screen pixel coordinates using calibration.
    Clamps to screen bounds. Handles potential inverted axes.
    """
    width, height = size
    xmin = calib['raw_x_min']
    xmax = calib['raw_x_max']
    ymin = calib['raw_y_min']
    ymax = calib['raw_y_max']

    # Prevent division by zero and handle inverted ranges
    if xmax == xmin:
        xr = 1
    else:
        xr = xmax - xmin
    if ymax == ymin:
        yr = 1
    else:
        yr = ymax - ymin

    # Normalize 0..1; invert if needed
    nx = (x - xmin) / xr
    ny = (y - ymin) / yr
    if xr < 0:
        nx = 1.0 - nx
    if yr < 0:
        ny = 1.0 - ny

    # Clamp and scale
    nx = 0.0 if nx < 0 else 1.0 if nx > 1 else nx
    ny = 0.0 if ny < 0 else 1.0 if ny > 1 else ny
    sx = int(nx * (width - 1))
    sy = int(ny * (height - 1))
    return sx, sy





class TagTapperApp:
    """Pygame-based TUI with tabs and touch support."""
    
    TABS = [
        {"id": "ip", "label": "IP"},
        {"id": "ping", "label": "Ping"},
        {"id": "range", "label": "Range"},
        {"id": "reboot", "label": "Reboot"},
        {"id": "shutdown", "label": "Shutdown"}
    ]
    
    # Colors
    BG_COLOR = (0, 0, 0)
    HEADER_BG = (0, 51, 102)
    TAB_BG = (0, 34, 68)
    TAB_ACTIVE_BG = (0, 68, 136)
    TAB_HOVER_BG = (0, 51, 102)
    TEXT_COLOR = (255, 255, 255)
    TEXT_ACTIVE = (0, 255, 0)
    BORDER_COLOR = (0, 255, 0)
    
    def __init__(self, size):
        self.size = size
        self.width, self.height = size
        self.active_tab = 0
        self.last_touch_x = None
        self.last_touch_y = None
        # Swipe detection
        self.touch_start_x = None
        self.touch_start_y = None
        
        # Layout constants - header + carousel
        self.header_height = 35
        self.indicator_radius = 8
        self.indicator_spacing = 24
        self.indicator_y = self.height - 30
        
        # Fonts from styles
        self.fonts = styles.load_fonts()
        self.header_font = self.fonts['header']
        self.tab_title_font = self.fonts['tab_title']
        self.title_font = self.fonts['title']
        self.content_font = self.fonts['content']

        # Components per tab (created lazily here)
        try:
            from GUI import tab_ip, tab_ping, tab_range, action
            self.components = {
                'ip': tab_ip.TabIP(),
                'ping': tab_ping.TabPing(),
                'range': tab_range.TabRange(),
                'reboot': action.ActionTab('reboot'),
                'shutdown': action.ActionTab('shutdown'),
            }
        except Exception:
            self.components = {}

        # Tabs/header component (handles title, indicators and swipe)
        try:
            self.tabs = tabs_module.Tabs()
        except Exception:
            self.tabs = None

        # Position smoothing buffer for touch POS events
        self.pos_buffer = deque(maxlen=4)
        # Swipe debounce control
        self.last_swipe_time = 0.0
        self.swipe_debounce = 0.2  # seconds
        # Long-press (hold) control for destructive actions
        self.long_press_start_time = None
        self.long_press_target = None
        self.long_press_duration = 5.0  # seconds to trigger action
        self.long_press_progress = 0.0
        self.long_press_executed = False
        # Animation state for pre-execution
        self.exec_after_anim = None
        self.anim_start = None
        self.anim_duration = 1.0  # seconds for pre-exec animation
        
        
    
    
    def draw(self, surface):
        """Draw the complete UI (header + content)."""
        surface.fill(styles.BG_COLOR)
        # Render header and indicators via Tabs component -> get safe content rect
        if self.tabs is not None:
            try:
                content_rect = self.tabs.render(surface, self, styles, self.fonts)
            except Exception:
                content_rect = pygame.Rect(0, self.header_height, self.width, self.height - self.header_height)
        else:
            content_rect = pygame.Rect(0, self.header_height, self.width, self.height - self.header_height)

        # Delegate rendering of the content area to the active component
        tab = self.TABS[self.active_tab]
        comp = self.components.get(tab['id']) if hasattr(self, 'components') else None
        if comp:
            try:
                comp.draw(surface, content_rect, self, styles, self.fonts)
            except Exception:
                pass
        else:
            title = self.title_font.render(tab['label'], True, styles.TEXT_ACTIVE)
            surface.blit(title, title.get_rect(center=(self.width // 2, self.header_height + 60)))

        # If an execution animation is active, draw it on top
        if self.exec_after_anim is not None:
            try:
                self.draw_animation(surface)
            except Exception:
                pass
    
    def handle_touch_start(self, x, y):
        """Record touch start position for swipe detection."""
        self.touch_start_x = x
        self.touch_start_y = y
        logging.debug(f"Touch start: X={x} Y={y}")
    
    # Swipe handling moved to Tabs component

    def draw_animation(self, surface):
        """Draw a short pre-execution animation (spinner + fade)."""
        if self.anim_start is None:
            return
        try:
            import math
            now = time.time()
            t = (now - self.anim_start) / max(0.0001, self.anim_duration)
            t = max(0.0, min(1.0, t))
            # Fade overlay
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            alpha = int(180 * t)
            overlay.fill((0, 0, 0, alpha))
            surface.blit(overlay, (0, 0))

            # Spinner at center
            cx = self.width // 2
            cy = self.header_height + 160
            radius = 70
            thickness = 14
            start_angle = -math.pi / 2
            end_angle = start_angle + (t * 2 * math.pi)
            rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
            pygame.draw.arc(surface, (255, 200, 0), rect, start_angle, end_angle, thickness)

            # Text "Executing..."
            txt = self.content_font.render("Executing…", True, (255, 200, 0))
            rtxt = txt.get_rect(center=(cx, cy + radius + 30))
            surface.blit(txt, rtxt)
        except Exception:
            pass
    



def main():
    """Main application loop."""
    # Force headless mode: do not attempt to use SDL/fbcon
    size = get_fb_size('/dev/fb1')
    fbw = FramebufferWriter('/dev/fb1')
    try:
        pygame.font.init()
    except Exception:
        pass
    screen = pygame.Surface(size)
    
    # Create app
    app = TagTapperApp(size)
    
    # Load touch calibration
    calib = load_touch_calibration()
    logging.info(f"Calibration: X={calib['raw_x_min']}-{calib['raw_x_max']} Y={calib['raw_y_min']}-{calib['raw_y_max']}")

    # Start touch monitoring thread (delegated to tagtapperpi_comp.touch)
    touch_queue = queue.Queue()
    stop_event = threading.Event()
    t = None
    try:
        from tagtapperpi_comp import touch as touch_module
        t = touch_module.start_touch_monitor(touch_queue, TOUCH_PATH, stop_event)
    except Exception as e:
        logging.error(f"Failed to start touch monitor: {e}")
    
    logging.info('App started. Starting main loop...')
    
    clock = pygame.time.Clock()
    running = True
    touched = False
    
    try:
        while running:
            # No pygame display or events in headless mode
            
            # Process touch queue
            try:
                while True:
                    ev = touch_queue.get_nowait()
                    if not ev:
                        continue
                    
                    if ev[0] == 'BTN':
                        # Touch button press/release
                        val = ev[1]
                        if val == 1:  # Press
                            touched = True
                            # record start position if available
                            if app.last_touch_x is not None:
                                app.touch_start_x = app.last_touch_x
                                app.touch_start_y = app.last_touch_y
                            # Start long-press immediately for destructive tabs (position-independent)
                            try:
                                if app.TABS[app.active_tab]["id"] in ("reboot", "shutdown"):
                                    app.long_press_start_time = time.time()
                                    app.long_press_target = app.active_tab
                                    app.long_press_progress = 0.0
                                    app.long_press_executed = False
                            except Exception:
                                pass
                        else:  # Release
                            touched = False
                            # Use simple position-based swipe detection (no timing constraint)
                            if app.touch_start_x is not None and app.last_touch_x is not None:
                                try:
                                    if app.tabs is not None:
                                        app.tabs.handle_swipe(app.touch_start_x, app.last_touch_x, app)
                                except Exception:
                                    pass
                            # Reset touch and position buffer
                            app.last_touch_x = None
                            app.last_touch_y = None
                            app.touch_start_x = None
                            app.touch_start_y = None
                            try:
                                app.pos_buffer.clear()
                            except Exception:
                                pass
                            # reset long-press unless it already executed
                            if not app.long_press_executed:
                                app.long_press_start_time = None
                                app.long_press_progress = 0.0
                                app.long_press_target = None
                            else:
                                app.long_press_target = None
                        logging.debug(f'Touch event -> touched={touched}')
                    
                    elif ev[0] == 'POS':
                        # Position update
                        _, x, y, p = ev
                        if x is not None and y is not None:
                            sx, sy = map_raw_to_screen(x, y, size, calib)
                            # Append to smoothing buffer and compute averages
                            try:
                                app.pos_buffer.append((sx, sy))
                                bx = int(sum(p[0] for p in app.pos_buffer) / len(app.pos_buffer))
                                by = int(sum(p[1] for p in app.pos_buffer) / len(app.pos_buffer))
                            except Exception:
                                bx, by = sx, sy
                            logging.debug(f"Touch raw: X={x} Y={y} -> screen: X={sx} Y={sy} avg: X={bx} Y={by}")
                            # Set touch_start on first POS event after press
                            if touched and app.touch_start_x is None:
                                app.handle_touch_start(bx, by)
                                # If this is a destructive tab, start long-press timer
                                if app.TABS[app.active_tab]["id"] in ("reboot", "shutdown"):
                                    app.long_press_start_time = time.time()
                                    app.long_press_target = app.active_tab
                                    app.long_press_progress = 0.0
                                    app.long_press_executed = False
                            app.last_touch_x = bx
                            app.last_touch_y = by
            
            except queue.Empty:
                pass
            # Update long-press progress and handle execution
            try:
                now = time.time()
                if app.long_press_start_time is not None and touched and app.long_press_target == app.active_tab:
                    # If touch moved too far from start, cancel
                    if app.touch_start_x is not None and app.last_touch_x is not None:
                        dx = app.last_touch_x - app.touch_start_x
                        dy = app.last_touch_y - app.touch_start_y
                        if (dx * dx + dy * dy) ** 0.5 > 30:
                            # Movement cancelled long-press
                            app.long_press_start_time = None
                            app.long_press_progress = 0.0
                        else:
                            dt = now - app.long_press_start_time
                            prog = max(0.0, min(1.0, dt / app.long_press_duration))
                            app.long_press_progress = prog
                            if prog >= 1.0 and not app.long_press_executed:
                                # Start pre-execution animation; actual exec happens after animation
                                tabid = app.TABS[app.active_tab]["id"]
                                logging.info(f"Long-press triggered for {tabid}; starting pre-exec animation")
                                app.exec_after_anim = tabid
                                app.anim_start = now
                                app.long_press_executed = True
                else:
                    # Not holding or different tab: ensure progress reset
                    if not touched:
                        app.long_press_start_time = None
                        app.long_press_progress = 0.0
                        app.long_press_target = None
                        app.long_press_executed = False
            except Exception:
                pass
            
            # Draw and update
            app.draw(screen)
            # Push buffer to framebuffer
            fbw.blit_surface(screen)
            # If a pre-exec animation is running, check for completion and perform cleanup+exec
            try:
                if app.exec_after_anim is not None and app.anim_start is not None:
                    if time.time() - app.anim_start >= app.anim_duration:
                        tabid = app.exec_after_anim
                        logging.info(f"Pre-exec animation complete for {tabid}; performing cleanup and executing")
                        # stop touch thread
                        stop_event.set()
                        try:
                            t.join(timeout=2)
                        except Exception:
                            pass
                        # close framebuffer
                        try:
                            fbw.close()
                        except Exception:
                            pass
                        # quit pygame
                        try:
                            pygame.quit()
                        except Exception:
                            pass
                        # execute system action
                        try:
                            if tabid == 'reboot':
                                subprocess.Popen(['sudo', 'reboot'])
                            elif tabid == 'shutdown':
                                subprocess.Popen(['sudo', 'poweroff'])
                        except Exception as e:
                            logging.error(f"Failed to execute {tabid}: {e}")
                        # short delay then exit loop
                        time.sleep(0.3)
                        running = False
                        break
            except Exception:
                pass
            
            clock.tick(30)  # 30 FPS
    
    except KeyboardInterrupt:
        logging.info('Exiting on user request')
    
    finally:
        stop_event.set()
        try:
            t.join(timeout=1)
        except Exception:
            pass
        try:
            fbw.close()
        except Exception:
            pass
        try:
            pygame.quit()
        except Exception:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"App error: {e}", exc_info=True)
        sys.exit(1)