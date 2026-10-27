"""
Tela de calibração: grade de pontos e etapa de movimento da cabeça.
"""

import time

import cv2
import numpy as np
from config import (CALIB_ROWS, CALIB_COLS, CALIB_MARGIN_X, CALIB_MARGIN_Y,
                    CALIB_FACE_WAIT_MS, CALIB_PULSE_MS, CALIB_CAPTURE_MS,
                    CALIB_HEAD_MOTION, CALIB_HEAD_STEP_MS, EYE_BANDS)

_GREEN = (0, 255, 0)
_WHITE = (255, 255, 255)
_RED   = (0, 0, 255)
_GRAY  = (90, 90, 90)
_LIGHT = (200, 200, 200)
_MIN_SAMPLES_PER_POINT = 10
_OPEN_RATIO   = 0.75     # abertura mínima (relativa à mediana) de amostra válida
_OUTLIER_Z    = 3.0      # distância robusta máxima das features do olho
_HEAD_GROUP   = 100      # grupos das etapas de cabeça: 100, 101, ...
_HEAD_INTRO_S = 4.0      # instrução antes do movimento da cabeça
_HEAD_STEPS   = [('ESQUERDA', (-1, 0)), ('CENTRO', None),
                 ('DIREITA',  (1, 0)),  ('CENTRO', None),
                 ('CIMA',     (0, -1)), ('CENTRO', None),
                 ('BAIXO',    (0, 1)),  ('CENTRO', None)]


def build_calibration_points(sw: int, sh: int) -> list[tuple[int, int]]:
    mx, my = int(sw * CALIB_MARGIN_X), int(sh * CALIB_MARGIN_Y)
    gw, gh = sw - 2 * mx, sh - 2 * my
    step_x = gw / (CALIB_COLS - 1) if CALIB_COLS > 1 else 0
    step_y = gh / (CALIB_ROWS - 1) if CALIB_ROWS > 1 else 0

    pts = []
    for r in range(CALIB_ROWS):
        cols = range(CALIB_COLS) if r % 2 == 0 else range(CALIB_COLS - 1, -1, -1)
        for c in cols:
            pts.append((mx + int(c * step_x), my + int(r * step_y)))
    return pts


