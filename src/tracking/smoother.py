"""
Suavização do olhar. Padrão: filtro de fixação (média durante a fixação,
salto quando uma sacada é confirmada). One Euro e EMA ficam para comparação.
"""

import math
import time
from collections import deque

import numpy as np

from config import (SMOOTHER, SMOOTH_ALPHA, MEDIAN_WINDOW,
                    ONE_EURO_MIN_CUTOFF, ONE_EURO_BETA, ONE_EURO_D_CUTOFF,
                    FIX_WINDOW_MS, FIX_SACCADE_SIGMAS, FIX_SACCADE_FRAMES,
                    FIX_NOISE_INIT_PX, FIX_NOISE_MIN_PX, FIX_NOISE_MAX_PX,
                    FIX_TAU_MS, FIX_TAU_SACCADE_MS)

_NOISE_RATE       = 0.01   # adaptação do ruído por amostra (~3 s a 30 fps)
_TRUNC_CORRECTION = 1.05   # resíduos só dentro do limiar subestimam a variância
_FALSE_SACCADE_UP = 1.15   # aumento do ruído após "sacada" que não saiu do lugar
_FAST_OUTPUT_S    = 0.25   # tempo de saída rápida após a sacada
_HISTORY_S        = 2.0


class FixationFilter:
    def __init__(self, window_ms: float = FIX_WINDOW_MS,
                 sigmas: float = FIX_SACCADE_SIGMAS,
                 confirm: int = FIX_SACCADE_FRAMES,
                 noise: tuple = FIX_NOISE_INIT_PX,
                 noise_min: float = FIX_NOISE_MIN_PX,
                 noise_max: float = FIX_NOISE_MAX_PX,
                 tau_ms: float = FIX_TAU_MS,
                 tau_saccade_ms: float = FIX_TAU_SACCADE_MS):
        self.window    = window_ms / 1000
        self.k2        = sigmas ** 2
        self.confirm   = max(1, int(confirm))
        self.noise_min = noise_min
        self.noise_max = noise_max
        self.tau       = tau_ms / 1000
        self.tau_fast  = tau_saccade_ms / 1000
        self.sigma     = np.clip(np.array(noise, float), noise_min, noise_max)
        self.saccades  = 0
        self.reset()

    def reset(self):
        self._fix: deque = deque()
        self._cand: deque = deque()
        self._centroid: np.ndarray | None = None
        self._out: np.ndarray | None = None
        self._t_out = None
        self._t_saccade = -math.inf
        self.fixation_start: float | None = None

    def set_noise(self, sx: float, sy: float):
        self.sigma = np.clip(np.array([sx, sy], float),
                             self.noise_min, self.noise_max)

    @property
    def radius(self) -> np.ndarray:
        return self.sigma * math.sqrt(self.k2)

    def _d2(self, p: np.ndarray, c: np.ndarray) -> float:
        return float((((p - c) / self.sigma) ** 2).sum())

    def update(self, x: float, y: float, t: float) -> tuple[float, float]:
        p = np.array([x, y], float)

        if self._centroid is None:
            self._start([(t, x, y)], t, first=True)
        elif self._d2(p, self._centroid) <= self.k2:
            self._cand.clear()
            if len(self._fix) >= 6:
                r2 = (p - self._centroid) ** 2 * _TRUNC_CORRECTION
                var = self.sigma ** 2 + _NOISE_RATE * (r2 - self.sigma ** 2)
                self.sigma = np.clip(np.sqrt(var), self.noise_min, self.noise_max)
            self._fix.append((t, x, y))
            while len(self._fix) > 1 and t - self._fix[0][0] > self.window:
                self._fix.popleft()
            self._centroid = np.mean([s[1:] for s in self._fix], axis=0)
        else:
            self._cand.append((t, x, y))
            if len(self._cand) >= self.confirm:
                last = list(self._cand)[-self.confirm:]
                pts  = np.array([s[1:] for s in last])
                m    = pts.mean(axis=0)
                if all(self._d2(q, m) <= self.k2 for q in pts):
                    old = self._centroid
                    self._start(last, t)
                    if self._d2(m, old) < 2.25 * self.k2:
                        # "Sacada" que quase não saiu do lugar: era ruído
                        self.sigma = np.minimum(self.sigma * _FALSE_SACCADE_UP,
                                                self.noise_max)
                else:
                    self._cand.popleft()

        return self._output(t)

    def hold(self):
        self._cand.clear()

    def _start(self, samples: list, t: float, first: bool = False):
        self._fix = deque(samples)
        self._cand.clear()
        self._centroid = np.mean([s[1:] for s in samples], axis=0)
        self.fixation_start = samples[0][0]
        if not first:
            self._t_saccade = t
            self.saccades += 1

    def _output(self, t: float) -> tuple[float, float]:
        if self._out is None:
            self._out = self._centroid.copy()
        else:
            dt  = max(t - self._t_out, 1e-3)
            tau = self.tau_fast if t - self._t_saccade < _FAST_OUTPUT_S else self.tau
            self._out += (1 - math.exp(-dt / tau)) * (self._centroid - self._out)
        self._t_out = t
        return float(self._out[0]), float(self._out[1])


