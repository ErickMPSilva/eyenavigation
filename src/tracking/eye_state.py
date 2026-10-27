"""
Estado dos olhos (aberto, fechando, fechado), com a abertura normal
aprendida por faixa da tela. Bloqueia o olhar durante as piscadas.
"""

import math

import numpy as np

from config import (EYE_BANDS, EYE_GATE_RATIO, EYE_CLOSED_RATIO,
                    EYE_REOPEN_RATIO, EYE_GRACE_MS, EYE_PARTIAL_MAX_MS)

OPEN, GATED, CLOSED = 'aberto', 'fechando', 'fechado'

_BASELINE_RATE = 0.02    # adaptação por frame com o olho aberto (~1,7 s)
_PARTIAL_RATE  = 0.5     # salto da referência após semifechamento longo
_REOPEN_HYST   = 0.03    # histerese para abortar o fechamento
_FACE_LOST_S   = 1.0     # rosto perdido por mais que isso cancela o fechamento


class EyeState:
    def __init__(self, screen_h: int, baselines=None, bands: int = EYE_BANDS):
        self.screen_h = screen_h
        self.bands    = bands
        self._initial = baselines
        self.reset()

    def reset(self):
        b = self._initial
        self._base = (np.array(b, float) if b is not None
                      and np.shape(b) == (self.bands, 2) else None)
        self.state          = OPEN
        self.gate_since     = None
        self.closed_since   = None
        self.last_closed_ms = 0.0
        self.just_reopened  = False
        self.blocked        = False
        self.blinks         = 0
        self.ratio          = (1.0, 1.0)
        self._t_reopen      = -math.inf
        self._t_seen        = None

    def set_baselines(self, baselines):
        self._initial = baselines
        self.reset()

    @property
    def closed(self) -> bool:
        return self.state == CLOSED

    def update(self, openness, gaze_y: float, t: float) -> bool:
        self.just_reopened = False

        if openness is None:
            if (self.state != OPEN and self._t_seen is not None
                    and t - self._t_seen > _FACE_LOST_S):
                self.state = OPEN
                self._t_reopen = t
            self.blocked = True
            return True
        self._t_seen = t

        o = np.asarray(openness, float)
        if self._base is None:
            self._base = np.tile(o, (self.bands, 1))
        ratio = o / np.maximum(self._baseline(gaze_y), 1e-6)
        self.ratio = (float(ratio[0]), float(ratio[1]))
        lo, hi = float(ratio.min()), float(ratio.max())

        if self.state == OPEN:
            if lo < EYE_GATE_RATIO:
                self.state, self.gate_since = GATED, t
            elif (t - self._t_reopen) * 1000 >= EYE_GRACE_MS:
                self._learn(o, gaze_y, _BASELINE_RATE)

        if self.state == GATED:
            if hi < EYE_CLOSED_RATIO:
                self.state, self.closed_since = CLOSED, t
            elif lo >= EYE_GATE_RATIO + _REOPEN_HYST:
                self.state, self._t_reopen = OPEN, t
            elif (t - self.gate_since) * 1000 > EYE_PARTIAL_MAX_MS:
                self._learn(o, gaze_y, _PARTIAL_RATE)
                self.state, self._t_reopen = OPEN, t
        elif self.state == CLOSED:
            if hi > EYE_REOPEN_RATIO:
                self.last_closed_ms = (t - self.closed_since) * 1000
                self.state, self._t_reopen = OPEN, t
                self.just_reopened = True
                self.blinks += 1

        self.blocked = (self.state != OPEN or
                        (t - self._t_reopen) * 1000 < EYE_GRACE_MS)
        return self.blocked

    def _band(self, y: float):
        pos = min(max(y / self.screen_h * self.bands - 0.5, 0.0),
                  self.bands - 1.0)
        i0 = int(pos)
        i1 = min(i0 + 1, self.bands - 1)
        return i0, i1, pos - i0

    def _baseline(self, y: float) -> np.ndarray:
        i0, i1, f = self._band(y)
        return (1 - f) * self._base[i0] + f * self._base[i1]

    def _learn(self, o: np.ndarray, y: float, rate: float):
        i0, i1, f = self._band(y)
        self._base[i0] += rate * (1 - f) * (o - self._base[i0])
        if i1 != i0:
            self._base[i1] += rate * f * (o - self._base[i1])

    @property
    def baselines(self):
        return None if self._base is None else self._base.tolist()
