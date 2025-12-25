import logging
import os
import sys
import time
import threading
import queue
import mmap
import struct
import yaml

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
        # Convert to RGB565 (little-endian) efficiently
        out = bytearray(self.size_bytes)
        ib = memoryview(rgb_bytes)
        ob = memoryview(out)
        # Process 3-byte RGB to 2-byte 565
        j = 0
        for i in range(0, len(ib), 3):
            r = ib[i]
            g = ib[i+1]
            b = ib[i+2]
            val = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            ob[j] = val & 0xFF
            ob[j+1] = (val >> 8) & 0xFF
            j += 2

        # Write to framebuffer mmap
        self.mm.seek(0)
        self.mm.write(ob)
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
        {"id": "power", "label": "Power", "content": "Power Options\n\nComing soon..."}
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
        self.hover_tab = None
        self.last_touch_x = None
        self.last_touch_y = None
        
        # Layout constants
        self.header_height = 40
        self.tab_bar_height = 60
        self.tab_width = self.width // len(self.TABS)
        self.content_y = self.header_height + self.tab_bar_height
        
        # Fonts
        self.title_font = pygame.font.Font(None, 36)
        self.tab_font = pygame.font.Font(None, 32)
        self.content_font = pygame.font.Font(None, 48)
        
    def draw_header(self, surface):
        """Draw the header bar."""
        header_rect = pygame.Rect(0, 0, self.width, self.header_height)
        pygame.draw.rect(surface, self.HEADER_BG, header_rect)
        
        title = self.title_font.render("Tag Tapper Pi", True, self.TEXT_COLOR)
        title_rect = title.get_rect(center=(self.width // 2, self.header_height // 2))
        surface.blit(title, title_rect)
        
    def draw_tabs(self, surface):
        """Draw the tab bar."""
        tab_y = self.header_height
        
        for i, tab in enumerate(self.TABS):
            x = i * self.tab_width
            tab_rect = pygame.Rect(x, tab_y, self.tab_width, self.tab_bar_height)
            
            # Background color based on state
            if i == self.active_tab:
                bg_color = self.TAB_ACTIVE_BG
                text_color = self.TEXT_ACTIVE
            elif i == self.hover_tab:
                bg_color = self.TAB_HOVER_BG
                text_color = self.TEXT_COLOR
            else:
                bg_color = self.TAB_BG
                text_color = (170, 170, 170)
            
            pygame.draw.rect(surface, bg_color, tab_rect)
            pygame.draw.rect(surface, (50, 50, 50), tab_rect, 1)  # Border
            
            # Tab label
            label = self.tab_font.render(tab["label"], True, text_color)
            label_rect = label.get_rect(center=tab_rect.center)
            surface.blit(label, label_rect)
    
    def draw_content(self, surface):
        """Draw the active tab content."""
        content_rect = pygame.Rect(0, self.content_y, self.width, 
                                   self.height - self.content_y)
        pygame.draw.rect(surface, self.BG_COLOR, content_rect)
        
        # Draw content text
        tab = self.TABS[self.active_tab]
        lines = tab["content"].split('\n')
        
        y_offset = self.content_y + 60
        for line in lines:
            if line.strip():
                text = self.content_font.render(line, True, self.TEXT_ACTIVE)
                text_rect = text.get_rect(center=(self.width // 2, y_offset))
                surface.blit(text, text_rect)
                y_offset += 60
    
    def draw(self, surface):
        """Draw the complete UI."""
        surface.fill(self.BG_COLOR)
        self.draw_header(surface)
        self.draw_tabs(surface)
        self.draw_content(surface)
    
    def handle_click(self, x, y):
        """Handle touch/click event."""
        # Check if click is in tab bar
        if self.header_height <= y < self.header_height + self.tab_bar_height:
            tab_index = x // self.tab_width
            if 0 <= tab_index < len(self.TABS):
                logging.info(f"Tab clicked: {self.TABS[tab_index]['label']}")
                self.active_tab = tab_index
                return True
        return False
    
    def update_hover(self, x, y):
        """Update hover state based on position."""
        if x is None or y is None:
            self.hover_tab = None
            return
        
        if self.header_height <= y < self.header_height + self.tab_bar_height:
            tab_index = x // self.tab_width
            if 0 <= tab_index < len(self.TABS):
                self.hover_tab = tab_index
                return
        self.hover_tab = None


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
                            if app.last_touch_x is not None and app.last_touch_y is not None:
                                app.handle_click(app.last_touch_x, app.last_touch_y)
                        else:  # Release
                            touched = False
                            app.last_touch_x = None
                            app.last_touch_y = None
                        logging.info(f'Touch event -> touched={touched}')
                    
                    elif ev[0] == 'POS':
                        # Position update
                        _, x, y, p = ev
                        if x is not None and y is not None:
                            sx, sy = map_raw_to_screen(x, y, size, calib)
                            app.last_touch_x = sx
                            app.last_touch_y = sy
                            app.update_hover(sx, sy)
            
            except queue.Empty:
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