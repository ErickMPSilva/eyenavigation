import numpy as np
import pytest

pytest.importorskip('cv2')

from config import VALIDATION_MAX_ERROR_PX
from calibration.validation import analyze, validation_points

SW, SH = 1920, 1080
TGT = validation_points(SW, SH)


def _rec(pred_fn, rng, n=45, noise=20.0):
    out = []
    for tgt in TGT:
        px, py = pred_fn(tgt)
        out.append([(i / 30, px + rng.normal(0, noise), py + rng.normal(0, noise), 0.8)
                    for i in range(n)])
    return out


def test_accurate_calibration_passes():
    rng = np.random.default_rng(0)
    res = analyze(TGT, _rec(lambda t: t, rng), SW, SH, now=2.0)
    assert res.passed and res.error < 30
    assert 12 < res.noise_x < 30


def test_systematic_offset_and_gain_are_corrected_and_pass():
    rng = np.random.default_rng(1)
    c = np.array([SW / 2, SH / 2])
    f = lambda t: c + 0.8 * (np.array(t) - c) + (60, -70)
    res = analyze(TGT, _rec(f, rng), SW, SH, now=2.0)
    assert res.raw_error > 120
    assert res.passed and res.error < 40


def test_inconsistent_calibration_fails():
    rng = np.random.default_rng(2)
    bad = {TGT[i]: (rng.uniform(0, SW), rng.uniform(0, SH)) for i in range(5)}
    res = analyze(TGT, _rec(lambda t: bad[t], rng), SW, SH, now=2.0)
    assert not res.passed and res.error > VALIDATION_MAX_ERROR_PX


def test_missing_points_fail():
    rng = np.random.default_rng(3)
    rec = _rec(lambda t: t, rng)
    rec[1] = rec[2] = []                   # dois pontos sem rosto
    res = analyze(TGT, rec, SW, SH, now=2.0)
    assert res.preds[1] is None and not res.passed


def test_blink_frames_are_ignored():
    rng = np.random.default_rng(4)
    rec = _rec(lambda t: t, rng)
    for r in rec:                          # piscadas: abertura baixa, olhar saltado
        for i in range(20, 26):
            t, x, y, _ = r[i]
            r[i] = (t, x, y + 300, 0.1)
    res = analyze(TGT, rec, SW, SH, now=2.0)
    assert res.passed and res.error < 30
