import logging
import os
from textual.app import App, ComposeResult
from textual.widgets import Button
from textual.containers import Container
from textual.reactive import reactive
from textual.events import Click
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
    CSS_PATH = os.path.join(os.path.dirname(__file__), "tagtapperpi_comp", "styles.tcss")
    touched = reactive(False)

    def compose(self) -> ComposeResult:
        with Container(id="main"):
            yield Button("TAG TAPPER PI\n\n[ BEREIT ]", id="center_btn")

    def watch_touched(self, value: bool) -> None:
        """Triggered automatisch bei Änderung von self.touched."""
        try:
            btn = self.query_one("#center_btn")
            if value:
                btn.update("TAG TAPPER PI\n\n[ BERÜHRT ]")
            else:
                btn.update("TAG TAPPER PI\n\n[ BEREIT ]")
        except Exception:
            pass

    def action_trigger_touch(self):
        """Wird vom touch_monitor Thread aufgerufen."""
        logging.info("Hardware-Touch erkannt -> Toggle State")
        self.touched = not self.touched

    def on_click(self, event: Click) -> None:
        """Handle UI clicks on widgets (e.g. for testing without hardware).

        If the `label` widget is clicked, toggle the touched state.
        """
        try:
            if getattr(event.sender, "id", None) == "center_btn":
                logging.info("UI-Click erkannt -> Toggle State")
                self.touched = not self.touched
        except Exception:
            pass

    def on_mount(self) -> None:
        logging.info("App gestartet. Initialisiere Touch-Monitor...")
        # Start the external touch monitor (reads kernel device in background)
        touch_mod.start_touch_monitor(self, TOUCH_PATH)

if __name__ == "__main__":
    try:
        TagTapperApp().run()
    except Exception as e:
        logging.error(f"App konnte nicht starten: {e}")