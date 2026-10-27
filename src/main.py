"""
EyeNav – navegação web pelo olhar.

TC II – Ciência da Computação | UNIP  | 
Autor: Erick Martins Paulino Silva

Ponto de entrada: abre a câmera, calibra e valida, e roda o loop principal
(olhar → cursor, piscadas → cliques, bordas → scroll). As teclas da janela
de debug estão em _print_controls().
"""

import copy
import sys
import time
from collections import deque

from desktop import mouse_backend      # primeiro: inicializa o X11 para várias threads
import cv2
import numpy as np


def _screen_geometry() -> tuple[int, int, int, int]:
    try:
        from screeninfo import get_monitors
        mons = get_monitors()
        m = next((m for m in mons if getattr(m, 'is_primary', False)), mons[0])
        return m.x, m.y, m.width, m.height
    except Exception:
        return 0, 0, 1920, 1080


SCREEN_X, SCREEN_Y, SCREEN_W, SCREEN_H = _screen_geometry()

from config            import (WEBCAM_INDEX, WEBCAM_WIDTH, WEBCAM_HEIGHT,
                                TARGET_FPS, CALIB_FILE, SMOOTHER,
                                SHOW_DEBUG_WINDOW, DEBUG_WINDOW_SCALE,
                                DWELL_TIME_MS, DWELL_RADIUS_PX,
                                DWELL_CLICK_ENABLED, BLINK_CLICK_ENABLED,
                                SCROLL_ENABLED, ZOOM_CLICK_ENABLED,
                                VALIDATION_ENABLED, CALIB_MAX_ATTEMPTS,
                                BLINK_POS_LOOKBACK_MS, EDGE_SNAP_PX,
                                SCROLL_LOCK_ON_CLICK, SCROLL_LOCK_ON_CANCEL,
                                SCROLL_PARK_AVOID_DEBUG, SCROLL_HANDLE_SIDE,
                                SCROLL_HANDLE_MAX_WIDTH_PX)
from capture.camera            import Camera
from tracking.gaze_estimator    import GazeEstimator
from tracking.gaze_model        import GazeModel
from calibration.calibration       import CalibrationScreen
from calibration.validation        import ValidationScreen
from tracking.correction        import GazeCorrection
from desktop.gaze_overlay      import GazeOverlay, EdgeBar, dwell_state
from tracking.smoother          import GazeSmoother
from interaction.cursor_controller import CursorController
from interaction.dwell_clicker     import DwellClicker
from interaction.blink_clicker     import BlinkClicker, fire
from tracking.eye_state         import EyeState, OPEN
from interaction.edge_scroller     import EdgeScroller
from interaction.scroll_lock       import ScrollLock, PROMISES
from interaction.zoom              import ZoomView
from desktop.feedback          import Sounds
from diagnostics.metrics           import MetricsCollector
from diagnostics.recorder          import SessionRecorder


_GREEN  = (0, 220, 80)
_CYAN   = (0, 220, 220)
_RED    = (0, 60, 220)
_WHITE  = (220, 220, 220)
_GRAY   = (120, 120, 120)
_YELLOW = (0, 200, 255)
_ORANGE = (0, 165, 255)

_CLICK_FLASH_S = 0.35
_ACTION_LABEL  = {'single': 'CLIQUE', 'double': 'DUPLO CLIQUE',
                  'right': 'CLIQUE DIREITO',
                  'scroll_unlock': 'DESTRAVAR SCROLL',
                  'scroll_lock': 'TRAVAR SCROLL',
                  'scroll_brake': 'FREAR E TRAVAR SCROLL'}
_VIOLET        = (255, 80, 170)    # BGR


def _to_screen(x: float, y: float) -> tuple[int, int]:
    if x < EDGE_SNAP_PX:
        x = 0
    elif x > SCREEN_W - 1 - EDGE_SNAP_PX:
        x = SCREEN_W - 1
    if y < EDGE_SNAP_PX:
        y = 0
    elif y > SCREEN_H - 1 - EDGE_SNAP_PX:
        y = SCREEN_H - 1

    return (int(max(0, min(x, SCREEN_W - 1))),
            int(max(0, min(y, SCREEN_H - 1))))


