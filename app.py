import logging
import os
from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Container
from textual.reactive import reactive

# Hardware-Pfad
TOUCH_PATH = "/dev/input/by-path/platform-3f204000.spi-cs-1-event"

logging.basicConfig(
    filename='/home/dietpi/hello_lcd/touch_debug.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

class FinalReactiveApp(App):
    # Der reaktive State
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
            yield Static("TRUNK TAGGER PI\n\n[ BEREIT ]", id="label")

    def watch_touched(self, value: bool) -> None:
        """Wird automatisch aufgerufen, wenn self.touched sich ändert."""
        main = self.query_one("#main")
        label = self.query_one("#label")
        
        if value:
            main.styles.background = "#004400"
            main.styles.border = ("double", "#FFFF00")
            label.update("TRUNK TAGGER PI\n\n[ BERÜHRT ]")
        else:
            main.styles.background = "#000000"
            main.styles.border = ("round", "#00FF00")
            label.update("TRUNK TAGGER PI\n\n[ BEREIT ]")

    def action_trigger_touch(self):
        """Wird vom Hardware-Thread aufgerufen."""
        logging.info("Hardware-Touch erkannt -> State-Wechsel")
        self.touched = not self.touched

    def on_mount(self) -> None:
        self.run_worker(self.touch_monitor, thread=True)

    async def touch_monitor(self):
        """Direktes Lesen der Kernel-Events."""
        try:
            with open(TOUCH_PATH, 'rb') as f:
                while True:
                    data = f.read(24) # Liest einen evdev Event-Block
                    if data:
                        self.call_from_thread(self.action_trigger_touch)
                        import time
                        time.sleep(0.3) # Entprellen
                        os.read(f.fileno(), 1024) # Buffer leeren
        except Exception as e:
            logging.error(f"Monitor-Fehler: {e}")

if __name__ == "__main__":
    FinalReactiveApp().run()