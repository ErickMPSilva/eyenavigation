"""
Gravação da sessão em .npz (tecla G), para diagnóstico.
"""

import time

import numpy as np

_STATES = {'aberto': 0, 'fechando': 1, 'fechado': 2}


class SessionRecorder:
    def __init__(self):
        self.active = False
        self._rows: list = []
        self._meta: dict = {}

    def start(self, meta: dict):
        self._rows = []
        self._meta = dict(meta)
        self._meta['inicio'] = time.strftime('%Y-%m-%d %H:%M:%S')
        self.active = True
        print('  [G] Gravação da sessão INICIADA (G de novo para salvar).')

    def add(self, t, feat, raw, gaze, eye_state: str, blocked: bool):
        if not self.active:
            return
        nan2 = (np.nan, np.nan)
        eye  = feat['eye']  if feat is not None else np.full(6, np.nan)
        head = feat['head'] if feat is not None else np.full(4, np.nan)
        op   = feat['openness'] if feat is not None else nan2
        self._rows.append(np.r_[t, eye, head, op, raw if raw else nan2,
                                gaze, _STATES.get(eye_state, -1), float(blocked)])

    def event(self, t, kind: str, **data):
        if self.active:
            self._meta.setdefault('eventos', []).append({'t': t, 'tipo': kind, **data})

    def stop(self) -> str | None:
        if not self.active:
            return None
        self.active = False
        if not self._rows:
            return None
        A = np.array(self._rows)
        path = time.strftime('eyenav_record_%Y%m%d_%H%M%S.npz')
        np.savez_compressed(path, t=A[:, 0], eye=A[:, 1:7], head=A[:, 7:11],
                            openness=A[:, 11:13], raw=A[:, 13:15],
                            gaze=A[:, 15:17], state=A[:, 17], blocked=A[:, 18],
                            meta=np.array(self._meta, dtype=object))
        print(f'  [G] Gravação salva → {path}  ({len(A)} frames, '
              f'{A[-1, 0] - A[0, 0]:.0f} s)')
        return path
