class TabPing:
    def draw(self, surface, rect, app, styles, fonts):
        title = fonts['title'].render("Ping", True, styles.TEXT_ACTIVE)
        surface.blit(title, title.get_rect(center=(rect.centerx, rect.top + 60)))

        # Placeholder content
        info = fonts['content'].render("Ping Test: Noch nicht implementiert", True, (200, 200, 200))
        surface.blit(info, info.get_rect(center=(rect.centerx, rect.top + 140)))
