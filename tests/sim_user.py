"""
Usuário simulado: gera features de olho e cabeça a partir da geometria
(alvo na tela, posição e rotação da cabeça), com ruído de landmark.

Usado nos testes do modelo de calibração.
"""

import numpy as np

SW, SH   = 1920, 1080
PX_CM    = 38.0          # monitor 24" 1080p
DIST_CM  = 60.0
NECK_CM  = 10.0          # olhos a ~10 cm do eixo de rotação do pescoço


def features(target, yaw=0.0, pitch=0.0, head_x=0.0, head_y=0.0,
             rng=None, noise=0.004):
    """target em px; yaw/pitch em rad; head_x/y em cm (deslocamento)."""
    rng = rng or np.random.default_rng()
    # Posição dos olhos: translação + efeito da rotação em torno do pescoço
    ex_cm = head_x + NECK_CM * np.sin(yaw)
    ey_cm = head_y + NECK_CM * np.sin(pitch)
    tx = (target[0] - SW / 2) / PX_CM
    ty = (target[1] - SH / 2) / PX_CM + 8.0     # câmera 8 cm acima do centro
    gx = np.arctan2(tx - ex_cm, DIST_CM) - yaw    # ângulo do olho na cabeça
    gy = np.arctan2(ty - ey_cm, DIST_CM) - pitch
    n = lambda s=noise: rng.normal(0, s)
    eye = np.array([
        0.55 * np.sin(gx) - 0.02 + n(),
        0.12 * np.sin(gy) + 0.01 * np.sin(gx) ** 2 + n(),
        0.55 * np.sin(gx) + 0.02 + n(),
        0.12 * np.sin(gy) + n(),
        -0.35 + 0.30 * np.sin(gy) + n(),
        -0.34 + 0.30 * np.sin(gy) + n(),
    ])
    head = np.array([yaw + n(0.004), 0.15 + pitch + n(0.004),
                     0.5 + ex_cm * 0.012 + n(0.0003),
                     0.3 + ey_cm * 0.012 + n(0.0003)])
    return eye, head


def calibration(rng, head_phase=True, per_point=36):
    E, H, T, G = [], [], [], []
    xs = np.linspace(0.08, 0.92, 4) * SW
    ys = np.linspace(0.06, 0.94, 4) * SH
    k = 0
    for y in ys:
        for x in xs:
            # Cabeça quase parada, com pequena deriva involuntária
            yaw, pitch = rng.normal(0, 0.008, 2)
            hx, hy = rng.normal(0, 0.3, 2)
            for _ in range(per_point):
                e, h = features((x, y), yaw, pitch, hx, hy, rng)
                E.append(e); H.append(h); T.append((x, y)); G.append(k)
            k += 1
    if head_phase:
        c = (SW / 2, SH / 2)
        for step, (dy, dp) in enumerate([(-1, 0), (1, 0), (0, -1), (0, 1)]):
            for i in range(80):
                a = np.sin(np.pi * i / 79)          # vai e volta
                e, h = features(c, 0.2 * dy * a, 0.15 * dp * a,
                                rng.normal(0, 0.3), rng.normal(0, 0.3), rng)
                E.append(e); H.append(h); T.append(c); G.append(100 + step)
    return np.array(E), np.array(H), np.array(T), np.array(G)


def test_set(rng, n=300, head_motion=True):
    out = []
    for _ in range(n):
        tgt = (rng.uniform(0.1, 0.9) * SW, rng.uniform(0.1, 0.9) * SH)
        if head_motion:
            yaw, pitch = rng.uniform(-0.12, 0.12), rng.uniform(-0.08, 0.08)
            hx, hy = rng.uniform(-3, 3), rng.uniform(-2, 2)
        else:
            yaw = pitch = hx = hy = 0.0
        e, h = features(tgt, yaw, pitch, hx, hy, rng)
        out.append((tgt, {'eye': e, 'head': h}))
    return out
