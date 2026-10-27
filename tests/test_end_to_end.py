"""
Testes de ponta a ponta do main(): calibração, validação e loop
principal, com câmera e estimador falsos que simulam um usuário.

O usuário simulado (sim_user) olha para o alvo mostrado na calibração e
na validação e, no loop principal, segue um roteiro: fixações, piscadas
lentas (clique, duplo, direito), piscadas naturais e olhar para a borda
inferior (scroll). Durante o fechamento dos olhos, as features da íris
"saltam" como no MediaPipe real.

Cenários:
  - desvio sistemático (câmera/cabeça) que a validação mede e corrige,
    com a trava do scroll: travado não rola; piscada na alça destrava;
    piscada rolando freia e trava sem clicar;
  - alça alcançável com desvio para a esquerda (olhando além da borda);
  - trava desligada: scroll como antes;
  - calibração ruim → validação reprova → recalibração automática;
  - clique com zoom, com desvio surgindo depois da validação, que os
    próprios cliques corrigem.
"""

import builtins
import time

import numpy as np
import pytest

cv2 = pytest.importorskip('cv2')
pytest.importorskip('mediapipe')

from calibration import calibration
import config
from tracking import correction as correction_mod
from desktop import gaze_overlay
import main
from interaction import scroll_lock as scroll_lock_mod
from desktop import mouse_backend
import sim_user
from calibration import validation
from interaction import zoom as zoom_mod

FPS = 30.0
DRIFT = np.array([0.03, 0.0, 0.03, 0.0, 0.0, 0.0])   # ≈ 120 px na horizontal

# Roteiro: (início s, fim s, alvo, olhos fechados)
DIRECT = [
    (0.0,  2.5,  (400, 300),   False),
    (2.5,  3.3,  (400, 300),   True),     # 0,8 s → clique
    (3.3,  6.0,  (1500, 800),  False),
    (6.0,  7.6,  (1500, 800),  True),     # 1,6 s → duplo clique
    (7.6,  9.0,  (900, 500),   False),
    (9.0,  9.2,  (900, 500),   True),     # piscada natural → nada
    (9.2,  10.5, (900, 500),   False),
    (10.5, 10.7, (900, 500),   True),     # piscada natural → nada
    (10.7, 11.5, (900, 500),   False),
    (11.5, 13.5, (960, 1075),  False),    # borda inferior TRAVADO → nada
    (13.5, 14.8, (1915, 540),  False),    # olha a alça: acende
    (14.8, 15.6, (1915, 540),  True),     # piscada lenta na alça → DESTRAVA
    (15.6, 18.1, (960, 1075),  False),    # borda inferior → rola
    (18.1, 18.9, (960, 1075),  True),     # piscada rolando → FREIO (sem clique)
    (18.9, 20.4, (960, 1075),  False),    # travado de novo: não rola
    (20.4, 22.0, (700, 600),   False),
    (22.0, 24.5, (700, 600),   True),     # 2,5 s → clique direito
    (24.5, 26.0, (700, 600),   False),
]

# Desvio para a esquerda: olhar além da borda direita ainda acende a alça
HANDLE_DRIFT = [
    (0.0,  1.5,  (900, 500),   False),
    (1.5,  3.0,  (2100, 540),  False),
    (3.0,  3.8,  (2100, 540),  True),     # piscada → destrava
    (3.8,  6.0,  (960, 1075),  False),    # rola
    (6.0,  7.0,  (900, 500),   False),
]

LEGACY = [
    (0.0,  1.5,  (900, 500),   False),
    (1.5,  4.0,  (960, 1075),  False),    # trava desligada: rola direto
    (4.0,  5.0,  (900, 500),   False),
]