def _clamp_raw(x: float, y: float) -> tuple[float, float]:
    return (min(max(x, -0.25 * SCREEN_W), 1.25 * SCREEN_W),
            min(max(y, -0.25 * SCREEN_H), 1.25 * SCREEN_H))


def _to_cam(p, cam_w, cam_h) -> tuple[int, int]:
    return int(p[0] * cam_w / SCREEN_W), int(p[1] * cam_h / SCREEN_H)


def _draw_dwell_arc(frame: np.ndarray, cx: int, cy: int, progress: float):
    r = DWELL_RADIUS_PX
    cv2.circle(frame, (cx, cy), r, _GRAY, 1)
    if progress > 0:
        angle = int(360 * progress)
        for a in range(0, min(angle, 360), 4):
            rad = np.radians(a - 90)
            px  = int(cx + (r - 4) * np.cos(rad))
            py  = int(cy + (r - 4) * np.sin(rad))
            g   = int(80  + 140 * progress)
            b   = int(200 * progress)
            cv2.circle(frame, (px, py), 2, (b, g, 0), -1)


def _draw_scroll_zone(frame: np.ndarray, cam_h: int, cam_w: int,
                      zone: str | None, activation: float):
    if zone == 'top':
        cv2.rectangle(frame, (0, 0), (cam_w, 18), _ORANGE, -1)
        cv2.putText(frame, 'SCROLL UP', (cam_w // 2 - 45, 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    elif zone == 'bottom':
        cv2.rectangle(frame, (0, cam_h - 18), (cam_w, cam_h), _ORANGE, -1)
        cv2.putText(frame, 'SCROLL DOWN', (cam_w // 2 - 55, cam_h - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    elif activation > 0:
        cv2.rectangle(frame, (0, 0), (int(cam_w * activation), 4), _ORANGE, -1)


def _draw_handle(frame: np.ndarray, regions: list, cam_w: int, cam_h: int,
                 color: tuple):
    for x0, y0, x1, y1 in regions:
        cv2.rectangle(frame, _to_cam((x0, y0), cam_w, cam_h),
                      _to_cam((x1 - 1, y1), cam_w, cam_h), color, 2)


def _draw_info_panel(frame: np.ndarray, lines: list[tuple[str, tuple]]):
    for i, (text, color) in enumerate(lines):
        cv2.putText(frame, text, (8, 28 + i * 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 1, cv2.LINE_AA)


def main():
    _banner()

    if not mouse_backend.available():
        print('[ERRO] Nenhum backend de mouse disponível.')
        print('       sudo apt install libxtst6   ou   pip install pynput')
        sys.exit(1)
    mouse_backend.set_origin(SCREEN_X, SCREEN_Y)

    cam = Camera(WEBCAM_INDEX, WEBCAM_WIDTH, WEBCAM_HEIGHT, TARGET_FPS)
    if not cam.is_opened():
        print(f'[ERRO] Câmera {WEBCAM_INDEX} não encontrada.')
        print('       Verifique WEBCAM_INDEX em src/config.py')
        sys.exit(1)
    cam_w, cam_h = cam.width, cam.height
    print(f'  Câmera aberta: {cam_w}×{cam_h} @ índice {WEBCAM_INDEX}')
    if cam_w < WEBCAM_WIDTH:
        print(f'  [AVISO] Resolução abaixo da pedida ({WEBCAM_WIDTH}×{WEBCAM_HEIGHT}). '
              f'A precisão do olhar será menor.')
    print(f'  Tela:          {SCREEN_W}×{SCREEN_H} em ({SCREEN_X}, {SCREEN_Y})')

    estimator  = GazeEstimator()
    model      = GazeModel()
    smoother   = GazeSmoother()
    correction = GazeCorrection(SCREEN_W, SCREEN_H)
    sounds     = Sounds()
    cursor     = CursorController(SCREEN_W, SCREEN_H)
    dwell      = DwellClicker()
    blink      = BlinkClicker(sounds)
    scroller   = EdgeScroller(SCREEN_W, SCREEN_H)
    scroll_lock = ScrollLock(SCREEN_W, SCREEN_H)
    eye_state  = EyeState(SCREEN_H)
    metrics    = MetricsCollector()
    recorder   = SessionRecorder()

    force = _ask_calibration(model)
    val = _setup(model, estimator, cam, smoother, eye_state, force)
    if val is not None:
        correction = val.correction
        scroll_lock.fit_to_error(val.error)

    overlay  = GazeOverlay(origin=(SCREEN_X, SCREEN_Y))
    edge_bar = EdgeBar(SCREEN_W, scroll_lock.regions, (SCREEN_X, SCREEN_Y))
    zoom     = ZoomView(SCREEN_W, SCREEN_H, (SCREEN_X, SCREEN_Y))

    debug_win = None
    if SHOW_DEBUG_WINDOW:
        debug_win = 'EyeNav – Debug'
        cv2.namedWindow(debug_win, cv2.WINDOW_NORMAL)
        _dw = int(cam_w * DEBUG_WINDOW_SCALE)
        _dh = int(cam_h * DEBUG_WINDOW_SCALE)
        cv2.resizeWindow(debug_win, _dw, _dh)
        cv2.setWindowProperty(debug_win, cv2.WND_PROP_TOPMOST, 1)
        right = 10 + (SCROLL_HANDLE_MAX_WIDTH_PX
                      if scroll_lock.enabled and SCROLL_HANDLE_SIDE != 'left' else 0)
        _dx, _dy = SCREEN_W - _dw - right, SCREEN_H - _dh - 60
        cv2.moveWindow(debug_win, SCREEN_X + _dx, SCREEN_Y + _dy)
        if SCROLL_PARK_AVOID_DEBUG:
            # O cursor estacionado durante o scroll não pode cair na janela
            # (a roda iria para ela); margem para a barra de título
            scroller.avoid = [(_dx - 20, _dy - 40, _dx + _dw + 20, _dy + _dh + 20)]

    _print_controls()

    dwell_on     = DWELL_CLICK_ENABLED
    blink_on     = BLINK_CLICK_ENABLED
    scroll_on    = SCROLL_ENABLED
    zoom_on      = ZOOM_CLICK_ENABLED and zoom.available
    paused       = False
    gaze         = (SCREEN_W // 2, SCREEN_H // 2)
    raw_trail    = deque(maxlen=15)
    click_errors = []
    t_flash      = -1e9
    t_label      = -1e9
    last_action  = ''
    fps_val      = 0.0
    fps_counter  = 0
    fps_t        = time.monotonic()
    screenshot_n = 0
    dbg          = None

    def locate(t_past: float):
        p = smoother.position_at(t_past)
        return _to_screen(*correction.apply(*p)) if p else None

    def flash(t_now, label):
        nonlocal t_flash
        t_flash = t_now
        note(t_now, label)

    def note(t_now, label):
        nonlocal t_label, last_action
        t_label, last_action = t_now, label

    def set_scroll(locked: bool, t_now: float, reason: str, sound=None) -> bool:
        notches = scroll_lock.notches
        changed = (scroll_lock.lock(t_now, reason) if locked
                   else scroll_lock.unlock(t_now, reason))
        if not changed:
            return False
        scroller.reset()
        dwell.reset()
        if sound:
            sounds.play(sound)
        label = 'SCROLL TRAVADO' if locked else 'SCROLL LIVRE'
        note(t_now, label)
        print(f'  [SCROLL] {"TRAVADO" if locked else "LIVRE"} ({reason})')
        metrics.record_scroll_lock(locked, reason, notches if locked else 0)
        recorder.event(t_now, 'scroll_lock', travado=locked, motivo=reason,
                       passos=notches)
        return True

    def lock_after_click(t_now, reason='clique'):
        if SCROLL_LOCK_ON_CLICK:
            set_scroll(True, t_now, reason)

    try:
        while True:
            frame, t = cam.read()
            if frame is None:
                if (cv2.waitKey(1) & 0xFF) in (ord('q'), 27):
                    break
                continue
            t0 = time.perf_counter()

            fps_counter += 1
            if fps_counter % 30 == 0:
                now = time.monotonic()
                fps_val     = 30 / max(now - fps_t, 1e-9)
                fps_t       = now
                fps_counter = 0

            feat    = estimator.process(frame, t)
            face_ok = feat is not None
            blocked = True
            raw     = None
            corr_xy = None

            if model.is_trained:
                blocked = eye_state.update(feat['openness'] if face_ok else None,
                                           gaze[1], t)
                if face_ok and not blocked:
                    raw = _clamp_raw(*model.predict(feat))
                    fx, fy = smoother.update(*raw, t)
                    corr_xy = correction.apply(fx, fy)
                    gaze = _to_screen(*corr_xy)
                    raw_trail.append(_to_screen(*correction.apply(*raw)))
                else:
                    smoother.hold()

                claim = (scroll_lock.claim
                         if scroll_on and not zoom.active and not paused else None)
                res = (blink.update(eye_state, t, locate, claim)
                       if blink_on and not paused else None)

                if blink.cancelled and SCROLL_LOCK_ON_CANCEL:
                    set_scroll(True, t, 'cancelar', 'scroll_off')
                if res and res[0] in PROMISES:
                    set_scroll(res[0] != 'scroll_unlock', t,
                               'freio' if res[0] == 'scroll_brake' else 'alca')
                    res = None

                if zoom.active:
                    if res:
                        action, x, y = res
                        cx, cy = zoom.to_screen(x, y)
                        anchor = zoom.anchor_raw
                        zoom.close()
                        fire(action, cx, cy)
                        metrics.record_click(cx, cy, dwell_ms=0, kind=action)
                        flash(t, _ACTION_LABEL[action])
                        lock_after_click(t)
                        if anchor is not None:
                            # Calibração implícita: estimado × real
                            est = np.array(correction.apply(*anchor))
                            err = float(np.hypot(*(est - (cx, cy))))
                            click_errors.append(err)
                            correction.add(anchor, (cx, cy), t, kind='click')
                            correction.fit(t)
                            recorder.event(t, 'zoom_click', action=action,
                                           estimado=est.tolist(), real=(cx, cy))
                            print(f'  [ZOOM] erro do olhar neste clique: '
                                  f'{err:.0f} px  (média de {len(click_errors)}: '
                                  f'{np.mean(click_errors):.0f} px)')
                    elif blink.cancelled or zoom.expired(t):
                        zoom.close()
                        print('  [ZOOM] cancelado')
                elif res:
                    action, x, y = res
                    opened = False
                    if zoom_on:
                        overlay.hide()
                        edge_bar.hide()
                        time.sleep(0.05)
                        opened = zoom.open(x, y, t)
                        if opened:
                            zoom.anchor_raw = smoother.position_at(
                                eye_state.gate_since - BLINK_POS_LOOKBACK_MS / 1000)
                            scroller.reset()
                            dwell.reset()
                            lock_after_click(t, 'zoom')
                        else:
                            zoom_on = False
                    if not opened:
                        fire(action, x, y)
                        metrics.record_click(x, y, dwell_ms=0, kind=action)
                        recorder.event(t, 'click', action=action, pos=(x, y))
                        dwell.reset()
                        flash(t, _ACTION_LABEL[action])
                        lock_after_click(t)

                if not paused and not blocked and not zoom.active:
                    if dwell_on and (scroll_lock.in_handle or scroller.active_zone):
                        dwell.reset()
                    elif dwell_on and dwell.update(*gaze, t):
                        ax, ay = dwell.anchor
                        metrics.record_click(int(ax), int(ay),
                                             dwell_ms=DWELL_TIME_MS)
                        flash(t, 'DWELL')
                        print(f'  [DWELL] ({int(ax)}, {int(ay)})')
                        lock_after_click(t)
                    if scroll_on:
                        if scroll_lock.allows_scroll:
                            n = scroller.update(gaze[0], gaze[1], t, raw=corr_xy)
                            scroll_lock.note_scroll(t, n)
                        scroll_lock.observe(
                            gaze[0], gaze[1], t, moving=scroller.moving(t),
                            in_band=scroller.zone_of(gaze[1]) is not None,
                            engaged=scroller.engaged)
                        p = scroll_lock.dwell_toggle(t, blink_on)
                        if p:
                            unlock = p == 'scroll_unlock'
                            set_scroll(not unlock, t, 'dwell',
                                       'scroll_on' if unlock else 'scroll_off')
                elif not paused:
                    scroller.pause(t)
                    scroll_lock.pause(t, scroller.active_zone is not None,
                                      carry=face_ok and not zoom.active)

                # Travas automáticas só com os olhos abertos: no meio de uma
                # piscada elas atropelariam a promessa que a bola mostrou
                if scroll_on and not paused and eye_state.state == OPEN:
                    reason = scroll_lock.tick(t, face_ok)
                    if reason:
                        set_scroll(True, t, reason, 'scroll_auto_off')

                cursor.move(*(scroller.park_point or gaze))
                if face_ok:
                    overlay.move(*gaze)
                lock_view = scroll_lock.view if scroll_on else None
                pulse = scroll_lock.pulse_on(t)
                rest = (dwell_state(dwell.progress) if dwell_on and dwell.progress > 0
                        else 'unlocked' if scroll_on and scroll_lock.enabled
                        and not scroll_lock.locked else 'normal')
                overlay.set_state(
                    'paused' if paused else
                    'click'  if t - t_flash < _CLICK_FLASH_S else
                    'closed' if eye_state.closed and blink.armed else
                    'zoom'   if zoom.active else
                    ('handle' if pulse else rest) if lock_view == 'handle' else
                    'scroll' if lock_view == 'scroll' or (
                        not scroll_lock.enabled and scroller.active_zone) else
                    rest)

                if paused or zoom.active or not scroll_on:
                    edge_bar.hide()
                else:
                    edge_bar.show()
                    hint = scroll_lock.hint_active(t) and int(t * 4) % 2 == 0
                    edge_bar.set_state(
                        'handle' if (lock_view == 'handle' and pulse) or hint else
                        'scroll' if lock_view == 'scroll' else
                        'locked' if scroll_lock.locked else 'unlocked', t)

            recorder.add(t, feat, raw, gaze, eye_state.state, blocked)
            proc_ms = (time.perf_counter() - t0) * 1000
            metrics.record_frame(proc_ms)

            if debug_win:
                dbg = frame.copy()
                if face_ok:
                    dbg = estimator.draw_debug(dbg, feat)
                    for p in raw_trail:
                        cv2.circle(dbg, _to_cam(p, cam_w, cam_h), 2, _RED, -1)
                    gx, gy = _to_cam(gaze, cam_w, cam_h)
                    if dwell_on:
                        _draw_dwell_arc(dbg, gx, gy, dwell.progress)
                    cv2.circle(dbg, (gx, gy), 7, _GREEN, -1)

                _draw_scroll_zone(dbg, cam_h, cam_w, scroller.active_zone,
                                  scroller.activation)
                if scroll_on and scroll_lock.enabled:
                    _draw_handle(dbg, scroll_lock.regions, cam_w, cam_h,
                                 _WHITE if scroll_lock.lit else
                                 _GRAY if scroll_lock.locked else _VIOLET)

                total_ms = (time.monotonic() - t) * 1000
                prec = f'~{val.error:.0f} px' if val is not None else '?'
                if click_errors:
                    prec += (f'  | cliques: {np.mean(click_errors[-10:]):.0f} px '
                             f'({len(click_errors)})')
                info = [
                    (f'FPS: {fps_val:.1f}  |  Proc: {proc_ms:.0f} ms  |  '
                     f'Latencia: {total_ms:.0f} ms', _CYAN),
                    (f'Face: {"Detectada" if face_ok else "Ausente"}  |  '
                     f'Precisao: {prec}', _GREEN if face_ok else _RED),
                    (f'{"PAUSADO" if paused else "ATIVO"}  |  '
                     f'Blink: {"ON" if blink_on else "OFF"}  '
                     f'Zoom: {"ON" if zoom_on else "OFF"}  '
                     f'Dwell: {"ON" if dwell_on else "OFF"}  '
                     f'Scroll: {_scroll_text(scroll_on, scroll_lock, t)}'
                     f'{"  | GRAVANDO" if recorder.active else ""}',
                     _ORANGE if paused or recorder.active else _WHITE),
                    (f'Gaze (tela): {gaze}  |  {smoother.debug_text()}', _YELLOW),
                ]
                if face_ok:
                    ra, rb = eye_state.ratio
                    txt = (f'Olhos: {eye_state.state}  abertura {ra:.2f} / '
                           f'{rb:.2f}  piscadas: {eye_state.blinks}')
                    armed = blink.armed
                    if armed:
                        what = ('ZOOM' if armed not in PROMISES and zoom_on
                                and not zoom.active else _ACTION_LABEL[armed])
                        txt += f'  -> abrir = {what}'
                    info.append((txt, _ORANGE if eye_state.blocked else _YELLOW))
                if scroll_on and scroll_lock.hint_active(t):
                    info.append(('DICA: destrave o scroll na alca (borda direita)',
                                 _VIOLET))
                if t - t_label < 1.5 and last_action:
                    info.append((f'>>> {last_action}', _GREEN))
                _draw_info_panel(dbg, info)

                cv2.putText(dbg,
                            'Q=Sair R=Recalib F=Validar P=Pausa Z=Zoom L=Trava '
                            'D=Dwell B=Blink G=Gravar M=Metricas S=Screen',
                            (6, cam_h - 26), cv2.FONT_HERSHEY_SIMPLEX, 0.42, _GRAY, 1)
                cv2.imshow(debug_win, dbg)

            key = cv2.waitKey(1) & 0xFF

            if key in (ord('q'), 27):
                break

            elif key in (ord('r'), ord('f')):
                recal = key == ord('r')
                print('\n  Iniciando recalibração...' if recal else
                      '\n  Refazendo a validação...')
                set_scroll(True, t, 'recalibracao')
                overlay.hide()
                edge_bar.hide()
                zoom.close()
                new = _setup(model, estimator, cam, smoother, eye_state, recal)
                if new is not None:
                    val, correction = new, new.correction
                    click_errors.clear()
                    scroll_lock.fit_to_error(val.error)
                    edge_bar.set_regions(scroll_lock.regions)
                for m in (dwell, blink, scroller):
                    m.reset()

            elif key == ord('p'):
                paused = not paused
                set_scroll(True, t, 'pausa')
                zoom.close()
                dwell.reset()
                blink.reset()
                scroller.reset()
                print(f'  Cliques e scroll: {"PAUSADOS" if paused else "RETOMADOS"}')

            elif key == ord('z'):
                if not zoom.available:
                    print('  Clique com zoom indisponível (pip install mss; '
                          'não funciona em Wayland).')
                else:
                    zoom_on = not zoom_on
                    zoom.close()
                    print(f'  Clique com zoom: {"ATIVADO" if zoom_on else "DESATIVADO"}')

            elif key == ord('l'):
                if scroll_lock.enabled:
                    unlock = scroll_lock.locked
                    set_scroll(not unlock, t, 'tecla',
                               'scroll_on' if unlock else 'scroll_off')
                else:
                    print('  Trava do scroll desligada (SCROLL_LOCK_ENABLED).')

            elif key == ord('d'):
                dwell_on = not dwell_on
                dwell.reset()
                print(f'  Dwell click: {"ATIVADO" if dwell_on else "DESATIVADO"}')

            elif key == ord('b'):
                blink_on = not blink_on
                blink.reset()
                set_scroll(True, t, 'blink')
                print(f'  Blink click: {"ATIVADO" if blink_on else "DESATIVADO"}')

            elif key == ord('g'):
                if recorder.active:
                    recorder.stop()
                else:
                    recorder.start(_session_meta(cam_w, cam_h, model, val))

            elif key == ord('m'):
                metrics.print_summary()
                metrics.save_csv('eyenav_metrics.csv')

            elif key == ord('s') and dbg is not None:
                fname = f'eyenav_screenshot_{screenshot_n:03d}.png'
                cv2.imwrite(fname, dbg)
                print(f'  Screenshot salvo: {fname}')
                screenshot_n += 1

    except KeyboardInterrupt:
        pass

    finally:
        print('\n  Encerrando EyeNav...')
        recorder.stop()
        metrics.print_summary()
        if click_errors:
            print(f'  Erro do olhar medido nos cliques com zoom: '
                  f'{np.mean(click_errors):.0f} px (média de {len(click_errors)})')
        metrics.save_csv()
        cam.release()
        zoom.close()
        cv2.destroyAllWindows()
        overlay.close()
        edge_bar.close()
        estimator.close()
        mouse_backend.shutdown()
        print('  Encerrado. Até a próxima!')


def _scroll_text(scroll_on: bool, lock: ScrollLock, t: float) -> str:
    if not scroll_on:
        return 'OFF'
    if not lock.enabled:
        return 'ON'
    if lock.locked:
        return 'TRAVADO'
    left = lock.seconds_to_idle_lock(t)
    return 'LIVRE' + (f' (trava em {left:.0f}s)' if left is not None else '')


def _ask_calibration(model) -> bool:
    if model.load(CALIB_FILE):
        resp = input('\n  Calibração encontrada. Deseja recalibrar? (s/N): ')
        return resp.strip().lower() == 's'

    print()
    print('  ┌────────────────────────────────────────────┐')
    print('  │  CALIBRAÇÃO                                │')
    print('  │  1. Mova apenas os olhos, não a cabeça.    │')
    print('  │     Fixe o olhar em cada círculo até       │')
    print('  │     o arco completar.                      │')
    print('  │  2. Olhos no ponto central: gire a cabeça  │')
    print('  │     devagar seguindo as setas              │')
    print('  │     (ESPAÇO pula esta etapa).              │')
    print('  │  3. Validação: fixe 5 pontos. Se a         │')
    print('  │     precisão for ruim, a calibração é      │')
    print('  │     refeita automaticamente.               │')
    print('  │  ESC = cancelar                            │')
    print('  └────────────────────────────────────────────┘')
    input('  Pressione ENTER para iniciar...')
    return True


def _calibrate(model, estimator, cam) -> bool:
    screen = CalibrationScreen(SCREEN_W, SCREEN_H, (SCREEN_X, SCREEN_Y))
    data = screen.run(estimator, cam)
    if not data:
        return False
    try:
        model.train(data['eye'], data['head'], data['targets'], data['groups'],
                    eye_baselines=data['eye_baselines'])
    except ValueError as e:
        print(f'  [AVISO] {e}')
        return False
    model.save(CALIB_FILE)
    print(f'  Calibração concluída com {len(data["eye"])} amostras.\n')
    return True


def _setup(model, estimator, cam, smoother, eye_state, force_calib=False):
    attempts, best, n_val = 0, None, 0
    need_calib = force_calib or not model.is_trained
    while True:
        if need_calib:
            if attempts >= CALIB_MAX_ATTEMPTS:
                break
            attempts += 1
            if attempts > 1:
                print(f'\n  Recalibrando (tentativa {attempts} de {CALIB_MAX_ATTEMPTS})...')
            if not _calibrate(model, estimator, cam):
                print('  [AVISO] Calibração cancelada ou incompleta.')
                break
        if not model.is_trained or not VALIDATION_ENABLED:
            break

        print('\n  Validação: fixe o olhar em cada ponto.')
        res = ValidationScreen(SCREEN_W, SCREEN_H, (SCREEN_X, SCREEN_Y)).run(
            model, estimator, cam, will_retry=attempts < CALIB_MAX_ATTEMPTS)
        if res is None:
            print('  Validação pulada (ESC).')
            best = None
            break
        n_val += 1
        if best is None or res.error < best[0].error:
            best = (res, copy.deepcopy(model), n_val)
        if res.passed:
            break
        need_calib = True

    if best is not None:
        res, snapshot, idx = best
        if idx != n_val:
            model.__dict__.update(snapshot.__dict__)
            if attempts:
                model.save(CALIB_FILE)
        print(f'  Precisão estimada: {res.error:.0f} px '
              f'({"OK" if res.passed else "abaixo do desejado"}).\n')
        if not np.isnan(res.noise_x):
            smoother.set_noise(res.noise_x, res.noise_y)
        if res.min_cutoff is not None:
            smoother.set_min_cutoff(res.min_cutoff)
    smoother.reset()
    eye_state.set_baselines(model.eye_baselines)
    return best[0] if best else None


def _session_meta(cam_w, cam_h, model, val) -> dict:
    meta = {'tela': (SCREEN_W, SCREEN_H), 'camera': (cam_w, cam_h),
            'smoother': SMOOTHER, 'cv_error_px': model.cv_error_px}
    if val is not None:
        meta['validacao'] = {'alvos': val.targets, 'estimados': val.preds,
                             'erro_px': val.error, 'erro_sem_correcao_px': val.raw_error,
                             'ruido_px': (val.noise_x, val.noise_y),
                             'correcao': val.correction.describe()}
    return meta


def _banner():
    print()
    print('  ╔══════════════════════════════════════════════════════╗')
    print('  ║          EyeNav – Navegação por Rastreamento         ║')
    print('  ║          Ocular para Acessibilidade Digital          ║')
    print('  ║          UNIP   |  TC II  |                          ║')
    print('  ╚══════════════════════════════════════════════════════╝')
    print()


def _print_controls():
    print()
    print('  ┌────────────────────────────────────────────────────┐')
    print('  │  SISTEMA ATIVO                                     │')
    print('  │  Clique: feche os dois olhos devagar.              │')
    print('  │   Com zoom (Z): 1ª piscada amplia a região,        │')
    print('  │   olhe o alvo ampliado e pisque de novo.           │')
    print('  │  Na piscada que clica, abra os olhos no:           │')
    print('  │   1º bipe → clique    2º bipe → duplo clique       │')
    print('  │   3º bipe → clique direito    bipe grave → cancela │')
    print('  │  Scroll: olhe a alça (meio da borda direita) até a │')
    print('  │   bola pulsar e pisque devagar para destravar;     │')
    print('  │   olhe a borda de cima/baixo para rolar. Pisque    │')
    print('  │   enquanto rola (bola laranja) para frear/travar.  │')
    print('  │                                                    │')
    print('  │  Teclas na janela de debug:                        │')
    print('  │   Q / ESC → Encerrar      P → Pausar / retomar     │')
    print('  │   R → Recalibrar          F → Refazer validação    │')
    print('  │   Z → Zoom on/off         L → Travar/destravar     │')
    print('  │   D → Dwell click on/off                           │')
    print('  │   B → Blink click on/off  G → Gravar sessão        │')
    print('  │   M → Métricas (CSV)      S → Screenshot do debug  │')
    print('  └────────────────────────────────────────────────────┘')
    print()


if __name__ == '__main__':
    main()
