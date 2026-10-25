"""The 9:16 safe zone: nothing the editor adds (cards, effects, credits, end cards) may sit where the platform's own
UI covers it. TikTok is the tightest of TikTok, Reels and Shorts, so its UI sets the margins (1080x1920): the tabs
and search bar at the top, the username, caption and sound line at the bottom (about 25% of the height with a
two-line caption), and the avatar / like / comment / save / share column on the right (about 13% of the width).
Every placement reads these numbers; keep them here, never copied into a module."""
TOP, BOTTOM = 0.13, 0.25  # margins, fractions of the height
LEFT, RIGHT = 0.04, 0.13  # margins, fractions of the width
X0, Y0, X1, Y1 = LEFT, TOP, 1 - RIGHT, 1 - BOTTOM  # the safe rectangle


def inside(box, W: int, H: int, slack: float = 0.005) -> bool:
    """Whether a pixel box (x0, y0, x1, y1) sits inside the safe rectangle of a W x H frame."""
    x0, y0, x1, y1 = box
    return (x0 >= (X0 - slack) * W and x1 <= (X1 + slack) * W and y0 >= (Y0 - slack) * H
            and y1 <= (Y1 + slack) * H)
