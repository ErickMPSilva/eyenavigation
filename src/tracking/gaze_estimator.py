"""
Detecção do rosto com o MediaPipe FaceLandmarker (modo VIDEO, com
blendshapes) e extração das features de olhar.
"""

import os
import time
import urllib.request

import cv2
import numpy as np
import mediapipe as mp
from mediapipe.tasks import python as _mpt
from mediapipe.tasks.python import vision as _mpv

from tracking.gaze_features import compute_features, N_LANDMARKS

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_MODEL_PATH = os.path.join(_ROOT, 'models', 'face_landmarker.task')
_MODEL_URL  = ('https://storage.googleapis.com/mediapipe-models/'
               'face_landmarker/face_landmarker/float16/1/face_landmarker.task')


def _ensure_model():
    if os.path.exists(_MODEL_PATH):
        return
    print('[GazeEstimator] Baixando modelo (~4 MB)...')
    print(f'  URL: {_MODEL_URL}')
    try:
        urllib.request.urlretrieve(_MODEL_URL, _MODEL_PATH)
        print('[GazeEstimator] Modelo salvo em:', _MODEL_PATH)
    except Exception as e:
        raise RuntimeError(
            f'Falha ao baixar o modelo MediaPipe: {e}\n'
            f'Baixe manualmente de:\n  {_MODEL_URL}\n'
            f'e salve como: {_MODEL_PATH}'
        )


class GazeEstimator:
    def __init__(self):
        _ensure_model()
        opts = _mpv.FaceLandmarkerOptions(
            base_options=_mpt.BaseOptions(model_asset_path=_MODEL_PATH),
            running_mode=_mpv.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5,
            output_face_blendshapes=True,
        )
        self._detector = _mpv.FaceLandmarker.create_from_options(opts)
        self._last_ts  = -1
        self._warned   = False
        print('[GazeEstimator] FaceLandmarker (modo VIDEO + blendshapes)')

    def process(self, frame_bgr: np.ndarray, t: float | None = None) -> dict | None:
        ts = int((time.monotonic() if t is None else t) * 1000)
        if ts <= self._last_ts:
            ts = self._last_ts + 1
        self._last_ts = ts

        h, w = frame_bgr.shape[:2]
        rgb    = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        result = self._detector.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), ts)

        if not result.face_landmarks:
            return None
        lm = result.face_landmarks[0]
        if len(lm) < N_LANDMARKS:
            if not self._warned:
                print(f'[GazeEstimator] AVISO: modelo retornou apenas {len(lm)} '
                      f'landmarks (sem íris). Use o modelo full, não o lite.')
                self._warned = True
            return None

        P = np.array([(p.x * w, p.y * h, p.z * w) for p in lm[:N_LANDMARKS]])

        blink = None
        if result.face_blendshapes:
            bs = {c.category_name: c.score for c in result.face_blendshapes[0]}
            if 'eyeBlinkLeft' in bs and 'eyeBlinkRight' in bs:
                blink = (bs['eyeBlinkLeft'], bs['eyeBlinkRight'])

        return compute_features(P, w, h, blink)

    def draw_debug(self, frame: np.ndarray, feat: dict | None) -> np.ndarray:
        if feat is None:
            cv2.putText(frame, 'Nenhuma face detectada', (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
            return frame

        cv2.circle(frame, tuple(feat['iris_left_px']),  4, (0, 255, 80), -1)
        cv2.circle(frame, tuple(feat['iris_right_px']), 4, (0, 255, 80), -1)
        cv2.circle(frame, tuple(feat['eye_l_center_px']), 2, (255, 100, 0), -1)
        cv2.circle(frame, tuple(feat['eye_r_center_px']), 2, (255, 100, 0), -1)
        return frame

    def close(self):
        if self._detector is not None:
            self._detector.close()
            self._detector = None
