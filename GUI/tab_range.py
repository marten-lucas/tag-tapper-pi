class TabRange:
    def draw(self, surface, rect, app, styles, fonts):
        title = fonts['title'].render("Range", True, styles.TEXT_ACTIVE)
        surface.blit(title, title.get_rect(center=(rect.centerx, rect.top + 60)))

        info = fonts['content'].render("Range Scanner: Noch nicht implementiert", True, styles.MUTED_TEXT)
        surface.blit(info, info.get_rect(center=(rect.centerx, rect.top + 140)))
