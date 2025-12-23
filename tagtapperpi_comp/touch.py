import os
import time
import threading
import logging
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

