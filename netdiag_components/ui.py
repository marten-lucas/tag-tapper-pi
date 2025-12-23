import os
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane, Button
from textual.containers import Horizontal

class NetDiagApp(App):
    # Absoluter Pfad zur CSS-Datei
    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles.tcss")

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        # Tabs: IPs, Pings, WiFi, System
        with TabbedContent():
            with TabPane("IPs"):
                yield Static("IP-Übersicht (TODO)", id="ip_table")

            with TabPane("Pings"):
                yield Static("Ping-Matrix (TODO)", id="ping_table")

            with TabPane("WiFi"):
                yield Static("WiFi Status (TODO)", id="wifi_status")

            with TabPane("System"):
                # Große Touch-Buttons für Systemsteuerung
                yield Button("REBOOT", id="reboot", classes="danger")
                yield Button("POWEROFF", id="poweroff", classes="danger")

        # Navigation Buttons (Karussell)
        with Horizontal(id="nav"):
            yield Button("<<", id="prev", classes="nav")
            yield Button(">>", id="next", classes="nav")

        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed):
        # Hier kommen später reboot/poweroff Logik oder Tab-Wechsel
        if event.button.id in ("prev", "next"):
            tabs = self.query_one(TabbedContent)
            delta = -1 if event.button.id == "prev" else 1
            tabs.active = (tabs.active + delta) % len(tabs.tabs)
