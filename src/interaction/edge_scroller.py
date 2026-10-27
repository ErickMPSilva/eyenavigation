"""
Motor do scroll: rola quando o olhar está nas faixas de cima ou de baixo da tela.
"""

import math

from desktop import mouse_backend
from config import (SCROLL_ZONE_TOP, SCROLL_ZONE_BOTTOM, SCROLL_ACTIVATE_MS,
                    SCROLL_HYSTERESIS_PX, SCROLL_MIN_RATE, SCROLL_MAX_RATE,
                    SCROLL_RAMP_MS, SCROLL_PARK_CURSOR, SCROLL_PARK_OFFSET_PX,
                    SCROLL_MAX_RUN_MS, SCROLL_OFFSCREEN_MARGIN,
                    SCROLL_OFFSCREEN_MS, SCROLL_BRAKE_MS)

_RAMP_START = 0.3     # fração da velocidade logo ao ativar


class EdgeScroller:
    def __init__(self, screen_w: int, screen_h: int):
        self.sw = screen_w
        self.sh = screen_h
        self.top_px    = SCROLL_ZONE_TOP * screen_h
        self.bottom_px = SCROLL_ZONE_BOTTOM * screen_h
        self.avoid: list = []
        self.reset()

    def update(self, gx: float, gy: float, t: float, raw=None) -> int:
        dt = 0.0 if self._t_last is None else min(t - self._t_last, 0.1)
        self._t_last = t
        self._gx = gx

        if self._check_offscreen(raw, t):
            return 0

        if self._zone is None:
            cand = self._zone_of(gy)
            if cand is None and self._cand and not self._left_zone(gy, self._cand):
                cand = self._cand
            if cand != self._cand:
                self._cand, self._cand_since = cand, t
            if cand is None or (t - self._cand_since) * 1000 < SCROLL_ACTIVATE_MS:
                return 0
            self._zone, self._engaged = cand, t
            self._exhausted = False
            self._acc = 1.0                     # primeiro passo imediato
        elif self._left_zone(gy):
            self._zone = self._cand = None
            self._exhausted = False
            return 0

        if SCROLL_MAX_RUN_MS and (t - self._engaged) * 1000 >= SCROLL_MAX_RUN_MS:
            self._exhausted = True
        if self._exhausted:
            return 0

        depth = self._depth(gy)
        ramp = min(1.0, _RAMP_START + (1 - _RAMP_START)
                   * (t - self._engaged) * 1000 / SCROLL_RAMP_MS)
        rate = SCROLL_MIN_RATE + (SCROLL_MAX_RATE - SCROLL_MIN_RATE) * depth
        self._acc += rate * ramp * dt
        n = int(self._acc)
        if not n:
            return 0
        self._acc -= n
        clicks = n if self._zone == 'top' else -n
        px, py = self.park_point or (None, None)
        mouse_backend.scroll(clicks, px, py)
        self.last_notch_t = t
        return clicks

    def pause(self, t: float):
        self._t_last = t

    @property
    def active_zone(self) -> str | None:
        return None if self._exhausted else self._zone

    @property
    def engaged(self) -> bool:
        return (self._cand is not None or self._zone is not None) and not self._exhausted

    @property
    def exhausted(self) -> bool:
        return self._exhausted

    @property
    def offscreen(self) -> bool:
        return self._offscreen

    def moving(self, t: float) -> bool:
        """Rolando agora ou há menos de SCROLL_BRAKE_MS."""
        return (self.active_zone is not None
                or (t - self.last_notch_t) * 1000 < SCROLL_BRAKE_MS)

    def zone_of(self, gy: float) -> str | None:
        return self._zone_of(gy)

    @property
    def park_point(self) -> tuple[int, int] | None:
        """Onde o cursor deve ficar enquanto rola (None = seguir o olhar)."""
        if self.active_zone is None or not SCROLL_PARK_CURSOR:
            return None
        x = min(max(self._gx, 0.1 * self.sw), 0.9 * self.sw)
        if self._zone == 'top':
            y = self.top_px + SCROLL_PARK_OFFSET_PX
        else:
            y = self.sh - self.bottom_px - SCROLL_PARK_OFFSET_PX
        for x0, y0, x1, y1 in self.avoid:
            if x0 <= x <= x1 and y0 <= y <= y1:
                x = x0 - 1 if x0 - 1 >= 0.1 * self.sw else x1 + 1
        return int(x), int(y)

    @property
    def activation(self) -> float:
        if self._zone is not None:
            return 1.0
        if self._cand is None or self._t_last is None:
            return 0.0
        return min(1.0, (self._t_last - self._cand_since) * 1000
                   / SCROLL_ACTIVATE_MS)

    def reset(self):
        self._zone       = None
        self._cand       = None
        self._cand_since = 0.0
        self._engaged    = 0.0
        self._acc        = 0.0
        self._t_last     = None
        self._gx         = self.sw / 2
        self._exhausted  = False
        self._offscreen  = False
        self._off_since  = None
        self.last_notch_t = -math.inf

    def _check_offscreen(self, raw, t: float) -> bool:
        m = SCROLL_OFFSCREEN_MARGIN
        if raw is None or not m:
            return False
        x, y = raw
        out = (x < -m * self.sw or x > (1 + m) * self.sw
               or y < -m * self.sh or y > (1 + m) * self.sh)
        if not out:
            self._off_since = None
            self._offscreen = False
            return False
        if self._off_since is None:
            self._off_since = t
        if (t - self._off_since) * 1000 >= SCROLL_OFFSCREEN_MS:
            self._offscreen = True
            self._zone = self._cand = None
            self._exhausted = False
        return self._offscreen

    def _zone_of(self, gy: float) -> str | None:
        if gy < self.top_px:
            return 'top'
        if gy > self.sh - self.bottom_px:
            return 'bottom'
        return None

    def _left_zone(self, gy: float, zone: str | None = None) -> bool:
        if (zone or self._zone) == 'top':
            return gy > self.top_px + SCROLL_HYSTERESIS_PX
        return gy < self.sh - self.bottom_px - SCROLL_HYSTERESIS_PX

    def _depth(self, gy: float) -> float:
        if self._zone == 'top':
            d = (self.top_px - gy) / self.top_px
        else:
            d = (gy - (self.sh - self.bottom_px)) / self.bottom_px
        return min(max(d, 0.0), 1.0)
