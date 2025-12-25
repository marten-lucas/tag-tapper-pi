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
import subprocess

try:
    import pygame
except Exception as e:
    print("pygame is required. Install with: pip3 install pygame")
    sys.exit(1)

try:
    from evdev import InputDevice, ecodes
except Exception as e:
    print("evdev is required. Install with: pip3 install evdev")
    sys.exit(1)

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


def touch_thread(devpath, q, stop_event):
    """Thread to read touch events from evdev and push to queue."""
    try:
        d = InputDevice(devpath)
        logging.info(f"Opened touch device {devpath} ({d.name})")
        cur_x = None
        cur_y = None
        cur_pressure = 0
        for ev in d.read_loop():
            if stop_event.is_set():
                break
            try:
                t = ev.type
                c = ev.code
                v = ev.value
                tname = ecodes.EV.get(t, str(t))
                cname = ecodes.bytype.get(t, {}).get(c, c)
            except Exception:
                tname = ev.type
                cname = ev.code
                v = ev.value

            logging.debug('evdev: type=%s code=%s value=%s', tname, cname, v)

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
                elif ev.type == ecodes.EV_SYN and ev.code == ecodes.SYN_REPORT:
                    q.put(('POS', cur_x, cur_y, cur_pressure))
            except Exception:
                pass
    except Exception as e:
        logging.error(f"touch thread error: {e}")


