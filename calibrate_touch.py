#!/usr/bin/env python3
"""Touch screen calibration tool for tag-tapper-pi using pygame for direct framebuffer."""
import logging
import os
import sys
import struct
import threading
import queue
import time
import yaml
import mmap

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
CONFIG_FILE = "/home/dietpi/tag-tapper-pi/config.yaml"

logging.basicConfig(filename='/tmp/touch_calibration.log', level=logging.INFO, format='%(asctime)s - %(message)s')


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
    return 480, 320


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
        """Copy a pygame Surface to the framebuffer as RGB565."""
        if surface.get_width() != self.width or surface.get_height() != self.height:
            surface = pygame.transform.smoothscale(surface, (self.width, self.height))

        rgb_bytes = pygame.image.tostring(surface, 'RGB')
        out = bytearray(self.size_bytes)
        ib = memoryview(rgb_bytes)
        ob = memoryview(out)
        j = 0
        for i in range(0, len(ib), 3):
            r = ib[i]
            g = ib[i+1]
            b = ib[i+2]
            val = ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)
            ob[j] = val & 0xFF
            ob[j+1] = (val >> 8) & 0xFF
            j += 2

        self.mm.seek(0)
        self.mm.write(ob)


def touch_thread(devpath, q, stop_event):
    """Thread to read touch events from evdev and push to queue."""
    try:
        d = InputDevice(devpath)
        logging.info(f"Opened touch device {devpath} ({d.name})")
        cur_x = None
        cur_y = None
        for ev in d.read_loop():
            if stop_event.is_set():
                break
            try:
                if ev.type == ecodes.EV_ABS:
                    if ev.code in (ecodes.ABS_X, ecodes.ABS_MT_POSITION_X):
                        cur_x = ev.value
                    elif ev.code in (ecodes.ABS_Y, ecodes.ABS_MT_POSITION_Y):
                        cur_y = ev.value
                elif ev.type == ecodes.EV_KEY and ev.code == ecodes.BTN_TOUCH:
                    if ev.value == 1:  # Press
                        q.put(('TOUCH', cur_x, cur_y))
                elif ev.type == ecodes.EV_SYN and ev.code == ecodes.SYN_REPORT:
                    q.put(('POS', cur_x, cur_y))
            except Exception:
                pass
    except Exception as e:
        logging.error(f"touch thread error: {e}")


