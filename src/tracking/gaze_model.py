"""
Modelo de calibração: Ridge sobre o polinômio de grau 2 das features dos
olhos mais termos lineares da cabeça, escolhido por validação cruzada
agrupada (um ponto da grade de fora por vez).
"""

import pickle

import numpy as np

from config import CALIB_FILE, FEATURE_VERSION, CALIB_RIDGE_ALPHAS

_HEAD_SCALE_FLOOR = np.array([0.03, 0.03, 0.01, 0.01])   # yaw, pitch (rad), hx, hy
_MIN_GROUPS_CV    = 4


def _eye_mean(E: np.ndarray) -> np.ndarray:
    return np.column_stack([(E[:, 0] + E[:, 2]) / 2,
                            (E[:, 1] + E[:, 3]) / 2,
                            (E[:, 4] + E[:, 5]) / 2])


def _poly2(Z: np.ndarray) -> np.ndarray:
    i, j = np.triu_indices(Z.shape[1])
    return np.hstack([Z, Z[:, i] * Z[:, j]])


def _ridge(A: np.ndarray, Y: np.ndarray, alpha: float):
    mu_a, mu_y = A.mean(axis=0), Y.mean(axis=0)
    Ac, Yc = A - mu_a, Y - mu_y
    W = np.linalg.solve(Ac.T @ Ac + alpha * np.eye(A.shape[1]), Ac.T @ Yc)
    return W, mu_y - mu_a @ W


def _robust_ridge(A: np.ndarray, Y: np.ndarray, alpha: float):
    """Ajusta, descarta resíduos atípicos (> mediana + 3·MAD) e reajusta."""
    W, b = _ridge(A, Y, alpha)
    r = np.hypot(*(A @ W + b - Y).T)
    med = np.median(r)
    keep = r <= med + 3 * 1.4826 * np.median(np.abs(r - med)) + 1e-6
    if keep.sum() >= max(10, A.shape[1] + 1) and not keep.all():
        W, b = _ridge(A[keep], Y[keep], alpha)
    return W, b


