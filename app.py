import logging
import sys
import atexit
import os
import time

from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Container
from textual.reactive import reactive

# ---------- Logging ----------
# Prüfe ob wir auf DietPi laufen, sonst lokales error.log
ERROR_LOG = "/home/dietpi/error.log" if os.path.exists("/home/dietpi") else "error.log"

logging.basicConfig(
    filename=ERROR_LOG,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

sys.stderr = open(ERROR_LOG, "a")

# ---------- Cleanup ----------
def clear_terminal():
    os.system("clear")

atexit.register(clear_terminal)

# Hardware-Pfad (kann über Environment gesetzt werden)
TOUCH_PATH = os.environ.get(
    "TEXTUAL_EVDEV_PATH",
    "/dev/input/by-path/platform-3f204000.spi-cs-1-event",
)


class FinalReactiveApp(App):
    touched = reactive(False)

    CSS = """
    #main {
        align: center middle;
        width: 100%;
        height: 100%;
        content-align: center middle;
        text-style: bold;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="main"):
            yield Static("HALLO WELT\n\n[ BEREIT ]", id="label")

    def watch_touched(self, value: bool) -> None:
        main = self.query_one("#main")
        label = self.query_one("#label")

        if value:
            main.styles.background = "#004400"
            main.styles.border = ("double", "#FFFF00")
            label.update("HALLO WELT\n\n[ BERÜHRT ]")
        else:
            main.styles.background = "#000000"
            main.styles.border = ("round", "#00FF00")
            label.update("HALLO WELT\n\n[ BEREIT ]")

    def action_trigger_touch(self):
        logging.info("Hardware-Touch erkannt -> State-Wechsel")
        self.touched = not self.touched

    def on_mount(self) -> None:
        self.run_worker(self.touch_monitor, thread=True)

    async def touch_monitor(self):
        try:
            with open(TOUCH_PATH, "rb") as f:
                while True:
                    data = f.read(24)
                    if data:
                        self.call_from_thread(self.action_trigger_touch)
                        time.sleep(0.3)
                        try:
                            os.read(f.fileno(), 1024)
                        except Exception:
                            pass
        except Exception as e:
            logging.error(f"Monitor-Fehler: {e}")


if __name__ == "__main__":
    FinalReactiveApp().run()