class CalibrationApp:
    """Pygame-based calibration UI."""
    
    def __init__(self, size):
        self.width, self.height = size
        self.font_large = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 32)
        
        # Define 5 calibration points: 4 corners + center
        margin = 40
        self.calib_points = [
            (margin, margin, "1"),  # top-left
            (self.width - margin, margin, "2"),  # top-right
            (self.width // 2, self.height // 2, "3"),  # center
            (margin, self.height - margin, "4"),  # bottom-left
            (self.width - margin, self.height - margin, "5"),  # bottom-right
        ]
        
        self.current_point = 0
        self.raw_touches = []
        self.state = "intro"  # intro, calibrating, done
    
    def draw(self, surface):
        """Draw the calibration UI."""
        surface.fill((0, 0, 0))
        
        if self.state == "intro":
            # Draw intro screen
            title = self.font_large.render("Touch Calibration", True, (0, 255, 0))
            surface.blit(title, (self.width // 2 - title.get_width() // 2, 60))
            
            # Draw all 5 target positions
            for x, y, label in self.calib_points:
                pygame.draw.circle(surface, (255, 0, 0), (x, y), 20, 3)
                lbl = self.font_large.render(label, True, (255, 255, 0))
                surface.blit(lbl, (x - lbl.get_width() // 2, y - lbl.get_height() // 2))
            
            msg = self.font_small.render("Touch anywhere to start", True, (255, 255, 255))
            surface.blit(msg, (self.width // 2 - msg.get_width() // 2, self.height - 60))
            
        elif self.state == "calibrating":
            # Current target
            x, y, label = self.calib_points[self.current_point]
            
            # Draw target with crosshair
            pygame.draw.circle(surface, (255, 0, 0), (x, y), 25, 4)
            pygame.draw.line(surface, (255, 0, 0), (x - 30, y), (x + 30, y), 2)
            pygame.draw.line(surface, (255, 0, 0), (x, y - 30), (x, y + 30), 2)
            
            lbl = self.font_large.render(label, True, (255, 255, 0))
            surface.blit(lbl, (x - lbl.get_width() // 2, y - lbl.get_height() // 2))
            
            # Instructions
            msg = self.font_small.render(f"Touch target {self.current_point + 1}/5", True, (0, 255, 0))
            surface.blit(msg, (self.width // 2 - msg.get_width() // 2, self.height - 60))
            
        elif self.state == "done":
            title = self.font_large.render("Calibration Complete!", True, (0, 255, 0))
            surface.blit(title, (self.width // 2 - title.get_width() // 2, self.height // 2 - 40))
            
            msg = self.font_small.render("Saved to config.yaml", True, (255, 255, 255))
            surface.blit(msg, (self.width // 2 - msg.get_width() // 2, self.height // 2 + 20))
            
            msg2 = self.font_small.render("Exiting in 3 seconds...", True, (200, 200, 200))
            surface.blit(msg2, (self.width // 2 - msg2.get_width() // 2, self.height // 2 + 60))
    
    def handle_touch(self, raw_x, raw_y):
        """Handle a touch event."""
        if self.state == "intro":
            self.state = "calibrating"
            logging.info("Starting calibration")
            
        elif self.state == "calibrating":
            # Record calibration point
            sx, sy, label = self.calib_points[self.current_point]
            self.raw_touches.append((raw_x, raw_y, sx, sy))
            logging.info(f"Point {self.current_point + 1}: Raw=({raw_x},{raw_y}) -> Screen=({sx},{sy})")
            
            self.current_point += 1
            if self.current_point >= len(self.calib_points):
                self.save_calibration()
                self.state = "done"
                return True  # Signal done
        
        return False


    def save_calibration(self):
        """Save calibration to config.yaml."""
        if len(self.raw_touches) < 5:
            logging.error("Not enough calibration points")
            return
        
        raw_x = [r[0] for r in self.raw_touches]
        raw_y = [r[1] for r in self.raw_touches]
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = yaml.safe_load(f) or {}
        except:
            config = {}
        
        config['touch_calibration'] = {
            'raw_x_min': int(min(raw_x)),
            'raw_x_max': int(max(raw_x)),
            'raw_y_min': int(min(raw_y)),
            'raw_y_max': int(max(raw_y)),
            'screen_width': self.width,
            'screen_height': self.height,
            'calibration_points': [
                {'raw_x': int(r[0]), 'raw_y': int(r[1]), 'screen_x': int(r[2]), 'screen_y': int(r[3])} 
                for r in self.raw_touches
            ]
        }
        
        try:
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            logging.info(f"Saved to {CONFIG_FILE}: X={min(raw_x)}-{max(raw_x)}, Y={min(raw_y)}-{max(raw_y)}")
            print(f"✓ Calibration saved: X={min(raw_x)}-{max(raw_x)}, Y={min(raw_y)}-{max(raw_y)}")
        except Exception as e:
            logging.error(f"Save error: {e}")
            print(f"✗ Save error: {e}")


def main():
    """Main calibration loop."""
    size = get_fb_size('/dev/fb1')
    fbw = FramebufferWriter('/dev/fb1')
    
    try:
        pygame.font.init()
    except Exception:
        pass
    
    screen = pygame.Surface(size)
    app = CalibrationApp(size)
    
    # Start touch monitoring thread
    touch_queue = queue.Queue()
    stop_event = threading.Event()
    t = threading.Thread(target=touch_thread, args=(TOUCH_PATH, touch_queue, stop_event), daemon=True)
    t.start()
    
    logging.info('Calibration started')
    print("Touch calibration started. Touch the targets as they appear.")
    
    clock = pygame.time.Clock()
    running = True
    done_time = None
    
    try:
        while running:
            # Process touch queue
            try:
                while True:
                    ev = touch_queue.get_nowait()
                    if not ev:
                        continue
                    
                    if ev[0] == 'TOUCH':
                        _, x, y = ev
                        if x is not None and y is not None:
                            if app.handle_touch(x, y):
                                # Calibration complete
                                done_time = time.time()
            
            except queue.Empty:
                pass
            
            # Draw and update
            app.draw(screen)
            fbw.blit_surface(screen)
            
            # Auto-exit after completion
            if done_time and time.time() - done_time > 3:
                running = False
            
            clock.tick(30)
    
    except KeyboardInterrupt:
        logging.info('Calibration cancelled')
    
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
    main()

