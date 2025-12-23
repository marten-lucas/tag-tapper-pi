import os
from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane, Button
from textual.containers import Horizontal, Vertical, Container

class NetDiagApp(App):
    # CSS-Datei laden (lokal im Paketordner)
    CSS_PATH = os.path.join(os.path.dirname(__file__), "styles.tcss")

    TITLE = "Tag Tapper"
    SUB_TITLE = "Netzwerk-Dashboard"

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    def compose(self) -> ComposeResult:
        # Kopfzeile mit Uhr
        yield Header(show_clock=True)

        # Hauptinhalte: 4 Tabs
        with TabbedContent(id="tabs"):
            with TabPane("IPs", id="tab_ips"):
                # Platzhalter – später DataTable
                with Container(id="ip_container"):
                    yield Static("IP-Übersicht (TODO)", id="ip_table")

            with TabPane("Pings", id="tab_pings"):
                with Container(id="ping_container"):
                    yield Static("Ping-Matrix (TODO)", id="ping_table")

            with TabPane("WiFi", id="tab_wifi"):
                with Container(id="wifi_container"):
                    yield Static("WiFi Status (TODO)", id="wifi_status")

            with TabPane("System", id="tab_system"):
                # Große Touch-Buttons (volle Breite)
                with Vertical(id="system_buttons"):
                    yield Button("REBOOT", id="reboot", classes="danger flat large full")
                    yield Button("POWEROFF", id="poweroff", classes="danger flat large full")

        # Feste Navigation unten – rechts ausgerichtet
        with Horizontal(id="nav"):
            yield Button("<<", id="prev", classes="nav flat large")
            yield Button(">>", id="next", classes="nav flat large")

        # Fußzeile
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed):
        # Tab-Navigation (Karussell)
        if event.button.id in ("prev", "next"):
            tabs = self.query_one(TabbedContent)
            delta = -1 if event.button.id == "prev" else 1
            
            # Finde Index der aktuell aktiven Tab
            tab_ids = [tab.id for tab in tabs.query(TabPane)]
            current_index = tab_ids.index(tabs.active) if tabs.active in tab_ids else 0
            
            # Berechne neuen Index (mit Wrap-around)
            new_index = (current_index + delta) % len(tab_ids)
            tabs.active = tab_ids[new_index]

        # System-Buttons – Logik folgt später
        if event.button.id == "reboot":
            pass
        if event.button.id == "poweroff":
            pass
