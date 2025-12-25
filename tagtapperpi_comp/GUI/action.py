import math

class ActionTab:
    def __init__(self, action_id):
        self.action_id = action_id

    def draw(self, surface, rect, app, styles, fonts):
        # Draw dynamic title/hint with countdown if holding
        if app.long_press_start_time is not None and app.long_press_target == app.active_tab:
            elapsed = time = 0
            try:
                import time as _t
                elapsed = _t.time() - app.long_press_start_time
            except Exception:
                elapsed = 0
            remaining = int(max(0, math.ceil(app.long_press_duration - elapsed)))
            txt = f"Halten zum Bestätigen: {remaining}s"
        else:
            txt = "5s halten zum Bestätigen"

        try:
            title = fonts['title'].render(txt, True, (220, 180, 0))
            surface.blit(title, title.get_rect(center=(rect.centerx, rect.top + 60)))
        except Exception:
            pass

        # Draw the (large) progress ring based on app.long_press_progress
        cx = rect.centerx
        cy = rect.top + 190
        radius = 110
        thickness = 18
        # Background ring
        try:
            pygame = __import__('pygame')
            pygame.draw.circle(surface, (60, 60, 60), (cx, cy), radius, thickness)
            if app.long_press_progress > 0:
                start_angle = -math.pi / 2
                end_angle = start_angle + (app.long_press_progress * 2 * math.pi)
                rectr = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
                pygame.draw.arc(surface, (0, 200, 0), rectr, start_angle, end_angle, thickness)
        except Exception:
            pass