class TagTapperApp:
    """Pygame-based TUI with tabs and touch support."""
    
    TABS = [
        {"id": "ip", "label": "IP", "content": "IP Configuration\n\nComing soon..."},
        {"id": "ping", "label": "Ping", "content": "Ping Test\n\nComing soon..."},
        {"id": "range", "label": "Range", "content": "Range Scanner\n\nComing soon..."},
        {"id": "reboot", "label": "Reboot", "content": "Reboot System\n\nComing soon..."},
        {"id": "shutdown", "label": "Shutdown", "content": "Shutdown System\n\nComing soon..."}
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
        
        # Fonts (slightly larger)
        self.header_font = pygame.font.Font(None, 22)
        self.tab_title_font = pygame.font.Font(None, 26)
        self.title_font = pygame.font.Font(None, 72)
        self.content_font = pygame.font.Font(None, 44)

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
        
    def draw_header(self, surface):
        """Draw persistent header with title and date/time."""
        header_rect = pygame.Rect(0, 0, self.width, self.header_height)
        pygame.draw.rect(surface, self.HEADER_BG, header_rect)
        
        # Title left
        title = self.header_font.render("Tag Tapper Pi", True, self.TEXT_COLOR)
        surface.blit(title, (10, (self.header_height - title.get_height()) // 2))

        # Current tab title centered in header
        # Highlight this title: colored and bold as the only bold element
        try:
            self.tab_title_font.set_bold(True)
        except Exception:
            pass
        tab_label = self.tab_title_font.render(self.TABS[self.active_tab]["label"], True, self.TEXT_ACTIVE)
        tab_label_rect = tab_label.get_rect(center=(self.width // 2, self.header_height // 2))
        surface.blit(tab_label, tab_label_rect)
        try:
            self.tab_title_font.set_bold(False)
        except Exception:
            pass

        # Date/Time right
        import datetime
        now = datetime.datetime.now()
        time_str = now.strftime("%d.%m.%Y %H:%M")
        time_text = self.header_font.render(time_str, True, self.TEXT_COLOR)
        surface.blit(time_text, (self.width - time_text.get_width() - 10, (self.header_height - time_text.get_height()) // 2))
    
    def draw_content(self, surface):
        """Draw the carousel content - below header."""
        # Content area (below header)
        content_rect = pygame.Rect(0, self.header_height, self.width, self.height - self.header_height)
        pygame.draw.rect(surface, self.BG_COLOR, content_rect)
        
        # Active tab
        tab = self.TABS[self.active_tab]

        # Title at top of content
        title = self.title_font.render(tab["label"], True, self.TEXT_ACTIVE)
        title_rect = title.get_rect(center=(self.width // 2, self.header_height + 60))
        surface.blit(title, title_rect)
        
        # Content in center
        lines = tab["content"].split('\n')
        y_offset = self.header_height + 140
        for line in lines:
            if line.strip():
                text = self.content_font.render(line, True, (200, 200, 200))
                text_rect = text.get_rect(center=(self.width // 2, y_offset))
                surface.blit(text, text_rect)
                y_offset += 50
        
        # Page indicators at bottom
        total_width = len(self.TABS) * self.indicator_spacing
        start_x = (self.width - total_width) // 2 + self.indicator_radius
        
        for i in range(len(self.TABS)):
            x = start_x + i * self.indicator_spacing
            if i == self.active_tab:
                pygame.draw.circle(surface, self.TEXT_ACTIVE, (x, self.indicator_y), self.indicator_radius)
            else:
                pygame.draw.circle(surface, (80, 80, 80), (x, self.indicator_y), self.indicator_radius, 2)

        # Draw long-press progress for destructive tabs (reboot/shutdown)
        if self.TABS[self.active_tab]["id"] in ("reboot", "shutdown"):
            # position the progress indicator near center under the large title
            cx = self.width // 2
            cy = self.header_height + 140
            radius = 40
            thickness = 8
            # Background ring
            pygame.draw.circle(surface, (60, 60, 60), (cx, cy), radius, thickness)
            # Progress arc (start at top)
            if self.long_press_progress > 0:
                try:
                    import math
                    start_angle = -math.pi / 2
                    end_angle = start_angle + (self.long_press_progress * 2 * math.pi)
                    rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
                    pygame.draw.arc(surface, (0, 200, 0), rect, start_angle, end_angle, thickness)
                except Exception:
                    pass
    
    def draw(self, surface):
        """Draw the complete UI."""
        surface.fill(self.BG_COLOR)
        self.draw_header(surface)
        self.draw_content(surface)
    
    def handle_touch_start(self, x, y):
        """Record touch start position for swipe detection."""
        self.touch_start_x = x
        self.touch_start_y = y
        logging.debug(f"Touch start: X={x} Y={y}")
    
    def handle_swipe(self, start_x, end_x):
        """Detect and handle swipe gestures."""
        if start_x is None or end_x is None:
            return False
        
        delta_x = end_x - start_x
        threshold = 50  # Minimum swipe distance in pixels (reduced for responsiveness)

        logging.info(f"Swipe: start_x={start_x} end_x={end_x} delta={delta_x}")

        # Debounce: ignore additional swipes within debounce interval
        now = time.time()
        if now - self.last_swipe_time < self.swipe_debounce:
            return False

        if abs(delta_x) > threshold:
            if delta_x > 0:  # Swipe right → previous tab
                if self.active_tab > 0:
                    self.active_tab -= 1
                    logging.info(f"Swipe RIGHT → Tab {self.active_tab}: {self.TABS[self.active_tab]['label']}")
                    self.last_swipe_time = now
                    return True
            else:  # Swipe left → next tab
                if self.active_tab < len(self.TABS) - 1:
                    self.active_tab += 1
                    logging.info(f"Swipe LEFT → Tab {self.active_tab}: {self.TABS[self.active_tab]['label']}")
                    self.last_swipe_time = now
                    return True

        return False
    



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

    # Start touch monitoring thread
    touch_queue = queue.Queue()
    stop_event = threading.Event()
    t = threading.Thread(target=touch_thread, args=(TOUCH_PATH, touch_queue, stop_event), daemon=True)
    t.start()
    
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
                            # On press we don't have pos yet; long-press will start on first POS
                        else:  # Release
                            touched = False
                            # On release: attempt swipe handling, then reset long-press state
                            if app.touch_start_x is not None and app.last_touch_x is not None:
                                app.handle_swipe(app.touch_start_x, app.last_touch_x)
                            app.last_touch_x = None
                            app.last_touch_y = None
                            app.touch_start_x = None
                            app.touch_start_y = None
                            # clear position buffer after release
                            try:
                                app.pos_buffer.clear()
                            except Exception:
                                pass
                            # reset long-press
                            app.long_press_start_time = None
                            app.long_press_progress = 0.0
                            app.long_press_target = None
                            app.long_press_executed = False
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
                                # Execute action
                                tabid = app.TABS[app.active_tab]["id"]
                                logging.info(f"Long-press triggered for {tabid}")
                                try:
                                    if tabid == 'reboot':
                                        subprocess.Popen(['sudo', 'reboot'])
                                    elif tabid == 'shutdown':
                                        subprocess.Popen(['sudo', 'poweroff'])
                                except Exception as e:
                                    logging.error(f"Failed to execute {tabid}: {e}")
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