class GazeModel:
    def __init__(self):
        self.is_trained    = False
        self.cv_error_px   = None
        self.eye_baselines = None
        self.data          = None
        self._p: dict | None = None

    def train(self, eye, head, targets, groups,
              alphas=CALIB_RIDGE_ALPHAS, eye_baselines=None):
        E = np.asarray(eye,     dtype=float)
        H = np.asarray(head,    dtype=float)
        Y = np.asarray(targets, dtype=float)
        g = np.asarray(groups)
        if len(E) < 30 or len(np.unique(g)) < 6:
            raise ValueError('Dados insuficientes: são necessários ao menos '
                             '6 pontos de calibração válidos.')

        Em = _eye_mean(E)
        norm = {
            'e_mu': E.mean(axis=0),  'e_sd': E.std(axis=0) + 1e-9,
            'm_mu': Em.mean(axis=0), 'm_sd': Em.std(axis=0) + 1e-9,
            'h_mu': H.mean(axis=0),  'h_sd': np.maximum(H.std(axis=0),
                                                        _HEAD_SCALE_FLOOR),
        }

        results = []
        for eyes in ('both', 'mean'):
            for use_head in (True, False):
                A = self._design(E, H, norm, eyes, use_head)
                for alpha in alphas:
                    results.append((self._cv_error(A, Y, g, alpha),
                                    eyes, use_head, alpha))
        results.sort(key=lambda r: r[0])
        cv_err, eyes, use_head, alpha = results[0]

        A = self._design(E, H, norm, eyes, use_head)
        W, b = _robust_ridge(A, Y, alpha)
        self._p = {**norm, 'eyes': eyes, 'use_head': use_head,
                   'alpha': alpha, 'W': W, 'b': b}
        self.is_trained    = True
        self.cv_error_px   = float(cv_err)
        self.eye_baselines = eye_baselines
        self.data = {'eye': E, 'head': H, 'targets': Y, 'groups': g}

        pred = A @ W + b
        erros = np.hypot(*(pred - Y).T)
        print(f'[GazeModel] Modelo escolhido: olhos={eyes} | '
              f'cabeça={"sim" if use_head else "não"} | alpha={alpha:g}')
        no_head = min(r[0] for r in results if not r[2])
        with_head = min(r[0] for r in results if r[2])
        print(f'[GazeModel] Erro na validação cruzada: {cv_err:.0f} px  '
              f'(com cabeça {with_head:.0f} px | sem {no_head:.0f} px)')
        print(f'[GazeModel] Erro nos próprios pontos: média {erros.mean():.0f} px '
              f'| máx {erros.max():.0f} px')
        print(f'[GazeModel] Faixa da íris (olho esq.): '
              f'x [{E[:, 0].min():+.3f}, {E[:, 0].max():+.3f}]  '
              f'y [{E[:, 1].min():+.3f}, {E[:, 1].max():+.3f}]  '
              f'| pálpebra [{E[:, 4].min():+.3f}, {E[:, 4].max():+.3f}]')
        print(f'[GazeModel] Variação da cabeça: '
              f'yaw ±{np.degrees(H[:, 0].std()):.1f}°  '
              f'pitch ±{np.degrees(H[:, 1].std()):.1f}°')
        print(f'[GazeModel] Faixa prevista na tela: '
              f'x [{pred[:, 0].min():.0f}, {pred[:, 0].max():.0f}]  '
              f'y [{pred[:, 1].min():.0f}, {pred[:, 1].max():.0f}]')

    def predict(self, feat: dict) -> tuple[float, float]:
        if not self.is_trained:
            raise RuntimeError('Modelo não treinado. Execute a calibração.')
        p = self._p
        A = self._design(feat['eye'][None, :], feat['head'][None, :],
                         p, p['eyes'], p['use_head'])
        x, y = (A @ p['W'] + p['b'])[0]
        return float(x), float(y)

    def save(self, path: str = CALIB_FILE):
        data = {
            'version':       FEATURE_VERSION,
            'params':        self._p,
            'cv_error_px':   self.cv_error_px,
            'eye_baselines': self.eye_baselines,
            'data':          self.data,
        }
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        print(f'[GazeModel] Calibração salva → {path}')

    def load(self, path: str = CALIB_FILE) -> bool:
        try:
            with open(path, 'rb') as f:
                data = pickle.load(f)
        except FileNotFoundError:
            return False
        except Exception as e:
            print(f'[GazeModel] Calibração salva ilegível ({e}) — recalibre.')
            return False
        if not isinstance(data, dict) or data.get('version') != FEATURE_VERSION:
            print('[GazeModel] Calibração salva usa features antigas — '
                  'será necessário recalibrar.')
            return False
        self._p            = data['params']
        self.cv_error_px   = data.get('cv_error_px')
        self.eye_baselines = data.get('eye_baselines')
        self.data          = data.get('data')
        self.is_trained    = True
        err = f' (erro estimado {self.cv_error_px:.0f} px)' if self.cv_error_px else ''
        print(f'[GazeModel] Calibração carregada ← {path}{err}')
        return True

    @staticmethod
    def _design(E, H, norm, eyes: str, use_head: bool) -> np.ndarray:
        if eyes == 'mean':
            Z = (_eye_mean(E) - norm['m_mu']) / norm['m_sd']
        else:
            Z = (E - norm['e_mu']) / norm['e_sd']
        A = _poly2(Z)
        if use_head:
            A = np.hstack([A, (H - norm['h_mu']) / norm['h_sd']])
        return A

    @staticmethod
    def _cv_error(A, Y, groups, alpha) -> float:
        ids = np.unique(groups)
        if len(ids) < _MIN_GROUPS_CV:
            W, b = _robust_ridge(A, Y, alpha)
            return float(np.hypot(*(A @ W + b - Y).T).mean())
        errs = []
        for gid in ids:
            test = groups == gid
            W, b = _robust_ridge(A[~test], Y[~test], alpha)
            errs.append(np.hypot(*(A[test] @ W + b - Y[test]).T).mean())
        return float(np.mean(errs))
