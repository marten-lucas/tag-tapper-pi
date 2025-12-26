import time
import pygame

class Tabs:
    def __init__(self):
        # Header and indicator layout
        self.header_height = 35
        self.indicator_radius = 8
        self.indicator_spacing = 24
        self.indicator_margin = 30

    def render(self, surface, app, styles, fonts):
        """Render header (title) and indicators. Returns a content_rect for tabs to draw into.
        """
        w, h = app.width, app.height
        # Header
        header_rect = pygame.Rect(0, 0, w, self.header_height)
        pygame.draw.rect(surface, styles.HEADER_BG, header_rect)

        # Title centered
        try:
            fonts['tab_title'].set_bold(True)
        except Exception:
            pass
        label = app.TABS[app.active_tab]['label']
        tab_label = fonts['tab_title'].render(label, True, styles.TEXT_ACTIVE)
        tab_label_rect = tab_label.get_rect(center=(w // 2, self.header_height // 2))
        surface.blit(tab_label, tab_label_rect)
        try:
            fonts['tab_title'].set_bold(False)
        except Exception:
            pass

        # Left app name
        title = fonts['header'].render('Tag Tapper Pi', True, styles.TEXT_COLOR)
        surface.blit(title, (10, (self.header_height - title.get_height()) // 2))

        # Date/time right
        try:
            import datetime
            now = datetime.datetime.now()
            time_str = now.strftime('%d.%m.%Y %H:%M')
            time_text = fonts['header'].render(time_str, True, styles.TEXT_COLOR)
            surface.blit(time_text, (w - time_text.get_width() - 10, (self.header_height - time_text.get_height()) // 2))
        except Exception:
            pass

        # Indicators at bottom
        total_width = len(app.TABS) * self.indicator_spacing
        start_x = (w - total_width) // 2 + self.indicator_radius
        indicator_y = h - self.indicator_margin
        for i in range(len(app.TABS)):
            x = start_x + i * self.indicator_spacing
            if i == app.active_tab:
                pygame.draw.circle(surface, styles.TEXT_ACTIVE, (x, indicator_y), self.indicator_radius)
            else:
                pygame.draw.circle(surface, (80, 80, 80), (x, indicator_y), self.indicator_radius, 2)

        # Return content rect that avoids header and indicators
        content_top = self.header_height
        content_bottom = indicator_y - (self.indicator_radius * 2) - 12
        return pygame.Rect(0, content_top, w, max(0, content_bottom - content_top))