class EMASmoother:
    def __init__(self, alpha: float = SMOOTH_ALPHA):
        self.alpha = alpha
        self._sx: float | None = None
        self._sy: float | None = None

    def update(self, x: float, y: float, t: float | None = None) -> tuple[float, float]:
        if self._sx is None:
            self._sx, self._sy = float(x), float(y)
        else:
            self._sx = self.alpha * x + (1 - self.alpha) * self._sx
            self._sy = self.alpha * y + (1 - self.alpha) * self._sy
        return self._sx, self._sy

    def reset(self):
        self._sx = self._sy = None


class OneEuroSmoother:
    def __init__(self, min_cutoff: float = ONE_EURO_MIN_CUTOFF,
                 beta: float = ONE_EURO_BETA,
                 d_cutoff: float = ONE_EURO_D_CUTOFF):
        self.min_cutoff = min_cutoff
        self.beta       = beta
        self.d_cutoff   = d_cutoff
        self.reset()

    @staticmethod
    def _alpha(cutoff: float, dt: float) -> float:
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def update(self, x: float, y: float,
               t: float | None = None) -> tuple[float, float]:
        now = time.monotonic() if t is None else t
        p = np.array([x, y], dtype=float)

        if self._p is None:
            self._p, self._v, self._t = p, np.zeros(2), now
            return float(p[0]), float(p[1])

        dt = max(now - self._t, 1e-3)
        self._t = now

        v_raw   = (p - self._p) / dt
        a_d     = self._alpha(self.d_cutoff, dt)
        self._v = a_d * v_raw + (1 - a_d) * self._v

        speed  = float(np.hypot(*self._v))
        cutoff = self.min_cutoff + self.beta * speed
        a      = self._alpha(cutoff, dt)

        self._p = a * p + (1 - a) * self._p
        return float(self._p[0]), float(self._p[1])

    def reset(self):
        self._p = None
        self._v = None
        self._t = None


class GazeSmoother:
    def __init__(self, kind: str = SMOOTHER):
        self.kind = kind
        if kind == 'fixation':
            self._filt = FixationFilter()
            label = 'filtro de fixação'
        else:
            self._buf  = deque(maxlen=max(1, MEDIAN_WINDOW))
            self._filt = OneEuroSmoother() if kind == 'one_euro' else EMASmoother()
            label = (f'mediana({MEDIAN_WINDOW}) + '
                     f'{"One Euro" if kind == "one_euro" else "EMA"}')
        self._hist: deque = deque()
        print(f'[Smoother] {label}')

    def update(self, x: float, y: float, t: float) -> tuple[float, float]:
        if self.kind == 'fixation':
            out = self._filt.update(x, y, t)
        else:
            self._buf.append((x, y))
            mx, my = np.median(np.array(self._buf), axis=0)
            out = self._filt.update(mx, my, t)
        self._hist.append((t, out[0], out[1]))
        while self._hist and t - self._hist[0][0] > _HISTORY_S:
            self._hist.popleft()
        return out

    def position_at(self, t: float) -> tuple[float, float] | None:
        """Saída do filtro no instante t (a última amostra até t)."""
        best = None
        for ts, x, y in self._hist:
            if ts > t:
                break
            best = (x, y)
        if best is None and self._hist:
            best = self._hist[0][1:]
        return best

    def hold(self):
        if self.kind == 'fixation':
            self._filt.hold()

    def reset(self):
        self._filt.reset()
        self._hist.clear()
        if self.kind != 'fixation':
            self._buf.clear()

    def set_noise(self, sx: float, sy: float):
        if self.kind == 'fixation':
            self._filt.set_noise(sx, sy)
            s = self._filt.sigma
            print(f'[Smoother] ruído inicial: σx={s[0]:.0f} px  σy={s[1]:.0f} px')

    def set_min_cutoff(self, value: float):
        if isinstance(self._filt, OneEuroSmoother):
            self._filt.min_cutoff = value
            print(f'[Smoother] min_cutoff ajustado para {value:.3f} Hz')

    @property
    def fixation_start(self) -> float | None:
        return getattr(self._filt, 'fixation_start', None)

    def debug_text(self) -> str:
        if self.kind == 'fixation':
            s = self._filt.sigma
            return (f'Ruido: {s[0]:.0f}x{s[1]:.0f} px  '
                    f'Sacadas: {self._filt.saccades}')
        return self.kind