ZOOMED = [
    (0.0,  2.5,  (400, 300),   False),
    (2.5,  3.3,  (400, 300),   True),     # abre o zoom
    (3.3,  5.0,  (400, 300),   False),    # olha o alvo ampliado
    (5.0,  5.8,  (400, 300),   True),     # 0,8 s → clique
    (5.8,  8.0,  (1500, 800),  False),
    (8.0,  8.8,  (1500, 800),  True),
    (8.8,  10.5, (1500, 800),  False),
    (10.5, 12.1, (1500, 800),  True),     # 1,6 s → duplo clique
    (12.1, 14.0, (700, 600),   False),
    (14.0, 14.8, (700, 600),   True),
    (14.8, 16.5, (700, 600),   False),
    (16.5, 19.0, (700, 600),   True),     # 2,5 s → clique direito
    (19.0, 20.5, (700, 600),   False),
]


class Scenario:
    def __init__(self, script, drift_from=None, bad_calibrations=0, drift=DRIFT):
        self.script = script
        self.end = script[-1][1]
        self.drift_from = drift_from        # fase a partir da qual há desvio
        self.drift = drift
        self.bad_left = bad_calibrations
        self.phase = 'calib'
        self.target = (960, 540)
        self.head = False
        self.t0 = None
        self.zoom = None
        self.lock = None
        self.calibrations = 0
        self.validations = []
        self.rng = np.random.default_rng(42)
        self._wrong = {}

    def drift_on(self):
        order = ['calib', 'validation', 'main']
        return (self.drift_from is not None
                and order.index(self.phase) >= order.index(self.drift_from))

    def at(self, t):
        """(alvo na tela, olhos fechados, yaw, pitch) no instante t."""
        if self.phase == 'calib':
            if self.head:
                w = time.monotonic() * 3.0
                return self.target, False, 0.12 * np.sin(w), 0.08 * np.cos(w)
            if self.bad_left:
                # Usuário distraído: olha para outro lugar em cada ponto
                tgt = self._wrong.setdefault(self.target, (
                    self.rng.uniform(100, 1800), self.rng.uniform(100, 1000)))
                return tgt, False, 0.0, 0.0
            return self.target, False, 0.0, 0.0
        if self.phase == 'validation':
            return self.target, False, 0.0, 0.0
        s = t - self.t0
        for a, b, tgt, closed in self.script:
            if a <= s < b:
                if self.zoom is not None and self.zoom.active:
                    tgt = self.zoom.from_screen(*tgt)    # alvo dentro do zoom
                return tgt, closed, 0.0, 0.0
        return self.script[-1][2], False, 0.0, 0.0


class FakeCamera:
    width, height = 1280, 720

    def __init__(self):
        self.t = 1000.0
        self.frame = np.zeros((720, 1280, 3), np.uint8)

    def is_opened(self):
        return True

    def read(self, timeout=1.0):
        time.sleep(0.001)
        self.t += 1 / FPS
        return self.frame, self.t

    def release(self):
        pass


def make_estimator(scen):
    class FakeEstimator:
        def process(self, frame, t):
            tgt, closed, yaw, pitch = scen.at(t)
            eye, head = sim_user.features(tgt, yaw, pitch, rng=scen.rng)
            if scen.drift_on():
                eye = eye + scen.drift
            if closed:
                # Pálpebra cobrindo a íris: landmarks deslocados
                eye = eye + np.array([0, 0.06, 0, 0.06, 0.2, 0.2])
                openness = (0.05, 0.06)
            else:
                openness = (0.8 + scen.rng.normal(0, 0.01),
                            0.8 + scen.rng.normal(0, 0.01))
            return {'eye': eye, 'head': head, 'openness': openness,
                    'iris_left_px': np.array([600, 300]),
                    'iris_right_px': np.array([680, 300]),
                    'eye_l_center_px': np.array([600, 300]),
                    'eye_r_center_px': np.array([680, 300])}

        def draw_debug(self, frame, feat):
            return frame

        def close(self):
            pass
    return FakeEstimator


class FakeSounds:
    def __init__(self, *a, **k):
        pass

    def play(self, name):
        pass


