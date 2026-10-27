"""
Clique de precisão: a região do olhar é ampliada em tela cheia e a segunda
piscada clica no ponto real correspondente.
"""

import cv2
import numpy as np

from config import ZOOM_FACTOR, ZOOM_TIMEOUT_S

_BORDER = (0, 200, 255)


def _mss_grabber(origin, sw, sh):
    try:
        import mss
        sct = mss.mss()
    except Exception as e:
        print(f'[Zoom] Captura de tela indisponível ({e}) — clique com zoom '
              f'desativado. Instale com: pip install mss')
        return None
    region = {'left': origin[0], 'top': origin[1], 'width': sw, 'height': sh}

    def grab() -> np.ndarray:
        return cv2.cvtColor(np.asarray(sct.grab(region)), cv2.COLOR_BGRA2BGR)
    return grab


class ZoomView:
    WIN = 'EyeNav - Zoom'

    def __init__(self, sw: int, sh: int, origin: tuple = (0, 0),
                 factor: float = ZOOM_FACTOR, grab=None):
        self.sw, self.sh = sw, sh
        self.origin = origin
        self.factor = factor
        self.grab = grab if grab is not None else _mss_grabber(origin, sw, sh)
        self.active = False
        self.anchor_raw = None
        self._x0 = self._y0 = 0.0
        self._t_open = 0.0

    @property
    def available(self) -> bool:
        return self.grab is not None

    def open(self, cx: float, cy: float, t: float) -> bool:
        try:
            shot = self.grab()
        except Exception as e:
            print(f'[Zoom] Falha ao capturar a tela ({e}) — zoom desativado.')
            self.grab = None
            return False
        w, h = self.sw / self.factor, self.sh / self.factor
        self._x0 = float(np.clip(cx - w / 2, 0, self.sw - w))
        self._y0 = float(np.clip(cy - h / 2, 0, self.sh - h))
        x0, y0 = int(round(self._x0)), int(round(self._y0))
        crop = shot[y0:y0 + int(round(h)), x0:x0 + int(round(w))]
        view = cv2.resize(crop, (self.sw, self.sh), interpolation=cv2.INTER_CUBIC)
        cv2.rectangle(view, (0, 0), (self.sw - 1, self.sh - 1), _BORDER, 6)
        cv2.putText(view, 'ZOOM: olhe o alvo e pisque devagar  |  '
                          'feche os olhos ate o bipe grave para cancelar',
                    (20, self.sh - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                    _BORDER, 2, cv2.LINE_AA)

        cv2.namedWindow(self.WIN, cv2.WINDOW_NORMAL)
        cv2.moveWindow(self.WIN, *self.origin)
        cv2.setWindowProperty(self.WIN, cv2.WND_PROP_FULLSCREEN,
                              cv2.WINDOW_FULLSCREEN)
        cv2.imshow(self.WIN, view)
        cv2.waitKey(1)
        self.active = True
        self._t_open = t
        return True

    def to_screen(self, gx: float, gy: float) -> tuple[int, int]:
        """Olhar sobre a imagem ampliada → ponto real da tela."""
        return (int(round(self._x0 + gx / self.factor)),
                int(round(self._y0 + gy / self.factor)))

    def from_screen(self, x: float, y: float) -> tuple[float, float]:
        """Ponto real da tela → onde ele aparece na imagem ampliada."""
        return (x - self._x0) * self.factor, (y - self._y0) * self.factor

    def expired(self, t: float) -> bool:
        return self.active and t - self._t_open > ZOOM_TIMEOUT_S

    def close(self):
        if not self.active:
            return
        cv2.destroyWindow(self.WIN)
        # Processa os eventos da janela: ela precisa sumir ANTES de o
        # clique ser enviado, senão o clique cai nela e não na página
        for _ in range(6):
            cv2.waitKey(10)
        self.active = False
