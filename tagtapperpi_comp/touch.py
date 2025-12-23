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
    """Start a background thread that reads raw kernel input from `device_path`.

    When data is read the function will call `app.call_from_thread(app.action_trigger_touch)`
    so the Textual app can react on the main thread.
    """

    def _monitor():
        try:
            if not os.path.exists(device_path):
                logging.error(f"Device nicht gefunden: {device_path}")
                return

            # Ensure we also write position info to the central log file used by the service.
            LOG_PATH = "/home/dietpi/tag-tapper-pi/tag-tapper-pi.log"
            logger = logging.getLogger("tagtapper.touch")
            # Add a FileHandler only if not already present for that path
            try:
                has_file = any(
                    getattr(h, "baseFilename", None) == LOG_PATH for h in logger.handlers
                )
            except Exception:
                has_file = False

            if not has_file:
                try:
                    fh = logging.FileHandler(LOG_PATH)
                    fh.setLevel(logging.INFO)
                    fh.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
                    logger.addHandler(fh)
                except Exception:
                    # If we can't open the service log, fall back to root logger behavior
                    logger = logging.getLogger()

            with open(device_path, "rb") as f:
                logging.info(f"Touch-Monitor verbunden mit {device_path}")
                while True:
                    data = f.read(poll_size)
                    if data:
                        # First: notify app via existing action (guaranteed fallback)
                        try:
                            app.call_from_thread(app.action_trigger_touch)
                        except Exception:
                            # app might be shutting down
                            break

                        # Then: attempt to post a Click event targeted at the label widget.
                        try:
                            app.call_from_thread(post_click, app)
                        except Exception:
                            pass

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
                                    axis = "X" if code == 0 else "Y"
                                    logger.info(f"Touch position {axis}={value}")
                                # BTN_TOUCH often appears as type 1, code 330
                                elif etype == 1 and code in (330,):
                                    logger.info(f"BTN_TOUCH code={code} value={value}")
                                else:
                                    logger.debug(f"input_event type={etype} code={code} value={value}")
                            else:
                                logger.debug(f"Raw touch data: {data.hex()}")
                        except Exception as e:
                            logger.debug(f"Could not parse input_event: {e} raw={data.hex()}")
        except Exception as e:
            logging.error(f"Kritischer Fehler im Touch-Monitor: {e}")

    thread = threading.Thread(target=_monitor, daemon=True)
    thread.start()
    return thread


def post_click(target_app) -> None:
    """Try to post a `Click` event to `target_app`'s `#label` widget.

    This function attempts multiple constructor patterns for `textual.events.Click`
    to remain compatible across Textual versions. It logs successes/failures.
    """
    try:
        label = None
        try:
            label = target_app.query_one("#label")
        except Exception:
            pass

        if Click is None or label is None:
            logging.debug("Click event not available or label not found")
            return

        # Try several constructors to be compatible with Textual versions
        created = False
        for ctor_args in (
            (label,),
            (),
        ):
            try:
                if ctor_args:
                    ev = Click(*ctor_args)
                else:
                    ev = Click(sender=label, x=0, y=0, button=1)
                target_app.post_message(ev)
                logging.info("Posted Click event to app")
                created = True
                break
            except Exception:
                continue

        if not created:
            # Last resort: try to attach sender then post
            try:
                ev = Click(label)
                ev.sender = label
                target_app.post_message(ev)
                logging.info("Posted Click event (fallback) to app")
            except Exception as e:
                logging.debug(f"Could not create Click event: {e}")
    except Exception as e:
        logging.debug(f"Error while posting Click: {e}")
