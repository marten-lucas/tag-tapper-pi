import pygame

# Color palette
BG_COLOR = (0, 0, 0)
HEADER_BG = (0, 51, 102)
TAB_BG = (0, 34, 68)
TAB_ACTIVE_BG = (0, 68, 136)
TAB_HOVER_BG = (0, 51, 102)
TEXT_COLOR = (255, 255, 255)
TEXT_ACTIVE = (0, 255, 0)
BORDER_COLOR = (0, 255, 0)

# Additional common colors used across UI
ACCENT_COLOR = (255, 200, 0)       # for highlights, animations, accents
MUTED_TEXT = (200, 200, 200)       # for secondary text like IPs
OK_COLOR = (0, 200, 0)            # positive status (green dot)
ERROR_COLOR = (200, 60, 60)       # negative status (red X)
NEUTRAL_RING = (60, 60, 60)       # ring/background for action tab
INACTIVE_INDICATOR = (80, 80, 80) # indicator circle when inactive

# Font sizes
HEADER_FONT_SIZE = 22
TAB_TITLE_FONT_SIZE = 26
TITLE_FONT_SIZE = 72
CONTENT_FONT_SIZE = 44

# Optional smaller font for compact tables
SMALL_FONT_SIZE = 32


def load_fonts():
    # Ensure pygame.font was initialized by caller
    return {
        'header': pygame.font.Font(None, HEADER_FONT_SIZE),
        'tab_title': pygame.font.Font(None, TAB_TITLE_FONT_SIZE),
        'title': pygame.font.Font(None, TITLE_FONT_SIZE),
        'content': pygame.font.Font(None, CONTENT_FONT_SIZE),
        'small': pygame.font.Font(None, SMALL_FONT_SIZE),
    }
