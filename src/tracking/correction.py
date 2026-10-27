"""
Correção da sessão, aplicada após o filtro: ganho e deslocamento por eixo,
correção local e deriva, aprendidos na validação e nos cliques com zoom.
"""

import numpy as np

from config import (CORR_HALF_LIFE_S, CORR_DRIFT_HALF_LIFE_S,
                    CORR_MAX_SAMPLES, CORR_LOCAL_MIN, CORR_LOCAL_SIGMA,
                    CORR_MAX_GAIN_CHANGE)

_PRIOR_GAIN   = 0.1     # força do prior g = 1 (≈ 0,1 amostra na meia tela)
_PRIOR_OFFSET = 0.05    # prior o = 0 (fraco)
_LOCAL_SHRINK = 1.0     # λ do campo local
_DRIFT_SHRINK = 0.5     # λ da deriva: um clique corrige 2/3 do resíduo
_MIN_WEIGHT   = 0.1
_OUTLIER_PX   = 120.0


class GazeCorrection:
    def __init__(self, screen_w: int, screen_h: int):
        self.c = np.array([screen_w / 2, screen_h / 2], float)
        self.half = np.array([screen_w / 2, screen_h / 2], float)
        self.sigma = CORR_LOCAL_SIGMA * screen_w
        self.clear()

    def clear(self):
        self._pred: list = []
        self._true: list = []
        self._w0:   list = []
        self._t:    list = []
        self._kind: list = []
        self._params = (np.ones(2), np.zeros(2), None, np.zeros(2))

    def add(self, pred, true, t: float, kind: str = 'click', weight: float = 1.0):
        self._pred.append(np.asarray(pred, float))
        self._true.append(np.asarray(true, float))
        self._w0.append(float(weight))
        self._t.append(float(t))
        self._kind.append(kind)
        if len(self._pred) > CORR_MAX_SAMPLES:
            idx = next((i for i, k in enumerate(self._kind) if k == 'click'), 0)
            for lst in (self._pred, self._true, self._w0, self._t, self._kind):
                lst.pop(idx)

    @property
    def n(self) -> int:
        return len(self._pred)

    def count(self, kind: str) -> int:
        return sum(k == kind for k in self._kind)

    def fit(self, now: float | None = None):
        if not self._pred:
            self._params = (np.ones(2), np.zeros(2), None, np.zeros(2))
            return
        self._params = self._fit(np.arange(self.n), now)

    def apply(self, x: float, y: float) -> tuple[float, float]:
        q = self._apply(self._params, np.array([x, y], float))
        return float(q[0]), float(q[1])

    def loo_error(self, kind: str = 'validation') -> float | None:
        idx = [i for i, k in enumerate(self._kind) if k == kind]
        if len(idx) < 3:
            return None
        errs = []
        for i in idx:
            params = self._fit(np.delete(np.arange(self.n), i), None)
            q = self._apply(params, self._pred[i])
            errs.append(float(np.hypot(*(q - self._true[i]))))
        return float(np.mean(errs))

    def raw_error(self, kind: str = 'validation') -> float | None:
        idx = [i for i, k in enumerate(self._kind) if k == kind]
        if not idx:
            return None
        return float(np.mean([np.hypot(*(self._pred[i] - self._true[i]))
                              for i in idx]))

    def describe(self) -> str:
        g, o, _, d = self._params
        txt = (f'ganho x{g[0]:.2f} / y{g[1]:.2f}  '
               f'deslocamento ({o[0]:+.0f}, {o[1]:+.0f}) px')
        if np.any(d):
            txt += f'  deriva ({d[0]:+.0f}, {d[1]:+.0f}) px'
        return txt

    def _fit(self, idx: np.ndarray, now):
        P = np.array(self._pred)[idx]
        T = np.array(self._true)[idx]
        t = np.array(self._t)[idx]
        click = np.array([self._kind[i] == 'click' for i in idx])
        now = t.max() if now is None else now
        age = now - t
        w = np.array(self._w0)[idx] * np.maximum(
            0.5 ** (age / CORR_HALF_LIFE_S), _MIN_WEIGHT)

        # 1. Afim (robusto: um clique em que o usuário mudou de alvo não
        #    deve puxar a correção)
        gain, off = self._fit_affine(P, T, w)
        r = np.hypot(*(self._affine(gain, off, P) - T).T)
        bad = r > max(3 * np.median(r), _OUTLIER_PX)
        if bad.any() and (~bad).sum() >= 2:
            w = np.where(bad, 0.0, w)
            gain, off = self._fit_affine(P, T, w)

        loc = None
        if len(P) >= CORR_LOCAL_MIN:
            loc = (P, T - self._affine(gain, off, P), w)

        drift = np.zeros(2)
        if click.any():
            base = (gain, off, loc, np.zeros(2))
            R = np.array([T[i] - self._apply(base, P[i]) for i in range(len(P))])
            wd = np.where(click & (w > 0), 0.5 ** (age / CORR_DRIFT_HALF_LIFE_S), 0)
            drift = (wd[:, None] * R).sum(axis=0) / (wd.sum() + _DRIFT_SHRINK)
        return gain, off, loc, drift

    def _fit_affine(self, P, T, w):
        gain, off = np.ones(2), np.zeros(2)
        for a in range(2):
            A = np.column_stack([P[:, a] - self.c[a], np.ones(len(P))])
            e = T[:, a] - P[:, a]
            reg = np.diag([_PRIOR_GAIN * self.half[a] ** 2, _PRIOR_OFFSET])
            d, o = np.linalg.solve(A.T @ (w[:, None] * A) + reg, A.T @ (w * e))
            gain[a] = 1 + np.clip(d, -CORR_MAX_GAIN_CHANGE, CORR_MAX_GAIN_CHANGE)
            off[a] = o
        return gain, off

    def _affine(self, gain, off, P: np.ndarray) -> np.ndarray:
        return self.c + gain * (P - self.c) + off

    def _apply(self, params, p: np.ndarray) -> np.ndarray:
        gain, off, loc, drift = params
        q = self._affine(gain, off, p)
        if loc is not None:
            Pl, R, w = loc
            k = w * np.exp(-((Pl - p) ** 2).sum(axis=1) / (2 * self.sigma ** 2))
            q = q + (k[:, None] * R).sum(axis=0) / (k.sum() + _LOCAL_SHRINK)
        return q + drift
