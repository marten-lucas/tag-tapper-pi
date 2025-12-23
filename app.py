import logging
import os
from textual.app import App, ComposeResult
from textual.widgets import Static
from textual.containers import Container
from textual.reactive import reactive

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
    """

    def compose(self) -> ComposeResult:
        with Container(id="main"):
            yield Static("TAG TAPPER PI\n\n[ BEREIT ]", id="label")

    def watch_touched(self, value: bool) -> None:
        """Triggered automatisch bei Änderung von self.touched."""
        try:
            main = self.query_one("#main")
            label = self.query_one("#label")
            
            if value:
                main.styles.background = "#004400"
                main.styles.border = ("double", "#FFFF00")
                label.update("TAG TAPPER PI\n\n[ BERÜHRT ]")
            else:
                main.styles.background = "#000000"
                main.styles.border = ("round", "#00FF00")
                label.update("TAG TAPPER PI\n\n[ BEREIT ]")
        except Exception:
            # Falls die Widgets beim ersten Boot noch nicht bereit sind
            pass

    def action_trigger_touch(self):
        """Wird vom touch_monitor Thread aufgerufen."""
        logging.info("Hardware-Touch erkannt -> Toggle State")
        self.touched = not self.touched

    def on_mount(self) -> None:
        logging.info("App gestartet. Initialisiere Touch-Monitor...")
        # Startet den Background-Worker für die Hardware-Events
        self.run_worker(self.touch_monitor, thread=True)

    async def touch_monitor(self):
        """Liest Rohdaten direkt aus dem Kernel-Device."""
        try:
            # Prüfen ob Device existiert
            if not os.path.exists(TOUCH_PATH):
                logging.error(f"Device nicht gefunden: {TOUCH_PATH}")
                return

            with open(TOUCH_PATH, 'rb') as f:
                logging.info(f"Touch-Monitor verbunden mit {TOUCH_PATH}")
                while True:
                    data = f.read(24) # Standard evdev event Größe
                    if data:
                        # Event an UI-Thread senden
                        self.call_from_thread(self.action_trigger_touch)
                        
                        # Entprellen: Kurz warten und restliche Daten im Puffer verwerfen
                        import time
                        time.sleep(0.3)
                        try:
                            os.read(f.fileno(), 1024)
                        except BlockingIOError:
                            pass
        except Exception as e:
            logging.error(f"Kritischer Fehler im Monitor: {e}")

if __name__ == "__main__":
    try:
        TagTapperApp().run()
    except Exception as e:
        logging.error(f"App konnte nicht starten: {e}")