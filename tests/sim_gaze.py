"""Sinal de olhar sintético: fixações, sacadas e ruído de webcam."""

import numpy as np

FPS = 30.0


def scanpath(rng, n_fix=60, small_frac=0.3, sigma=(30, 45), rho=0.6,
             spike_p=0.01, sw=1920, sh=1080):
    """
    Returns t, raw (n, 2), truth (n, 2), saccade_times.

    Ruído AR(1) (landmarks do MediaPipe têm ruído correlado no tempo)
    + picos isolados ocasionais.
    """
    t, raw, truth, sacc = [], [], [], []
    pos = np.array([sw / 2, sh / 2])
    noise = np.zeros(2)
    s = np.array(sigma, float)
    k = 0
    for i in range(n_fix):
        if i:
            if rng.random() < small_frac:      # sacada pequena (link vizinho)
                ang = rng.uniform(0, 2 * np.pi)
                step = rng.uniform(80, 160) * np.array([np.cos(ang), np.sin(ang)])
                pos = np.clip(pos + step, 50, [sw - 50, sh - 50])
            else:
                pos = np.array([rng.uniform(50, sw - 50), rng.uniform(50, sh - 50)])
            sacc.append(k / FPS)
        for _ in range(int(rng.uniform(0.4, 1.5) * FPS)):
            noise = rho * noise + np.sqrt(1 - rho ** 2) * rng.normal(0, s)
            p = pos + noise
            if rng.random() < spike_p:
                p = p + rng.normal(0, 200, 2)
            t.append(k / FPS); raw.append(p); truth.append(pos.copy())
            k += 1
    return np.array(t), np.array(raw), np.array(truth), np.array(sacc)


def evaluate(out, t, truth, sacc, settle=0.35):
    """Tremor (px) nas fixações já assentadas e latência (s) das sacadas."""
    since = np.array([ti - sacc[sacc <= ti].max() if (sacc <= ti).any() else 9
                      for ti in t])
    settled = since > settle
    err = out - truth
    # Tremor: variação da saída em torno da sua própria média por fixação
    jit = []
    fix_id = np.searchsorted(sacc, t, side='right')
    for f in np.unique(fix_id):
        m = (fix_id == f) & settled
        if m.sum() > 5:
            jit.append(np.sqrt(((out[m] - out[m].mean(0)) ** 2).sum(1).mean()))
    lat = []
    for s0 in sacc:
        idx = np.where(t >= s0)[0]
        if not len(idx):
            continue
        tgt = truth[idx[0]]
        start_err = np.hypot(*(out[idx[0] - 1] - tgt)) if idx[0] else 0
        if start_err < 150:
            continue
        ok = idx[np.hypot(*(out[idx] - tgt).T) < 0.25 * start_err]
        if len(ok):
            lat.append(t[ok[0]] - s0)
    return {'tremor_px': float(np.mean(jit)),
            'erro_px': float(np.hypot(*err[settled].T).mean()),
            'latencia_ms': 1000 * float(np.median(lat))}
