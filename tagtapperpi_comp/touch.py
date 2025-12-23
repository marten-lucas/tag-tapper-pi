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

    When data is read the function will post a Click event targeted at the
    `#toggle` widget in the Textual app. It does not directly change app
    state; only a received Click on the button will cause the UI to toggle.
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
                        # Log raw kernel data for inspection
                        try:
                            # limit logged size to avoid huge outputs
                            preview = data[:256]
                            logging.info(
                                "Kernel touch data: %d bytes, repr=%s, hex=%s",
                                len(data),
                                repr(preview),
                                preview.hex()
                            )
                        except Exception as e:
                            logging.debug(f"Could not log raw data: {e}")

                        # Post a Click event to the button in the UI thread.
                        try:
                            logging.info("Scheduling post_click to app")
                            app.call_from_thread(post_click, app)
                        except Exception as e:
                            logging.error(f"Failed to schedule post_click: {e}")
                            # app might be shutting down
                            break

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
        # target the toggle button
        widget = None
        try:
            widget = target_app.query_one("#toggle")
        except Exception:
            pass

        if Click is None or widget is None:
            logging.debug("Click event not available or toggle button not found")
            return

        # Try several constructors to be compatible with Textual versions
        created = False
        for ctor_args in (
            (widget,),
            (),
        ):
            try:
                logging.debug("Trying Click constructor with args=%s", ctor_args)
                if ctor_args:
                    ev = Click(*ctor_args)
                else:
                    ev = Click(sender=widget, x=0, y=0, button=1)
                logging.debug("Posting event %s (sender id=%s)", type(ev), getattr(ev, 'sender', None))
                target_app.post_message(ev)
                logging.info("Posted Click event to app")
                created = True
                break
            except Exception as e:
                logging.debug(f"Click constructor attempt failed: {e}")
                continue

        if not created:
            # Last resort: try to attach sender then post
            try:
                logging.debug("Trying fallback Click(widget) constructor")
                ev = Click(widget)
                ev.sender = widget
                logging.debug("Posting fallback event %s (sender id=%s)", type(ev), getattr(ev, 'sender', None))
                target_app.post_message(ev)
                logging.info("Posted Click event (fallback) to app")
            except Exception as e:
                logging.debug(f"Could not create Click event: {e}")
    except Exception as e:
        logging.debug(f"Error while posting Click: {e}")

