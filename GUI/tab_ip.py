import socket

class TabIP:
    def draw(self, surface, rect, app, styles, fonts):
        # Title
        title = fonts['title'].render("Netzwerk", True, styles.TEXT_ACTIVE)
        surface.blit(title, title.get_rect(center=(rect.centerx, rect.top + 60)))

        # Try to determine primary IP (best-effort)
        ip = "unbekannt"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
        except Exception:
            pass

        info = fonts['content'].render(f"IP: {ip}", True, (200, 200, 200))
        surface.blit(info, info.get_rect(center=(rect.centerx, rect.top + 140)))
