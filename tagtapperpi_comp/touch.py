import os
import time
import threading
import logging
import struct
from typing import Optional

try:
    from textual.events import Click
except Exception:
    Click = None


def start_touch_monitor(app, device_path: str, poll_size: int = 24, debounce: float = 0.3):
    """Start a background thread that reads raw kernel input from `device_path`."""

    def _monitor():
        logger = logging.getLogger("tagtapper.touch")
        try:
            if not os.path.exists(device_path):
                logger.error(f"Device nicht gefunden: {device_path}")
                return

            with open(device_path, "rb") as f:
                logger.info(f"Touch-Monitor verbunden mit {device_path}")
                # Track latest raw and mapped coords and touch state
                last_raw_x = None
                last_raw_y = None
                last_mapped_x = None
                last_mapped_y = None
                btn_pressed = False

                while True:
                    data = f.read(poll_size)
                    if data:
                        # simple debouncing: wait and clear input buffer
                        time.sleep(debounce)
                        try:
                            os.read(f.fileno(), 1024)
                        except BlockingIOError:
                            pass
                        # Try to parse Linux input_event (24 bytes on 64-bit) to extract position
                        try:
                            if len(data) >= 24:
                                # tv_sec (long), tv_usec (long), type (unsigned short), code (unsigned short), value (int)
                                sec, usec, etype, code, value = struct.unpack("llHHi", data[:24])
                                # EV_ABS == 3, codes: 0 = ABS_X, 1 = ABS_Y
                                if etype == 3 and code in (0, 1):
                                    # raw value
                                    if code == 0:
                                        last_raw_x = int(value)
                                    else:
                                        last_raw_y = int(value)

                                    # map raw (0-4095) to display (480x320)
                                    try:
                                        RAW_MAX = 4095
                                        if last_raw_x is not None:
                                            mx = int(max(0, min(RAW_MAX, last_raw_x)) / RAW_MAX * (480 - 1))
                                            last_mapped_x = mx
                                        if last_raw_y is not None:
                                            my = int(max(0, min(RAW_MAX, last_raw_y)) / RAW_MAX * (320 - 1))
                                            last_mapped_y = my
                                        logger.info(f"Raw touch X={last_raw_x} Y={last_raw_y} -> Mapped X={last_mapped_x} Y={last_mapped_y}")
                                    except Exception:
                                        logger.debug("Mapping error")

                                # BTN_TOUCH often appears as type 1, code 330
                                elif etype == 1 and code in (330,):
                                    # value 1 = press, 0 = release
                                    btn_pressed = bool(value)
                                    logger.info(f"BTN_TOUCH code={code} value={value}")
                                    # On press, post Click with mapped coords if available
                                    if btn_pressed and last_mapped_x is not None and last_mapped_y is not None:
                                        try:
                                            # Post a Click event with mapped coordinates
                                            app.call_from_thread(post_click, app, last_mapped_x, last_mapped_y)
                                            logger.info(f"Posted Click at mapped X={last_mapped_x} Y={last_mapped_y}")
                                        except Exception:
                                            logger.debug("Failed to post mapped Click")
                                else:
                                    logger.debug(f"input_event type={etype} code={code} value={value}")
                            else:
                                logger.debug(f"Raw touch data: {data.hex()}")
                        except Exception as e:
                            logger.debug(f"Could not parse input_event: {e} raw={data.hex()}")
        except Exception as e:
            logger.error(f"Kritischer Fehler im Touch-Monitor: {e}")

    thread = threading.Thread(target=_monitor, daemon=True)
    thread.start()
    return thread


def post_click(target_app, x: Optional[int] = None, y: Optional[int] = None) -> None:
    """Try to post a `Click` event to `target_app`'s `#label` widget.

    This function attempts multiple constructor patterns for `textual.events.Click`
    to remain compatible across Textual versions. It logs successes/failures.
    """
    try:
        # target the center button if present
        widget = None
        try:
            widget = target_app.query_one("#center_btn")
        except Exception:
            try:
                widget = target_app.query_one("#label")
            except Exception:
                widget = None

        if Click is None or widget is None:
            logging.debug("Click event not available or target widget not found")
            return

        # Try to construct Click with coordinates when provided
        created = False
        for ctor_try in range(3):
            try:
                if x is not None and y is not None:
                    try:
                        ev = Click(sender=widget, x=int(x), y=int(y), button=1)
                    except Exception:
                        ev = Click(widget)
                        ev.x = int(x)
                        ev.y = int(y)
                else:
                    ev = Click(widget)

                target_app.post_message(ev)
                logging.info(f"Posted Click event to app (x={x} y={y})")
                created = True
                break
            except Exception:
                continue

        if not created:
            logging.debug("Could not create/post Click event after retries")
    except Exception as e:
        logging.debug(f"Error while posting Click: {e}")
