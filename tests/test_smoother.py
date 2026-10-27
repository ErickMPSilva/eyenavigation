import numpy as np
import pytest

import sim_gaze
from tracking.smoother import FixationFilter, OneEuroSmoother, EMASmoother, GazeSmoother


def _run(filt, t, raw, median=None):
    from collections import deque
    buf = deque(maxlen=median) if median else None
    out = []
    for ti, (x, y) in zip(t, raw):
        if buf is not None:
            buf.append((x, y))
            x, y = np.median(np.array(buf), axis=0)
        out.append(filt.update(x, y, ti))
    return np.array(out)


@pytest.fixture(scope='module')
def path():
    return sim_gaze.scanpath(np.random.default_rng(0))


def test_fixation_filter_beats_low_pass_filters(path, capsys):
    t, raw, truth, sacc = path
    res = {
        'bruto':    sim_gaze.evaluate(raw, t, truth, sacc),
        'fixação':  sim_gaze.evaluate(_run(FixationFilter(), t, raw), t, truth, sacc),
        'one euro': sim_gaze.evaluate(_run(OneEuroSmoother(), t, raw, 7), t, truth, sacc),
        'ema':      sim_gaze.evaluate(_run(EMASmoother(), t, raw, 7), t, truth, sacc),
    }
    with capsys.disabled():
        print()
        for k, v in res.items():
            print(f'  {k:9s} tremor {v["tremor_px"]:5.1f} px | erro {v["erro_px"]:5.1f} px'
                  f' | latência {v["latencia_ms"]:5.0f} ms')
    fx, oe = res['fixação'], res['one euro']
    assert fx['tremor_px'] < 0.6 * oe['tremor_px']
    assert fx['erro_px'] < 1.05 * oe['erro_px']
    assert fx['latencia_ms'] < min(200, oe['latencia_ms'])


def test_isolated_spike_does_not_move_cursor():
    f = FixationFilter(noise=(20, 20))
    t = 0.0
    for _ in range(30):
        t += 1 / 30
        f.update(500, 500, t)
    t += 1 / 30
    x, y = f.update(900, 100, t)            # pico de um frame
    for _ in range(5):
        t += 1 / 30
        x, y = f.update(500, 500, t)
    assert abs(x - 500) < 1 and abs(y - 500) < 1
    assert f.saccades == 0


def test_saccade_moves_cursor_quickly():
    f = FixationFilter(noise=(20, 20))
    t = 0.0
    for _ in range(30):
        t += 1 / 30
        f.update(500, 500, t)
    t_s = t
    while True:
        t += 1 / 30
        x, y = f.update(1200, 700, t)
        if np.hypot(x - 1200, y - 700) < 30:
            break
    assert t - t_s < 0.25
    assert f.saccades == 1


@pytest.mark.parametrize('init', [(8, 8), (140, 140)])
def test_noise_estimate_recovers_from_bad_init(init):
    rng = np.random.default_rng(3)
    t, raw, truth, sacc = sim_gaze.scanpath(rng, n_fix=120, sigma=(30, 45))
    f = FixationFilter(noise=init, noise_min=5, noise_max=200)
    _run(f, t, raw)
    sx, sy = f.sigma
    assert 18 < sx < 60 and 27 < sy < 80


def test_position_at_returns_past_output():
    s = GazeSmoother('fixation')
    t = 0.0
    for _ in range(20):
        t += 1 / 30
        s.update(300, 300, t)
    t_before = t
    for _ in range(20):
        t += 1 / 30
        s.update(1500, 900, t)
    x, y = s.position_at(t_before)
    assert abs(x - 300) < 5 and abs(y - 300) < 5
