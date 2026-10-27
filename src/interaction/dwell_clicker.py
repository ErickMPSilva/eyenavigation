"""
Clique por fixação do olhar (dwell). Desligado por padrão.
"""

from desktop import mouse_backend
from config import DWELL_TIME_MS, DWELL_RADIUS_PX, DWELL_REARM_PX


class DwellClicker:
    def __init__(self):
        self._ax:      float | None = None
        self._ay:      float | None = None
        self._t_start: float | None = None
        self._fired:   bool         = False
        self._t_now:   float        = 0.0
        self._click_count: int      = 0

    def update(self, gx: int, gy: int, t: float) -> bool:
        self._t_now = t
        if self._ax is None:
            self._reset_anchor(gx, gy)
            return False

        dist = _dist(gx, gy, self._ax, self._ay)

        if self._fired:
            if dist > DWELL_REARM_PX:
                self._reset_anchor(gx, gy)
            return False

        if dist > DWELL_RADIUS_PX:
            self._reset_anchor(gx, gy)
            return False

        elapsed_ms = (t - self._t_start) * 1000
        if elapsed_ms >= DWELL_TIME_MS:
            ax, ay = int(self._ax), int(self._ay)
            self._click_count += 1
            print(f'[DwellClicker] CLIQUE #{self._click_count} '
                  f'em ({ax}, {ay}) — backend: {mouse_backend.BACKEND}')
            mouse_backend.click(ax, ay)
            self._fired = True
            return True

        return False

    @property
    def progress(self) -> float:
        if self._t_start is None or self._fired:
            return 0.0
        elapsed = (self._t_now - self._t_start) * 1000
        return min(elapsed / DWELL_TIME_MS, 1.0)

    @property
    def anchor(self) -> tuple:
        return (self._ax, self._ay)

    def reset(self):
        self._ax      = None
        self._ay      = None
        self._t_start = None
        self._fired   = False

    def _reset_anchor(self, gx: int, gy: int):
        self._ax      = float(gx)
        self._ay      = float(gy)
        self._t_start = self._t_now
        self._fired   = False


def _dist(x1, y1, x2, y2) -> float:
    return ((x1 - x2) ** 2 + (y1 - y2) ** 2) ** 0.5
