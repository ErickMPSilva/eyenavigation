"""
Validação da calibração em 5 pontos: mede o erro real, ajusta a correção
da sessão e decide se é preciso recalibrar.
"""

import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

from config import (VALIDATION_PULSE_MS, VALIDATION_CAPTURE_MS,
                    VALIDATION_TIMEOUT_MS, VALIDATION_MAX_ERROR_PX,
                    VALIDATION_RESULT_MS, ONE_EURO_TARGET_JITTER_PX,
                    ONE_EURO_MIN_CUTOFF_FLOOR, MEDIAN_WINDOW, SMOOTHER)
from tracking.correction import GazeCorrection
from tracking.smoother import OneEuroSmoother

_GREEN  = (0, 255, 0)
_RED    = (0, 0, 255)
_ORANGE = (0, 165, 255)
_WHITE  = (255, 255, 255)
_LIGHT  = (200, 200, 200)
_GRAY   = (90, 90, 90)
_WARMUP      = 5          # primeiras amostras descartadas (olho assentando)
_OPEN_RATIO  = 0.75       # abertura mínima relativa (sem piscada)
_MIN_SAMPLES = 12
_MIN_POINTS  = 4
_CUTOFFS = np.geomspace(ONE_EURO_MIN_CUTOFF_FLOOR, 3.0, 30)   # candidatos (Hz)


def validation_points(sw: int, sh: int) -> list[tuple[int, int]]:
    return [(int(sw * fx), int(sh * fy)) for fx, fy in
            ((0.5, 0.5), (0.15, 0.15), (0.85, 0.15), (0.85, 0.85), (0.15, 0.85))]


@dataclass
class ValidationResult:
    targets:    list
    preds:      list
    raw_error:  float
    error:      float
    noise_x:    float
    noise_y:    float
    correction: GazeCorrection
    min_cutoff: float | None
    samples:    int

    @property
    def passed(self) -> bool:
        valid = sum(p is not None for p in self.preds)
        return valid >= _MIN_POINTS and self.error <= VALIDATION_MAX_ERROR_PX


def analyze(targets, recordings, sw: int, sh: int, now: float) -> ValidationResult:
    preds, seqs, stds = [], [], []
    for rec in recordings:
        if len(rec) < _WARMUP + _MIN_SAMPLES:
            preds.append(None)
            continue
        arr = np.array(rec[_WARMUP:], float)
        arr = arr[arr[:, 3] >= _OPEN_RATIO * np.median(arr[:, 3])]
        if len(arr) < _MIN_SAMPLES:
            preds.append(None)
            continue
        preds.append(tuple(np.median(arr[:, 1:3], axis=0)))
        stds.append(arr[:, 1:3].std(axis=0))
        seqs.append(arr[:, :3])

    corr = GazeCorrection(sw, sh)
    for tgt, p in zip(targets, preds):
        if p is not None:
            corr.add(p, tgt, now, kind='validation')
    corr.fit(now)

    raw = corr.raw_error()
    loo = corr.loo_error()
    if loo is None:
        loo = raw if raw is not None else float('inf')
    noise = np.mean(stds, axis=0) if stds else np.array([np.nan, np.nan])

    cutoff = None
    if SMOOTHER == 'one_euro' and seqs:
        cutoff = float(_CUTOFFS[0])
        for cut in _CUTOFFS:
            if _tremor(seqs, cut) <= ONE_EURO_TARGET_JITTER_PX:
                cutoff = float(cut)

    return ValidationResult(list(targets), preds,
                            float('inf') if raw is None else raw, float(loo),
                            float(noise[0]), float(noise[1]), corr, cutoff,
                            int(sum(len(s) for s in seqs)))


def _tremor(seqs, min_cutoff: float) -> float:
    vals = []
    for arr in seqs:
        filt = OneEuroSmoother(min_cutoff=min_cutoff)
        buf  = deque(maxlen=max(1, MEDIAN_WINDOW))
        out  = []
        for t, x, y in arr:
            buf.append((x, y))
            mx, my = np.median(np.array(buf), axis=0)
            out.append(filt.update(mx, my, t=t))
        vals.append(np.linalg.norm(np.array(out[_WARMUP:]).std(axis=0)))
    return float(np.mean(vals))


