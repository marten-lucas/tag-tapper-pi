import math

try:
    import pygame
except Exception:
    pygame = None


class ActionTab:
    def __init__(self, action_id):
        self.action_id = action_id

    def draw(self, surface, rect, app, styles, fonts):
        """Draw a large progress ring centered in the available content `rect`.
        The ring size adapts to the `rect` so it never overlaps header or indicators.
        The action name ('reboot'/'shutdown') is drawn small inside the ring.
        """
        # Compute center and maximum radius that fits into `rect` (leave padding)
        padding = 24
        cx = rect.centerx
        cy = rect.centery
        max_radius = min((rect.width, rect.height)) // 2 - padding
        if max_radius < 20:
            max_radius = 20

        radius = int(max_radius)
        thickness = max(8, int(radius * 0.15))

        # Draw background ring
        if pygame is None:
            return
        
        pygame.draw.circle(surface, (60, 60, 60), (cx, cy), radius, thickness)

        # Draw progress arc
        if app.long_press_progress > 0:
            start_angle = -math.pi / 2
            end_angle = start_angle + (app.long_press_progress * 2 * math.pi)
            arc_rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
            pygame.draw.arc(surface, (0, 200, 0), arc_rect, start_angle, end_angle, thickness)

        # Draw small action label inside the ring
        label_txt = self.action_id.capitalize()
        lbl = fonts['content'].render(label_txt, True, (220, 180, 0))
        lbl_rect = lbl.get_rect(center=(cx, cy))
        surface.blit(lbl, lbl_rect)
