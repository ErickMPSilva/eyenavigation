"""
Move o cursor do sistema para o ponto de olhar.
"""

from desktop import mouse_backend
from config import CURSOR_MOVE, CURSOR_DEADZONE_PX


class CursorController:
    def __init__(self, screen_w: int, screen_h: int):
        self.sw = screen_w
        self.sh = screen_h
        self._last: tuple[int, int] | None = None

    def move(self, x: float, y: float):
        if not CURSOR_MOVE:
            return
        cx = int(max(0, min(x, self.sw - 1)))
        cy = int(max(0, min(y, self.sh - 1)))
        if (self._last is not None
                and abs(cx - self._last[0]) < CURSOR_DEADZONE_PX
                and abs(cy - self._last[1]) < CURSOR_DEADZONE_PX):
            return
        self._last = (cx, cy)
        mouse_backend.move(cx, cy)