class ValidationScreen:
    WIN = 'EyeNav - Validacao'

    def __init__(self, sw: int, sh: int, origin: tuple = (0, 0)):
        self.sw, self.sh = sw, sh
        self.origin = origin
        self.points = validation_points(sw, sh)

    def run(self, model, estimator, cam,
            will_retry: bool = False) -> ValidationResult | None:
        cv2.namedWindow(self.WIN, cv2.WINDOW_NORMAL)
        cv2.moveWindow(self.WIN, *self.origin)
        cv2.setWindowProperty(self.WIN, cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        try:
            recordings = []
            now = 0.0
            for idx, pt in enumerate(self.points):
                if not self._pulse(pt, idx):
                    return None
                rec = self._capture(model, estimator, cam, pt, idx)
                if rec is None:
                    return None
                recordings.append(rec)
                if rec:
                    now = rec[-1][0]
            res = analyze(self.points, recordings, self.sw, self.sh, now)
            self._report(res, will_retry)
            return res
        finally:
            cv2.destroyWindow(self.WIN)

    def _pulse(self, pt, idx) -> bool:
        t0 = time.monotonic()
        while (e := time.monotonic() - t0) * 1000 < VALIDATION_PULSE_MS:
            canvas = self._blank()
            cv2.circle(canvas, pt, 15 + int(15 * abs(np.sin(2 * np.pi * e))),
                       _GREEN, -1)
            self._hud(canvas, idx)
            cv2.imshow(self.WIN, canvas)
            if cv2.waitKey(15) & 0xFF == 27:
                return False
        return True

    def _capture(self, model, estimator, cam, pt, idx):
        rec = []
        t_start = t_last = None
        t_face = 0.0
        while t_face * 1000 < VALIDATION_CAPTURE_MS:
            frame, now = cam.read()
            if t_start is None:
                t_start = t_last = now
            dt, t_last = now - t_last, now
            if (now - t_start) * 1000 > VALIDATION_TIMEOUT_MS:
                print(f'[Validação] Ponto {idx + 1}: rosto ou olho aberto '
                      f'não detectado a tempo.')
                break
            if frame is None:
                continue

            feat = estimator.process(frame, now)
            if feat is not None:
                px, py = model.predict(feat)
                rec.append((now, px, py, float(np.mean(feat['openness']))))
                t_face += dt

            canvas = self._blank()
            frac = min(t_face * 1000 / VALIDATION_CAPTURE_MS, 1.0)
            cv2.circle(canvas, pt, 18, _GREEN if feat is not None else _RED, -1)
            cv2.ellipse(canvas, pt, (40, 40), 0, -90, -90 + 360 * (1 - frac),
                        _WHITE, 4)
            if feat is None:
                self._text(canvas, 'Rosto nao detectado', self.sh // 2 - 80, _RED)
            self._hud(canvas, idx)
            cv2.imshow(self.WIN, canvas)
            if cv2.waitKey(1) & 0xFF == 27:
                return None
        return rec

    def _report(self, res: ValidationResult, will_retry: bool):
        canvas = self._blank()
        for i, (tgt, p) in enumerate(zip(res.targets, res.preds)):
            cv2.circle(canvas, tgt, 22, _WHITE, 2)
            if p is None:
                cv2.putText(canvas, 'sem dados', (tgt[0] - 45, tgt[1] + 50),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, _RED, 1)
                continue
            raw = (int(p[0]), int(p[1]))
            fixed = tuple(int(v) for v in res.correction.apply(*p))
            cv2.line(canvas, tgt, raw, _GRAY, 1)
            cv2.circle(canvas, raw, 6, _RED, -1)
            cv2.line(canvas, tgt, fixed, _GREEN, 2)
            cv2.circle(canvas, fixed, 7, _GREEN, -1)

        if res.passed:
            status, color = 'Precisao OK', _GREEN
        elif will_retry:
            status, color = 'Precisao insuficiente - recalibrando', _RED
        else:
            status, color = 'Precisao insuficiente - seguindo com a melhor calibracao', _ORANGE
        y = self.sh // 2 - 40
        self._text(canvas, status, y, color, 1.2)
        self._text(canvas, f'Erro medio: {res.error:.0f} px   '
                           f'(sem correcao: {res.raw_error:.0f} px)', y + 50)
        self._text(canvas, 'vermelho = olhar estimado   verde = apos a correcao',
                   y + 95, _GRAY, 0.6)
        cv2.imshow(self.WIN, canvas)
        cv2.waitKey(VALIDATION_RESULT_MS)

        valid = [p for p in res.preds if p is not None]
        print(f'[Validação] {len(valid)}/{len(res.preds)} pontos | erro médio '
              f'{res.error:.0f} px após a correção (sem correção '
              f'{res.raw_error:.0f} px) | ruído σx={res.noise_x:.0f} '
              f'σy={res.noise_y:.0f} px | {res.correction.describe()}')
        for i, (tgt, p) in enumerate(zip(res.targets, res.preds)):
            if p is None:
                print(f'[Validação]   ponto {i + 1} {tgt}: sem dados')
            else:
                print(f'[Validação]   ponto {i + 1} {tgt}: estimado '
                      f'({p[0]:.0f}, {p[1]:.0f}) → erro '
                      f'{np.hypot(p[0] - tgt[0], p[1] - tgt[1]):.0f} px')

    def _blank(self):
        return np.zeros((self.sh, self.sw, 3), dtype=np.uint8)

    def _text(self, canvas, txt, y, color=_LIGHT, scale=0.8):
        size, _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
        cv2.putText(canvas, txt, ((self.sw - size[0]) // 2, y),
                    cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)

    def _hud(self, canvas, idx):
        cv2.putText(canvas, f'Validacao {idx + 1}/{len(self.points)}',
                    (20, self.sh - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, _GRAY, 1)
        cv2.putText(canvas, 'ESC = pular', (self.sw - 130, self.sh - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, _GRAY, 1)
