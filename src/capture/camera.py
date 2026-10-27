"""
Captura da webcam em thread própria, entregando sempre o frame mais recente.
"""

import threading
import time

import cv2

from config import CAMERA_MIRROR


class Camera:
    def __init__(self, index: int, width: int, height: int, fps: int,
                 mirror: bool = CAMERA_MIRROR):
        self._cap = cv2.VideoCapture(index)
        # MJPG: muitas webcams só entregam 720p/30fps nesse formato;
        # em YUYV caem para 640×480, deixando o olho com ~30 px na imagem
        self._cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._cap.set(cv2.CAP_PROP_FPS,          fps)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)

        self.width  = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._mirror = mirror

        self._cond    = threading.Condition()
        self._frame   = None
        self._t       = 0.0
        self._seq     = 0
        self._served  = 0
        self._running = self._cap.isOpened()
        self._thread  = threading.Thread(target=self._loop, daemon=True)
        if self._running:
            self._thread.start()

    def is_opened(self) -> bool:
        return self._running

    def _loop(self):
        while self._running:
            ok, frame = self._cap.read()
            t = time.monotonic()
            if not ok:
                time.sleep(0.01)
                continue
            if self._mirror:
                frame = cv2.flip(frame, 1)
            with self._cond:
                self._frame, self._t = frame, t
                self._seq += 1
                self._cond.notify_all()

    def read(self, timeout: float = 1.0):
        with self._cond:
            ok = self._cond.wait_for(
                lambda: self._seq != self._served or not self._running,
                timeout)
            if not ok or self._frame is None or not self._running:
                return None, time.monotonic()
            self._served = self._seq
            return self._frame, self._t

    def release(self):
        self._running = False
        with self._cond:
            self._cond.notify_all()
        if self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._cap.release()
