import numpy as np

from tracking.correction import GazeCorrection

SW, SH = 1920, 1080
VAL = [(960, 540), (288, 162), (1632, 162), (1632, 918), (288, 918)]


def distort(t, gain=(0.8, 0.75), off=(40, -60)):
    c = np.array([SW / 2, SH / 2])
    return c + np.array(gain) * (np.array(t, float) - c) + np.array(off)


def _err(corr, points, f):
    return np.mean([np.hypot(*(np.array(corr.apply(*f(p))) - p)) for p in points])


def test_recovers_gain_and_offset():
    c = GazeCorrection(SW, SH)
    for i, t in enumerate(VAL):
        c.add(distort(t), t, t=i, kind='validation')
    c.fit()
    grid = [(x, y) for x in range(200, 1800, 200) for y in range(150, 1000, 150)]
    before = np.mean([np.hypot(*(distort(p) - p)) for p in grid])
    after = _err(c, grid, distort)
    assert before > 100
    assert after < 0.15 * before
    assert c.raw_error() > 100 and c.loo_error() < 40


def test_noise_gives_honest_loo_error():
    rng = np.random.default_rng(0)
    c = GazeCorrection(SW, SH)
    for i, t in enumerate(VAL):
        c.add(distort(t) + rng.normal(0, 25, 2), t, t=i, kind='validation')
    c.fit()
    assert 10 < c.loo_error() < 90


def test_single_click_mostly_shifts():
    c = GazeCorrection(SW, SH)
    c.add((900, 500), (960, 540), t=0)
    c.fit()
    x, y = c.apply(900, 500)
    assert abs(x - 960) < 25 and abs(y - 540) < 25
    # Ganho quase inalterado com uma amostra só
    assert abs(c._params[0] - 1).max() < 0.05


def test_outlier_click_is_ignored():
    c = GazeCorrection(SW, SH)
    for i, t in enumerate(VAL):
        c.add(distort(t), t, t=i, kind='validation')
    c.fit()
    ref = c.apply(*distort((700, 400)))
    c.add(distort((700, 400)), (1500, 100), t=10)     # usuário mudou de alvo
    c.fit()
    now = c.apply(*distort((700, 400)))
    assert np.hypot(*(np.array(now) - ref)) < 30


def test_clicks_fix_local_error():
    # Erro só no canto superior esquerdo (que a afim não captura)
    def local(t):
        p = distort(t)
        if t[0] < 700 and t[1] < 400:
            p = p + np.array([70, 50])
        return p
    c = GazeCorrection(SW, SH)
    for i, t in enumerate(VAL):
        c.add(local(t), t, t=i, kind='validation')
    c.fit()
    corner = [(300, 200), (450, 250), (550, 320), (380, 330)]
    before = _err(c, corner, local)
    for i, t in enumerate(corner * 2):
        c.add(local(t), t, t=10 + i, kind='click')
    c.fit()
    after = _err(c, corner, local)
    far = _err(c, [(1500, 800), (1200, 900)], local)
    assert after < 0.5 * before
    assert far < 40                    # resto da tela não piorou


def test_old_samples_lose_weight():
    c = GazeCorrection(SW, SH)
    c.add((900, 500), (960, 540), t=0)
    c.add((900, 500), (900, 500), t=3600)          # uma hora depois: sem erro
    c.fit()
    x, _ = c.apply(900, 500)
    assert abs(x - 900) < 15
