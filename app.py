import logging
import os
from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Container
from textual.reactive import reactive
from tagtapperpi_comp import touch as touch_mod

TOUCH_PATH = "/dev/input/by-path/platform-3f204000.spi-cs-1-event"
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tag-tapper-pi.log")

# Configure logging to file only - prevent any console output
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Prevent Textual's internal logging from going to console
logging.getLogger("textual").setLevel(logging.WARNING)
logging.getLogger("textual").handlers = []
logging.getLogger("textual").addHandler(logging.FileHandler(LOG_PATH))

class TagTapperApp(App):
    """Einfache TUI mit Touch-Button."""
    touched = reactive(False)

    CSS = """
    #main {
        align: center middle;
        width: 100%;
        height: 100%;
    }
    
    #label {
        width: 30;
        height: 9;
        content-align: center middle;
        text-align: center;
        text-style: bold;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="main"):
            yield Static("Touch me", id="label")

    def watch_touched(self, value: bool) -> None:
        """Triggered automatisch bei Änderung von self.touched."""
        label = self.query_one("#label")
        
        if value:
            label.styles.background = "#004400"
            label.styles.border = ("double", "#FFFF00")
            label.update("Touched!")
        else:
            label.styles.background = "#003366"
            label.styles.border = ("round", "#00FF00")
            label.update("Touch me")

    def action_trigger_touch(self):
        """Wird vom touch_monitor Thread aufgerufen."""
        logging.info("Hardware-Touch erkannt -> Toggle State")
        self.touched = not self.touched

    def on_mount(self) -> None:
        logging.info("App gestartet. Initialisiere Touch-Monitor...")
        # Start the external touch monitor (reads kernel device in background)
        touch_mod.start_touch_monitor(self, TOUCH_PATH)

if __name__ == "__main__":
    try:
        TagTapperApp().run()
    except Exception as e:
        logging.error(f"App konnte nicht starten: {e}")