class FakeXWin:
    """Janela X11 falsa: registra visibilidade e tamanho."""

    def __init__(self, w, h, round_, palette, origin=(0, 0)):
        self.w, self.h, self.round = w, h, round_
        self.visible = False
        FAKE_WINDOWS.append(self)

    def move(self, x, y):
        pass

    def raise_(self):
        pass

    def set_color(self, state):
        self.state = state

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def close(self):
        self.visible = False
        self.closed = True


FAKE_WINDOWS: list = []


def run_session(monkeypatch, tmp_path, scen, use_zoom=False, gui=False,
                lock_enabled=True, fake_x11=False):
    """
    gui=False: sem janelas e sem mouse real (testes).
    gui=True : janelas do OpenCV, captura de tela e mouse reais (smoke
               test em um servidor X, ex.: Xvfb).

    Returns (cliques, scrolls, erros dos cliques com zoom); cada scroll é
    ('scroll', passos, y da roda, instante no roteiro).
    """
    events, click_errors = [], []
    cam = FakeCamera()
    real = {n: getattr(mouse_backend, n)
            for n in ('click', 'double_click', 'right_click', 'scroll')}
    if not gui:
        monkeypatch.setattr(mouse_backend, 'available', lambda: True)
        monkeypatch.setattr(mouse_backend, 'move', lambda x, y: None)
        monkeypatch.setattr(mouse_backend, 'shutdown', lambda: None)
    for name in ('click', 'double_click', 'right_click'):
        def spy(x, y, _n=name):
            events.append((_n, x, y))
            if gui:
                real[_n](x, y)
        monkeypatch.setattr(mouse_backend, name, spy)

    def spy_scroll(n, x=None, y=None):
        events.append(('scroll', n, y, cam.t - (scen.t0 or cam.t)))
        if gui:
            real['scroll'](n, x, y)
    monkeypatch.setattr(mouse_backend, 'scroll', spy_scroll)

    real_wait = cv2.waitKey
    if not gui:
        # Janelas do OpenCV: sem interface gráfica no teste
        for fn in ('namedWindow', 'moveWindow', 'setWindowProperty', 'imshow',
                   'destroyWindow', 'destroyAllWindows', 'resizeWindow'):
            monkeypatch.setattr(cv2, fn, lambda *a, **k: None)

    def wait_key(ms=0):
        k = real_wait(max(1, min(ms, 5))) if gui else -1
        return ord('q') if (scen.phase == 'main'
                            and cam.t - scen.t0 > scen.end) else k
    monkeypatch.setattr(cv2, 'waitKey', wait_key)
    monkeypatch.setattr(builtins, 'input', lambda *a: '')

    monkeypatch.setattr(main, 'Camera', lambda *a, **k: cam)
    monkeypatch.setattr(main, 'GazeEstimator', make_estimator(scen))
    monkeypatch.setattr(main, 'Sounds', FakeSounds)
    monkeypatch.setattr(main, 'CALIB_FILE', str(tmp_path / 'calib.pkl'))
    monkeypatch.setattr(main, 'ZOOM_CLICK_ENABLED', use_zoom)
    monkeypatch.setattr(main.MetricsCollector, 'save_csv', lambda *a, **k: None)

    if fake_x11:
        FAKE_WINDOWS.clear()
        monkeypatch.setattr(gaze_overlay, '_x11_available', lambda: True)
        monkeypatch.setattr(gaze_overlay, '_ShapedWindow', FakeXWin)
    scen.visible_at_grab = []

    class RecZoom(zoom_mod.ZoomView):
        def __init__(self, sw, sh, origin):
            def fake_grab():
                # Bola e barra da alça não podem aparecer na captura
                scen.visible_at_grab += [w for w in FAKE_WINDOWS
                                         if w.visible and not getattr(w, 'closed', False)]
                return np.zeros((sh, sw, 3), np.uint8)
            super().__init__(sw, sh, origin, grab=None if gui else fake_grab)
            scen.zoom = self
    monkeypatch.setattr(main, 'ZoomView', RecZoom)

    monkeypatch.setattr(config, 'SCROLL_LOCK_ENABLED', lock_enabled)

    class RecLock(scroll_lock_mod.ScrollLock):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            scen.lock = self
    monkeypatch.setattr(main, 'ScrollLock', RecLock)

    # Animações rápidas
    monkeypatch.setattr(calibration, 'CALIB_PULSE_MS', 5)
    monkeypatch.setattr(calibration, 'CALIB_CAPTURE_MS', 120)
    monkeypatch.setattr(calibration, 'CALIB_HEAD_STEP_MS', 80)
    monkeypatch.setattr(calibration, '_HEAD_INTRO_S', 0.05)
    monkeypatch.setattr(validation, 'VALIDATION_PULSE_MS', 5)

    orig_run = calibration.CalibrationScreen.run
    orig_capture = calibration.CalibrationScreen._capture
    orig_head = calibration.CalibrationScreen._head_motion
    orig_val_capture = validation.ValidationScreen._capture
    orig_val_run = validation.ValidationScreen.run

    def calib_run(self, est, cam_):
        scen.phase = 'calib'
        try:
            return orig_run(self, est, cam_)
        finally:
            scen.calibrations += 1
            scen.bad_left = max(0, scen.bad_left - 1)

    def capture(self, est, cam_, pt, idx):
        scen.phase, scen.target, scen.head = 'calib', pt, False
        return orig_capture(self, est, cam_, pt, idx)

    def head(self, est, cam_):
        scen.target, scen.head = (self.sw // 2, self.sh // 2), True
        try:
            return orig_head(self, est, cam_)
        finally:
            scen.head = False

    def val_capture(self, model, est, cam_, pt, idx):
        scen.phase, scen.target = 'validation', pt
        return orig_val_capture(self, model, est, cam_, pt, idx)

    def val_run(self, *a, **k):
        res = orig_val_run(self, *a, **k)
        scen.validations.append(res)
        return res

    def controls():
        scen.phase, scen.t0 = 'main', cam.t

    orig_add = correction_mod.GazeCorrection.add

    def add(self, pred, true, t, kind='click', weight=1.0):
        if kind == 'click':
            est = np.array(self.apply(*pred))
            click_errors.append(float(np.hypot(*(est - np.array(true)))))
        return orig_add(self, pred, true, t, kind, weight)

    monkeypatch.setattr(calibration.CalibrationScreen, 'run', calib_run)
    monkeypatch.setattr(calibration.CalibrationScreen, '_capture', capture)
    monkeypatch.setattr(calibration.CalibrationScreen, '_head_motion', head)
    monkeypatch.setattr(validation.ValidationScreen, '_capture', val_capture)
    monkeypatch.setattr(validation.ValidationScreen, 'run', val_run)
    monkeypatch.setattr(main, '_print_controls', controls)
    monkeypatch.setattr(correction_mod.GazeCorrection, 'add', add)

    main.main()

    clicks = [e for e in events if e[0] != 'scroll']
    scrolls = [e for e in events if e[0] == 'scroll']
    return clicks, scrolls, click_errors


def _near(clicks, targets, tol):
    for (_, x, y), tgt in zip(clicks, targets):
        assert np.hypot(x - tgt[0], y - tgt[1]) < tol, ((x, y), tgt)


def test_direct_clicks_with_systematic_drift(monkeypatch, tmp_path, capsys):
    scen = Scenario(DIRECT, drift_from='validation')
    clicks, scrolls, _ = run_session(monkeypatch, tmp_path, scen)
    val = scen.validations[-1]
    with capsys.disabled():
        print(f'\n  validação: erro {val.error:.0f} px (sem correção '
              f'{val.raw_error:.0f} px) | cliques: {clicks}')
    lock_events = [(locked, reason) for _, locked, reason, _ in scen.lock.events]
    with capsys.disabled():
        print(f'  trava do scroll: {lock_events} | scroll entre '
              f'{scrolls[0][3]:.1f} e {scrolls[-1][3]:.1f} s' if scrolls else '')
    # A validação viu o desvio e a correção o removeu
    assert val.raw_error > 80 and val.passed
    # Destravar e frear NÃO são cliques
    assert [c[0] for c in clicks] == ['click', 'double_click', 'right_click']
    _near(clicks, [(400, 300), (1500, 800), (700, 600)], 60)
    # Destravado pela alça, travado pelo freio
    assert lock_events == [(False, 'alca'), (True, 'freio')]
    # Só rolou entre destravar e frear (antes, travado, a borda não rolava)
    assert scrolls and all(15.6 <= e[3] <= 18.4 for e in scrolls)
    assert all(e[1] < 0 for e in scrolls) and -sum(e[1] for e in scrolls) >= 5
    # Roda sobre o conteúdo (fora da faixa e fora da janela de debug)
    assert all(e[2] < main.SCREEN_H * 0.88 for e in scrolls)


def test_bad_calibration_is_redone_automatically(monkeypatch, tmp_path, capsys):
    scen = Scenario(DIRECT[:3], bad_calibrations=1)
    run_session(monkeypatch, tmp_path, scen)
    errs = [v.error for v in scen.validations]
    with capsys.disabled():
        print(f'\n  calibrações: {scen.calibrations} | erros da validação: '
              f'{[round(e) for e in errs]}')
    assert scen.calibrations == 2
    assert not scen.validations[0].passed and scen.validations[1].passed


def test_zoom_clicks_are_precise_and_teach_the_correction(monkeypatch, tmp_path,
                                                         capsys):
    scen = Scenario(ZOOMED, drift_from='main')     # desvio DEPOIS da validação
    clicks, _, errs = run_session(monkeypatch, tmp_path, scen, use_zoom=True,
                                  fake_x11=True)
    with capsys.disabled():
        print(f'\n  cliques com zoom: {clicks}')
        print(f'  erro do olhar medido em cada clique: {[round(e) for e in errs]} px')
    assert [c[0] for c in clicks] == ['click', 'double_click', 'right_click']
    # Zoom e cliques não destravam o scroll
    assert scen.lock.locked and scen.lock.events == []
    # A bola e a barra da alça existem, mas somem antes de cada captura do zoom
    bars = [w for w in FAKE_WINDOWS if not w.round]
    assert bars and any(w.round for w in FAKE_WINDOWS)
    assert scen.visible_at_grab == []
    # A barra tem a altura da alça ajustada ao erro da validação
    (_, y0, _, y1), = scen.lock.regions
    assert bars[-1].h == int(y1 - y0)
    # Mesmo com ~120 px de desvio, o clique cai perto do alvo
    _near(clicks, [(400, 300), (1500, 800), (700, 600)], 60)
    _near(clicks[1:], [(1500, 800), (700, 600)], 35)
    # E cada clique ensina a correção: o erro medido cai. (O 1º erro medido
    # é menor que a deriva real: o ponto do zoom carrega 1/ZOOM_FACTOR dela)
    assert errs[0] > 60 and errs[-1] < 0.5 * errs[0]


def test_handle_reachable_with_leftward_drift(monkeypatch, tmp_path, capsys):
    # Desvio de ~120 px para a esquerda surgindo depois da validação: olhando
    # a barra de rolagem, a estimativa cai fora da alça; olhar além da borda
    # (para a moldura do monitor) ainda a alcança
    scen = Scenario(HANDLE_DRIFT, drift_from='main', drift=-DRIFT)
    _, scrolls, _ = run_session(monkeypatch, tmp_path, scen)
    lock_events = [(locked, reason) for _, locked, reason, _ in scen.lock.events]
    with capsys.disabled():
        print(f'\n  trava com desvio: {lock_events} | passos: '
              f'{-sum(e[1] for e in scrolls)}')
    assert lock_events[:1] == [(False, 'alca')]
    assert -sum(e[1] for e in scrolls) >= 5


def test_lock_disabled_scrolls_like_before(monkeypatch, tmp_path):
    scen = Scenario(LEGACY)
    _, scrolls, _ = run_session(monkeypatch, tmp_path, scen, lock_enabled=False)
    assert scen.lock.events == []
    assert -sum(e[1] for e in scrolls) >= 5