def clean_point_samples(samples: list) -> list:
    if len(samples) < 5:
        return samples
    E = np.array([s[0] for s in samples])
    o = np.array([np.mean(s[2]) for s in samples])
    keep = o >= _OPEN_RATIO * np.median(o)

    med = np.median(E[keep], axis=0)
    mad = np.median(np.abs(E[keep] - med), axis=0) * 1.4826 + 1e-4
    d = np.sqrt((((E - med) / mad) ** 2).mean(axis=1))
    good = keep & (d <= _OUTLIER_Z)
    if good.sum() < len(samples) // 2:      # nunca descarta mais da metade
        order = np.argsort(np.where(keep, d, np.inf))
        good = np.zeros(len(samples), bool)
        good[order[:len(samples) // 2]] = True
    return [s for s, g in zip(samples, good) if g]


def eye_baselines(openness: np.ndarray, ys: np.ndarray, sh: int) -> list:
    bands = np.clip((ys / sh * EYE_BANDS).astype(int), 0, EYE_BANDS - 1)
    overall = np.median(openness, axis=0)
    out = []
    for b in range(EYE_BANDS):
        sel = openness[bands == b]
        out.append([float(v) for v in
                    (np.median(sel, axis=0) if len(sel) >= 10 else overall)])
    return out


def _smoothstep(t: float) -> float:
    return t * t * (3 - 2 * t)


class CalibrationScreen:
    WIN = 'EyeNav - Calibracao'

    def __init__(self, sw: int, sh: int, origin: tuple = (0, 0)):
        self.sw      = sw
        self.sh      = sh
        self.origin  = origin
        self.points  = build_calibration_points(sw, sh)
        self._open_ref: float | None = None

    def run(self, estimator, cam) -> dict | None:
        cv2.namedWindow(self.WIN, cv2.WINDOW_NORMAL)
        cv2.moveWindow(self.WIN, *self.origin)
        cv2.setWindowProperty(self.WIN, cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        try:
            return self._run(estimator, cam)
        finally:
            cv2.destroyWindow(self.WIN)

    def _run(self, estimator, cam) -> dict | None:
        if not self._wait_for_face(estimator, cam):
            return None

        samples, targets, groups = [], [], []
        for idx, pt in enumerate(self.points):
            if not self._pulse(cam, pt, idx):
                return None
            got = self._capture(estimator, cam, pt, idx)
            if got is None:
                return None
            got = clean_point_samples(got)
            if len(got) < _MIN_SAMPLES_PER_POINT:
                print(f'[Calibração] AVISO: ponto {idx + 1} {pt} com apenas '
                      f'{len(got)} amostras (piscadas ou rosto perdido).')
            samples += got
            targets += [pt] * len(got)
            groups  += [idx] * len(got)

        if CALIB_HEAD_MOTION:
            head = self._head_motion(estimator, cam)
            if head is None:
                return None
            center = (self.sw // 2, self.sh // 2)
            for step, got in head:
                samples += got
                targets += [center] * len(got)
                groups  += [_HEAD_GROUP + step] * len(got)

        self._show_message('Calibracao concluida!', (0, 255, 100), 1000)

        if not samples:
            return None
        grid = np.array(groups) < _HEAD_GROUP
        openness = np.array([s[2] for s in samples], dtype=float)
        T = np.array(targets, dtype=float)
        n_head = int((~grid).sum())
        print(f'[Calibração] {int(grid.sum())} amostras em {len(self.points)} '
              f'pontos ({CALIB_ROWS}×{CALIB_COLS}) + {n_head} de movimento '
              f'de cabeça.')
        return {
            'eye':     np.array([s[0] for s in samples]),
            'head':    np.array([s[1] for s in samples]),
            'targets': T,
            'groups':  np.array(groups),
            'eye_baselines': eye_baselines(openness[grid], T[grid, 1], self.sh),
        }

    def _wait_for_face(self, estimator, cam) -> bool:
        t_start = None
        opens: list[float] = []

        while True:
            frame, now = cam.read()
            if frame is None:
                continue
            feat = estimator.process(frame, now)
            canvas = self._blank()

            if feat is not None and self._eye_open(feat, opens):
                if t_start is None:
                    t_start = now
                    opens.clear()
                opens.append(float(np.mean(feat['openness'])))

                t = (now - t_start) * 1000 / CALIB_FACE_WAIT_MS
                if t >= 1.0:
                    self._open_ref = float(np.median(opens))
                    return True
                ang = 360 * (1 - _smoothstep(t))
                cv2.ellipse(canvas, (self.sw // 2, self.sh // 2), (50, 50),
                            0, -90, -90 + ang, _GREEN, -1)
            else:
                t_start = None
                self._center_text(canvas, 'Rosto nao detectado', _RED)

            self._hint(canvas)
            cv2.imshow(self.WIN, canvas)
            if cv2.waitKey(1) & 0xFF == 27:
                return False

    def _pulse(self, cam, pt: tuple, idx: int) -> bool:
        t0 = time.monotonic()
        while (elapsed := time.monotonic() - t0) * 1000 < CALIB_PULSE_MS:
            canvas = self._blank()
            radius = 15 + int(15 * abs(np.sin(2 * np.pi * elapsed)))
            cv2.circle(canvas, pt, radius, _GREEN, -1)
            self._progress(canvas, idx)
            cv2.imshow(self.WIN, canvas)
            if cv2.waitKey(15) & 0xFF == 27:
                return False
        return True

    def _capture(self, estimator, cam, pt: tuple, idx: int) -> list | None:
        samples: list = []
        t0 = time.monotonic()
        while (elapsed := time.monotonic() - t0) * 1000 < CALIB_CAPTURE_MS:
            frame, now = cam.read()
            if frame is None:
                continue

            canvas = self._blank()
            cv2.circle(canvas, pt, 20, _GREEN, -1)
            t   = elapsed * 1000 / CALIB_CAPTURE_MS
            ang = 360 * (1 - _smoothstep(min(t, 1.0)))
            cv2.ellipse(canvas, pt, (40, 40), 0, -90, -90 + ang, _WHITE, 4)
            self._progress(canvas, idx)
            cv2.imshow(self.WIN, canvas)
            if cv2.waitKey(1) & 0xFF == 27:
                return None

            feat = estimator.process(frame, now)
            if feat is not None and self._eye_open(feat):
                samples.append((feat['eye'], feat['head'], feat['openness']))
        return samples

    def _head_motion(self, estimator, cam) -> list | None:
        c = (self.sw // 2, self.sh // 2)

        t0 = time.monotonic()
        while (e := time.monotonic() - t0) < _HEAD_INTRO_S:
            canvas = self._blank()
            cv2.circle(canvas, c, 14, _GREEN, -1)
            self._text(canvas, 'Mantenha os OLHOS no ponto verde', self.sh // 4)
            self._text(canvas, 'e gire a CABECA devagar, seguindo as setas',
                       self.sh // 4 + 45)
            self._text(canvas, f'{int(_HEAD_INTRO_S - e) + 1}', self.sh // 4 + 110, 1.2)
            self._hint(canvas, skip=True)
            cv2.imshow(self.WIN, canvas)
            key = cv2.waitKey(15) & 0xFF
            if key == 27:
                return None
            if key == 32:
                print('[Calibração] Etapa de movimento da cabeça pulada.')
                return []

        per_step: dict[int, list] = {}
        for i, (label, direction) in enumerate(_HEAD_STEPS):
            t0 = time.monotonic()
            while (e := time.monotonic() - t0) * 1000 < CALIB_HEAD_STEP_MS:
                frame, now = cam.read()
                if frame is None:
                    continue
                canvas = self._blank()
                cv2.circle(canvas, c, 14, _GREEN, -1)
                if direction:
                    dx, dy = direction
                    a = (c[0] + dx * 60,  c[1] + dy * 60)
                    b = (c[0] + dx * 200, c[1] + dy * 200)
                    cv2.arrowedLine(canvas, a, b, _LIGHT, 4, tipLength=0.3)
                self._text(canvas, f'Cabeca: {label}', self.sh // 4)
                frac = (i + e * 1000 / CALIB_HEAD_STEP_MS) / len(_HEAD_STEPS)
                cv2.rectangle(canvas, (self.sw // 2 - 150, self.sh - 60),
                              (self.sw // 2 - 150 + int(300 * frac),
                               self.sh - 52), _GREEN, -1)
                self._hint(canvas, skip=True)
                cv2.imshow(self.WIN, canvas)
                key = cv2.waitKey(1) & 0xFF
                if key == 27:
                    return None
                if key == 32:
                    print('[Calibração] Etapa de movimento da cabeça pulada.')
                    return []

                feat = estimator.process(frame, now)
                if feat is not None and self._eye_open(feat):
                    per_step.setdefault(i // 2, []).append(
                        (feat['eye'], feat['head'], feat['openness']))
        return sorted(per_step.items())

    def _eye_open(self, feat: dict, recent: list | None = None) -> bool:
        ref = self._open_ref
        if ref is None:
            if not recent:
                return True
            ref = float(np.median(recent))
        return float(np.mean(feat['openness'])) >= ref * _OPEN_RATIO

    def _blank(self) -> np.ndarray:
        return np.zeros((self.sh, self.sw, 3), dtype=np.uint8)

    def _text(self, canvas, txt, y, scale=1.0, color=_LIGHT):
        size, _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
        cv2.putText(canvas, txt, ((self.sw - size[0]) // 2, y),
                    cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)

    def _center_text(self, canvas, txt, color):
        size, _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 1.5, 3)
        cv2.putText(canvas, txt,
                    ((self.sw - size[0]) // 2, (self.sh + size[1]) // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, 3)

    def _progress(self, canvas, idx: int):
        cv2.putText(canvas, f'{idx + 1}/{len(self.points)}',
                    (20, self.sh - 20), cv2.FONT_HERSHEY_SIMPLEX,
                    0.5, _GRAY, 1)
        self._hint(canvas)

    def _hint(self, canvas, skip: bool = False):
        txt = 'ESPACO = pular   ESC = cancelar' if skip else 'ESC = cancelar'
        size, _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.putText(canvas, txt, (self.sw - size[0] - 20, self.sh - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, _GRAY, 1)

    def _show_message(self, txt, color, ms):
        canvas = self._blank()
        self._center_text(canvas, txt, color)
        cv2.imshow(self.WIN, canvas)
        cv2.waitKey(ms)
