"""
Features de olhar a partir dos 478 landmarks: posição da íris e da pálpebra
no referencial de cada olho, pose da cabeça e abertura dos olhos.
"""

import numpy as np

from config import (LEFT_IRIS_CENTER, RIGHT_IRIS_CENTER,
                    LEFT_EYE_OUTER, LEFT_EYE_INNER, LEFT_EYE_TOP,
                    RIGHT_EYE_INNER, RIGHT_EYE_OUTER, RIGHT_EYE_TOP)

N_LANDMARKS = 478

_L_IRIS = list(range(LEFT_IRIS_CENTER,  LEFT_IRIS_CENTER + 5))
_R_IRIS = list(range(RIGHT_IRIS_CENTER, RIGHT_IRIS_CENTER + 5))

_L_CORNERS = (LEFT_EYE_OUTER, LEFT_EYE_INNER)
_R_CORNERS = (RIGHT_EYE_INNER, RIGHT_EYE_OUTER)

_L_LID = [LEFT_EYE_TOP, 158, 160]
_R_LID = [RIGHT_EYE_TOP, 385, 387]

# EAR de 6 pontos: abertura do olho quando não há blendshapes
_L_EAR = [33, 160, 158, 133, 153, 144]
_R_EAR = [362, 385, 387, 263, 373, 380]

# Pontos rígidos (testa, nariz, cantos dos olhos, maçãs do rosto): pose da cabeça
_RIGID = [10, 109, 338, 151, 67, 297, 168, 6,
          33, 133, 362, 263, 116, 345, 50, 280, 123, 352]

N_EYE  = 6    # lnx, lny, rnx, rny, l_lid, r_lid
N_HEAD = 4    # yaw, pitch, hx, hy


def _eye(P: np.ndarray, iris_ids, corners, lid_ids, ear_ids):
    """(nx, ny, lid, ear, iris_px, center_px) de um olho."""
    a, b   = P[corners[0], :2], P[corners[1], :2]
    axis   = b - a
    width  = float(np.hypot(*axis))
    center = (a + b) / 2
    iris   = P[iris_ids, :2].mean(axis=0)
    if width <= 1:
        return 0.0, 0.0, 0.0, 0.3, iris, center

    ex = axis / width
    if ex[0] < 0:
        ex = -ex
    ey = np.array([-ex[1], ex[0]])
    half = width / 2

    d   = iris - center
    nx  = float(d @ ex) / half
    ny  = float(d @ ey) / half
    lid = float((P[lid_ids, :2].mean(axis=0) - center) @ ey) / half

    p = P[ear_ids, :2]
    ear = ((np.hypot(*(p[1] - p[5])) + np.hypot(*(p[2] - p[4])))
           / (2 * np.hypot(*(p[0] - p[3])) + 1e-9))
    return nx, ny, lid, float(ear), iris, center


def _head(P: np.ndarray, w: int, h: int):
    """(yaw, pitch, hx, hy): normal do plano dos pontos rígidos + posição."""
    Q = P[_RIGID]
    c = Q.mean(axis=0)
    # Normal do plano = direção de menor variância (último vetor singular)
    _, _, vt = np.linalg.svd(Q - c, full_matrices=False)
    n = vt[2]
    if n[2] > 0:
        n = -n
    yaw   = float(np.arctan2(n[0], -n[2]))
    pitch = float(np.arctan2(n[1], -n[2]))

    eyes = P[[_L_CORNERS[0], _L_CORNERS[1], _R_CORNERS[0], _R_CORNERS[1]], :2]
    hx, hy = eyes.mean(axis=0)
    return yaw, pitch, float(hx / w), float(hy / h)


def compute_features(P: np.ndarray, w: int, h: int,
                     blink: tuple | None = None) -> dict:
    lnx, lny, llid, ear_l, iris_l, c_l = _eye(P, _L_IRIS, _L_CORNERS,
                                              _L_LID, _L_EAR)
    rnx, rny, rlid, ear_r, iris_r, c_r = _eye(P, _R_IRIS, _R_CORNERS,
                                              _R_LID, _R_EAR)
    yaw, pitch, hx, hy = _head(P, w, h)

    if blink is not None:
        openness = (1.0 - blink[0], 1.0 - blink[1])
    else:
        openness = (ear_l, ear_r)

    return {
        'eye':             np.array([lnx, lny, rnx, rny, llid, rlid]),
        'head':            np.array([yaw, pitch, hx, hy]),
        'openness':        openness,
        'ear':             (ear_l + ear_r) / 2,
        'blink':           blink,
        'gaze_vector':     ((lnx + rnx) / 2, (lny + rny) / 2),
        'iris_left_px':    iris_l.astype(int),
        'iris_right_px':   iris_r.astype(int),
        'eye_l_center_px': c_l.astype(int),
        'eye_r_center_px': c_r.astype(int),
    }
