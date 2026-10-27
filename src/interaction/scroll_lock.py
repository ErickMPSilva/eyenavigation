"""
Trava do scroll. Começa travado; uma piscada lenta na alça (meio da borda
direita) destrava ou trava, uma piscada durante a rolagem freia, e há
travas automáticas (clique, zoom, ociosidade, rosto ausente).
"""

import math
from collections import deque

import numpy as np

import config

PROMISES = ('scroll_unlock', 'scroll_lock', 'scroll_brake')
_CLAIM_MAX_AGE_S = 0.5
_GAP_S           = 0.5     # lacuna entre observações que reinicia o dwell


class ScrollLock:
    def __init__(self, screen_w: int, screen_h: int, enabled: bool | None = None):
        self.sw, self.sh = screen_w, screen_h
        self.enabled = config.SCROLL_LOCK_ENABLED if enabled is None else enabled
        self.width  = float(config.SCROLL_HANDLE_WIDTH_PX)
        self.half_h = config.SCROLL_HANDLE_HALF_H * screen_h
        self.events: list = []
        self.locked = self.enabled and config.SCROLL_START_LOCKED
        self.notches = 0
        self._hist: deque = deque(maxlen=90)
        self._reset_gaze()
        self._last_activity = None
        self._face_lost_since = None
        self._hint_until = -math.inf
        self._t_hint_last = -math.inf

    def _reset_gaze(self):
        self._t_in = None
        self._t_dwell = None
        self._t_obs = None
        self.in_handle = False
        self.lit = False
        self.view = None
        self._dwell_armed = True
        self._band_since = None
        self._hinted = False

    @property
    def regions(self) -> list:
        if not self.enabled:
            return []
        cy = config.SCROLL_HANDLE_CY * self.sh
        y0, y1 = cy - self.half_h, cy + self.half_h
        side = config.SCROLL_HANDLE_SIDE
        out = []
        if side in ('right', 'both'):
            out.append((self.sw - self.width, y0, float(self.sw), y1))
        if side in ('left', 'both'):
            out.append((0.0, y0, self.width, y1))
        return out

    def fit_to_error(self, error_px):
        if (not self.enabled or not config.SCROLL_HANDLE_FIT_ERROR
                or error_px is None or not np.isfinite(error_px)):
            return
        self.width = float(np.clip(error_px, config.SCROLL_HANDLE_WIDTH_PX,
                                   config.SCROLL_HANDLE_MAX_WIDTH_PX))
        self.half_h = float(np.clip(2.5 * error_px,
                                    config.SCROLL_HANDLE_HALF_H * self.sh,
                                    config.SCROLL_HANDLE_MAX_HALF_H * self.sh))

    def _inside(self, x: float, y: float, margin: float) -> bool:
        for x0, y0, x1, y1 in self.regions:
            lo = -math.inf if x0 <= 0 else x0 - margin
            hi = math.inf if x1 >= self.sw else x1 + margin
            if lo <= x <= hi and y0 - margin <= y <= y1 + margin:
                return True
        return False

    def observe(self, gx: float, gy: float, t: float, moving: bool,
                in_band: bool, engaged: bool):
        if not self.enabled:
            return
        gap = self._t_obs is not None and t - self._t_obs > _GAP_S
        self._t_obs = t
        margin = config.SCROLL_HANDLE_MARGIN_PX if self._t_in is not None else 0
        inside = self._inside(gx, gy, margin)
        if inside:
            if self._t_in is None:
                self._t_in = self._t_dwell = t
            elif gap:
                self._t_dwell = t
        else:
            self._t_in = self._t_dwell = None
            self._dwell_armed = True
        self.in_handle = inside
        self.lit = inside and (t - self._t_in) * 1000 >= config.SCROLL_HANDLE_MIN_FIX_MS

        moving = moving and not self.locked
        if self.lit:
            promise = 'scroll_unlock' if self.locked else 'scroll_lock'
        elif moving:
            promise = 'scroll_brake'
        else:
            promise = None
        self._hist.append((t, promise))

        # A bola mostra o que uma piscada que começasse AGORA faria: a
        # promessa de BLINK_POS_LOOKBACK_MS atrás, a mesma que ela consultaria
        effective = self.claim(t - config.BLINK_POS_LOOKBACK_MS / 1000)
        self.view = ('handle' if effective in ('scroll_unlock', 'scroll_lock')
                     else 'scroll' if effective == 'scroll_brake'
                     else None if self.locked else 'unlocked')

        # Olhar uma faixa ou a alça é atividade: a trava por ociosidade não
        # pode disparar enquanto o usuário vai travar pela alça
        if not self.locked and (engaged or inside):
            self._last_activity = t

        if self.locked and in_band and not self.lit:
            if self._band_since is None:
                self._band_since = t
            if (not self._hinted
                    and (t - self._band_since) * 1000 >= config.SCROLL_HINT_MS
                    and t - self._t_hint_last >= config.SCROLL_HINT_EVERY_S):
                self._hinted = True
                self._t_hint_last = t
                self._hint_until = t + config.SCROLL_HINT_DURATION_MS / 1000
        else:
            self._band_since = None
            self._hinted = False

    def pause(self, t: float, zone_active: bool, carry: bool = False):
        if not self.enabled:
            return
        if not self.locked and zone_active:
            self._last_activity = t
        if carry and self._hist:
            self._hist.append((t, self._hist[-1][1]))

    def claim(self, t_ref: float) -> str | None:
        """Promessa vigente no instante t_ref (para o BlinkClicker)."""
        for ts, promise in reversed(self._hist):
            if ts <= t_ref:
                return promise if t_ref - ts <= _CLAIM_MAX_AGE_S else None
        return None

    def note_scroll(self, t: float, clicks: int):
        if clicks:
            self.notches += abs(clicks)
            self._last_activity = t

    def tick(self, t: float, face_ok: bool) -> str | None:
        if face_ok:
            self._face_lost_since = None
        elif self._face_lost_since is None:
            self._face_lost_since = t
        if not self.enabled or self.locked:
            return None
        lost_ms = config.SCROLL_LOCK_FACE_LOST_MS
        if (lost_ms and self._face_lost_since is not None
                and (t - self._face_lost_since) * 1000 >= lost_ms):
            return 'rosto'
        idle_ms = config.SCROLL_IDLE_LOCK_MS
        if (idle_ms and self._last_activity is not None
                and (t - self._last_activity) * 1000 >= idle_ms):
            return 'ocioso'
        return None

    def dwell_toggle(self, t: float, blink_on: bool) -> str | None:
        if not self.enabled or not self.lit:
            return None
        if blink_on:
            self._t_dwell = t
            return None
        if (not self._dwell_armed or self._t_dwell is None
                or (t - self._t_dwell) * 1000 < config.SCROLL_HANDLE_DWELL_MS):
            return None
        self._dwell_armed = False
        return 'scroll_unlock' if self.locked else 'scroll_lock'

    def lock(self, t: float, reason: str) -> bool:
        if not self.enabled or self.locked:
            return False
        self.locked = True
        self.events.append((t, True, reason, self.notches))
        self._hint_until = -math.inf
        self._band_since = None
        return True

    def unlock(self, t: float, reason: str) -> bool:
        if not self.enabled or not self.locked:
            return False
        self.locked = False
        self.notches = 0
        self._last_activity = t
        self.events.append((t, False, reason, 0))
        return True

    def apply(self, promise: str, t: float, reason: str) -> bool:
        if promise == 'scroll_unlock':
            return self.unlock(t, reason)
        return self.lock(t, reason)

    @property
    def allows_scroll(self) -> bool:
        return not self.enabled or not self.locked

    def hint_active(self, t: float) -> bool:
        return t < self._hint_until

    def pulse_on(self, t: float) -> bool:
        hz = config.SCROLL_HANDLE_PULSE_HZ
        return bool(hz) and int(t * 2 * hz) % 2 == 0

    def seconds_to_idle_lock(self, t: float) -> float | None:
        idle_ms = config.SCROLL_IDLE_LOCK_MS
        if self.locked or not idle_ms or self._last_activity is None:
            return None
        return max(0.0, idle_ms / 1000 - (t - self._last_activity))
