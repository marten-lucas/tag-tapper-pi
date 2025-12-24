import logging
import os
from textual.app import App, ComposeResult
from textual.widgets import Static, TabbedContent, TabPane, Header, Footer
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
    Screen {
        background: #000000;
    }
    
    Header {
        background: #003366;
        color: #ffffff;
    }
    
    TabbedContent {
        height: 100%;
    }
    
    /* Large touch-friendly tabs with equal width */
    Tabs {
        background: #001122;
        height: 4;
    }
    
    Tab {
        height: 3;
        width: 1fr;
        padding: 0;
        background: #002244;
        color: #aaaaaa;
        text-style: bold;
        content-align: center bottom;
        text-align: center;
    }
    
    Tab:hover {
        background: #003366;
    }
    
    Tab.-active {
        background: #004488;
        color: #00ff00;
        text-style: bold;
    }
    
    TabPane {
        padding: 2;
        background: #000000;
    }
    
    .tab-content {
        align: center middle;
        width: 100%;
        height: 100%;
        content-align: center middle;
        text-align: center;
        text-style: bold;
        color: #00ff00;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with TabbedContent(initial="ip"):
            with TabPane("IP", id="ip"):
                yield Container(Static("IP Configuration\n\nComing soon...", classes="tab-content"))
            with TabPane("Ping", id="ping"):
                yield Container(Static("Ping Test\n\nComing soon...", classes="tab-content"))
            with TabPane("Range", id="range"):
                yield Container(Static("Range Scanner\n\nComing soon...", classes="tab-content"))
            with TabPane("Power", id="power"):
                yield Container(Static("Power Options\n\nComing soon...", classes="tab-content"))

    # Touch events are now handled by Textual's built-in mouse event system
    # The touch monitor posts MouseDown events that Textual routes to widgets

    def on_mount(self) -> None:
        logging.info("App gestartet. Initialisiere Touch-Monitor...")
        # Start the external touch monitor (reads kernel device in background)
        touch_mod.start_touch_monitor(self, TOUCH_PATH)

if __name__ == "__main__":
    try:
        TagTapperApp().run()
    except Exception as e:
        logging.error(f"App konnte nicht starten: {e}")