import os
import time
import threading
import logging


def start_touch_monitor(app, device_path: str, poll_size: int = 24, debounce: float = 0.3):
    """Start a background thread that reads raw kernel input from `device_path`.
    
    When touch data is detected, calls app.action_trigger_touch() to toggle state.
    """

    def _monitor():
        logger = logging.getLogger("tagtapper.touch")
        try:
            if not os.path.exists(device_path):
                logger.error(f"Device nicht gefunden: {device_path}")
                return

            with open(device_path, "rb") as f:
                logger.info(f"Touch-Monitor verbunden mit {device_path}")
                
                while True:
                    data = f.read(poll_size)
                    if data:
                        # Touch erkannt - trigger action in app
                        try:
                            app.call_from_thread(app.action_trigger_touch)
                            logger.info("Touch erkannt -> action_trigger_touch aufgerufen")
                        except Exception as e:
                            logger.error(f"Fehler beim Aufrufen von action_trigger_touch: {e}")
                            break
                        
                        # Debounce: wait and clear input buffer
                        time.sleep(debounce)
                        try:
                            os.read(f.fileno(), 1024)
                        except BlockingIOError:
                            pass
        except Exception as e:
            logger.error(f"Kritischer Fehler im Touch-Monitor: {e}")

    thread = threading.Thread(target=_monitor, daemon=True)
    thread.start()
    return thread
