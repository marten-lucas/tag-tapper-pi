import pygame

# Color palette (friendly theme)
BG_COLOR = (0, 0, 0)                 # 000000 background
HEADER_BG = (11, 124, 141)           # 0B7C8D app bar
TAB_BG = (26, 166, 157)              # 1AA69D table header
TAB_ACTIVE_BG = (20, 133, 126)       # darker variant of 1AA69D
TAB_HOVER_BG = (16, 110, 104)        # darker variant
TEXT_COLOR = (255, 255, 255)
TEXT_ACTIVE = (237, 154, 23)         # accent for active labels
BORDER_COLOR = (26, 166, 157)        # border accents

# Additional common colors used across UI
ACCENT_COLOR = (237, 154, 23)        # ED9A17 for highlights/animations/mid-range
MUTED_TEXT = (200, 200, 200)         # secondary text like IPs
OK_COLOR = (48, 155, 64)             # 309B40 success (green dot)
ERROR_COLOR = (225, 85, 20)          # E15514 error (red/orange)
NEUTRAL_RING = (60, 60, 60)          # ring/background for action tab
INACTIVE_INDICATOR = (120, 120, 120) # indicator circle when inactive

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
