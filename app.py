import logging
import os
from textual.app import App, ComposeResult
from textual.widgets import Button
from textual.containers import Container
from textual.reactive import reactive
from textual.events import Click

# touch monitor module
from tagtapperpi_comp import touch as touch_mod

# Hardware-Pfad (Bleibt gleich, da Kernel-Ebene)
TOUCH_PATH = "/dev/input/by-path/platform-3f204000.spi-cs-1-event"

# Logging: Jetzt im korrekten Projektordner
logging.basicConfig(
    filename='/home/dietpi/tag-tapper-pi/app.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

class TagTapperApp(App):
    """
    Haupt-App für den Trunk Tagger.
    Reagiert auf Kernel-Events des Touchscreens.
    """
    # Der reaktive State für den visuellen Effekt
    touched = reactive(False)

    CSS = """
    #main {
        align: center middle;
        width: 100%;
        height: 100%;
        content-align: center middle;
        text-style: bold;
    }
    #center_btn {
        width: 288px;
        height: 128px;
        min-width: 288px;
        min-height: 128px;
        max-width: 288px;
        max-height: 128px;
        content-align: center middle;
        text-style: bold;
        padding: 0 1;
        background: #003366;
        color: #ffffff;
        border: solid 3px #00FF00;
        border-radius: 6px;
    }

    #center_btn:pressed {
        background: #002244;
        border-color: #FFFF00;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="main"):
            yield Button("TAG TAPPER PI\n\n[ BEREIT ]", id="center_btn")

    def watch_touched(self, value: bool) -> None:
        """Triggered automatisch bei Änderung von self.touched."""
        try:
            main = self.query_one("#main")
            btn = self.query_one("#center_btn")
            
            if value:
                main.styles.background = "#004400"
                main.styles.border = ("double", "#FFFF00")
                btn.update("TAG TAPPER PI\n\n[ BERÜHRT ]")
            else:
                main.styles.background = "#000000"
                main.styles.border = ("round", "#00FF00")
                btn.update("TAG TAPPER PI\n\n[ BEREIT ]")
        except Exception:
            # Falls die Widgets beim ersten Boot noch nicht bereit sind
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

    # Touch monitoring is handled by tagtapperpi_comp.touch.start_touch_monitor

if __name__ == "__main__":
    try:
        TagTapperApp().run()
    except Exception as e:
        logging.error(f"App konnte nicht starten: {e}")