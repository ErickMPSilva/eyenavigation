import math

import pytest

import config
from interaction.scroll_lock import ScrollLock

SW, SH, FPS = 1920, 1080, 30
HANDLE = (1915, 540)          # meio da borda direita
MIDDLE = (900, 500)


def feed(lock, seconds, pos, t0, moving=False, in_band=False, engaged=False):
    t = t0
    for _ in range(int(round(seconds * FPS))):
        t += 1 / FPS
        lock.observe(*pos, t, moving=moving, in_band=in_band, engaged=engaged)
    return t


def test_starts_locked_and_handle_needs_fixation():
    lk = ScrollLock(SW, SH, enabled=True)
    assert lk.locked and not lk.allows_scroll
    t = feed(lk, 0.2, HANDLE, 0)
    assert lk.in_handle and not lk.lit                 # < 300 ms: ainda não
    assert lk.claim(t) is None
    t = feed(lk, 0.2, HANDLE, t)
    assert lk.lit and lk.claim(t) == 'scroll_unlock'
    # A bola só pulsa quando uma piscada começando agora já valeria
    # (a piscada consulta a promessa de BLINK_POS_LOOKBACK_MS atrás)
    assert lk.view is None
    t = feed(lk, config.BLINK_POS_LOOKBACK_MS / 1000 + 0.05, HANDLE, t)
    assert lk.view == 'handle'
    assert lk.claim(t - config.BLINK_POS_LOOKBACK_MS / 1000) == 'scroll_unlock'


def test_passing_saccade_does_not_light_handle():
    lk = ScrollLock(SW, SH, enabled=True)
    t = feed(lk, 0.1, HANDLE, 0)
    t = feed(lk, 0.5, MIDDLE, t)
    assert not lk.lit and lk.claim(t) is None


def test_handle_region_and_exit_hysteresis():
    lk = ScrollLock(SW, SH, enabled=True)
    (x0, y0, x1, y1), = lk.regions
    assert x1 == SW and SW - x0 == config.SCROLL_HANDLE_WIDTH_PX
    t = feed(lk, 0.5, (SW - 1, 540), 0)
    assert lk.lit
    # 20 px fora da região (dentro da margem de 30): continua acesa
    t = feed(lk, 0.2, (x0 - 20, 540), t)
    assert lk.lit
    t = feed(lk, 0.1, (x0 - 60, 540), t)
    assert not lk.in_handle and not lk.lit
    # Acima/abaixo da região (perto das faixas de scroll): fora
    feed(lk, 0.5, (SW - 1, y0 - 100), t)
    assert not lk.in_handle


def test_fit_to_error_bounds():
    lk = ScrollLock(SW, SH, enabled=True)
    lk.fit_to_error(20)
    assert lk.width == config.SCROLL_HANDLE_WIDTH_PX
    lk.fit_to_error(90)
    assert lk.width == 90 and lk.half_h == pytest.approx(0.2083 * SH, rel=0.01)
    lk.fit_to_error(500)
    assert lk.width == config.SCROLL_HANDLE_MAX_WIDTH_PX
    assert lk.half_h == config.SCROLL_HANDLE_MAX_HALF_H * SH
    lk.fit_to_error(float('nan'))                     # ignorado
    assert lk.width == config.SCROLL_HANDLE_MAX_WIDTH_PX
    # Sempre sobra espaço até as faixas de scroll
    (_, y0, _, y1), = lk.regions
    assert y0 > config.SCROLL_ZONE_TOP * SH + 100
    assert y1 < SH - config.SCROLL_ZONE_BOTTOM * SH - 100


def test_promises_when_unlocked():
    lk = ScrollLock(SW, SH, enabled=True)
    assert lk.unlock(0, 'teste') and not lk.unlock(0, 'teste')   # idempotente
    t = feed(lk, 0.5, MIDDLE, 0)
    assert lk.claim(t) is None and lk.view == 'unlocked'
    t = feed(lk, 0.3, (900, 1070), t, moving=True)
    assert lk.claim(t) == 'scroll_brake' and lk.view == 'scroll'
    t = feed(lk, 0.5, HANDLE, t)
    assert lk.claim(t) == 'scroll_lock'


def test_claim_uses_history_before_blink_and_expires():
    lk = ScrollLock(SW, SH, enabled=True)
    t = feed(lk, 0.5, HANDLE, 0)
    t_ref = t - 0.1
    assert lk.claim(t_ref) == 'scroll_unlock'
    assert lk.claim(t + 2.0) is None                  # promessa velha demais
    # Depois de destravar, a promessa antiga ("quero destravado") é inofensiva
    # (trocas idempotentes); as novas observações já prometem travar
    lk.unlock(t, 'alca')
    assert not lk.unlock(t, 'alca')
    t = feed(lk, 0.1, HANDLE, t)
    assert lk.claim(t) == 'scroll_lock'


def test_idle_lock_only_without_activity():
    lk = ScrollLock(SW, SH, enabled=True)
    lk.unlock(0, 'teste')
    idle = config.SCROLL_IDLE_LOCK_MS / 1000
    t = feed(lk, idle - 1, MIDDLE, 0)
    assert lk.tick(t, True) is None
    # Olhar numa faixa (ativando/rolando) conta como atividade
    t = feed(lk, 3.0, (900, 1070), t, engaged=True)
    assert lk.tick(t, True) is None
    t = feed(lk, idle + 0.1, MIDDLE, t)
    assert lk.tick(t, True) == 'ocioso'


def test_blink_during_scroll_counts_as_activity():
    lk = ScrollLock(SW, SH, enabled=True)
    lk.unlock(0, 'teste')
    t = 0.0
    for _ in range(int((config.SCROLL_IDLE_LOCK_MS / 1000 + 2) * FPS)):
        t += 1 / FPS
        lk.pause(t, zone_active=True)
    assert lk.tick(t, True) is None


def test_face_lost_locks():
    lk = ScrollLock(SW, SH, enabled=True)
    lk.unlock(0, 'teste')
    lost = config.SCROLL_LOCK_FACE_LOST_MS / 1000
    assert lk.tick(1.0, False) is None
    assert lk.tick(1.0 + lost / 2, False) is None
    assert lk.tick(1.0 + lost / 2 + 0.1, True) is None   # voltou: zera
    assert lk.tick(5.0, False) is None
    assert lk.tick(5.0 + lost + 0.01, False) == 'rosto'


def test_dwell_toggle_without_blink_and_rearm():
    lk = ScrollLock(SW, SH, enabled=True)
    dwell = config.SCROLL_HANDLE_DWELL_MS / 1000
    t = feed(lk, dwell - 0.2, HANDLE, 0)
    assert lk.dwell_toggle(t, blink_on=False) is None
    t = feed(lk, 0.3, HANDLE, t)
    assert lk.dwell_toggle(t, blink_on=False) == 'scroll_unlock'
    lk.unlock(t, 'dwell')
    t = feed(lk, dwell + 0.5, HANDLE, t)
    assert lk.dwell_toggle(t, blink_on=False) is None    # precisa sair e voltar
    t = feed(lk, 0.2, MIDDLE, t)
    t = feed(lk, dwell + 0.4, HANDLE, t)
    assert lk.dwell_toggle(t, blink_on=False) == 'scroll_lock'


def test_hint_rate_limited():
    lk = ScrollLock(SW, SH, enabled=True)
    band = (900, 1070)
    hint_s = config.SCROLL_HINT_MS / 1000
    t = feed(lk, hint_s - 0.2, band, 0, in_band=True)
    assert not lk.hint_active(t)
    t = feed(lk, 0.3, band, t, in_band=True)
    assert lk.hint_active(t)
    t = feed(lk, 3.0, band, t, in_band=True)
    assert not lk.hint_active(t)                         # uma vez por permanência
    t = feed(lk, 0.5, MIDDLE, t)
    t = feed(lk, hint_s + 0.2, band, t, in_band=True)
    assert not lk.hint_active(t)                         # e no máximo a cada 30 s
    t = feed(lk, config.SCROLL_HINT_EVERY_S, MIDDLE, t)
    t = feed(lk, hint_s + 0.1, band, t, in_band=True)
    assert lk.hint_active(t)


def test_disabled_lock_always_allows_scroll():
    lk = ScrollLock(SW, SH, enabled=False)
    assert lk.allows_scroll and not lk.locked and lk.regions == []
    t = feed(lk, 1.0, HANDLE, 0)
    assert lk.claim(t) is None and lk.view is None
    assert not lk.lock(t, 'x') and lk.tick(t + 100, False) is None


def test_left_and_both_sides(monkeypatch):
    monkeypatch.setattr(config, 'SCROLL_HANDLE_SIDE', 'both')
    lk = ScrollLock(SW, SH, enabled=True)
    assert len(lk.regions) == 2
    feed(lk, 0.5, (0, 540), 0)
    assert lk.lit


def test_pulse_phase():
    lk = ScrollLock(SW, SH, enabled=True)
    phases = {lk.pulse_on(i / 100) for i in range(100)}
    assert phases == {True, False}
    assert math.isclose(sum(lk.pulse_on(i / 1000) for i in range(1000)) / 1000,
                        0.5, abs_tol=0.01)


def test_dwell_does_not_inherit_time_with_blink_on():
    # Blink ligado olhando a alça; o cuidador desliga o blink (tecla B):
    # o dwell começa do zero, não destrava no frame seguinte
    lk = ScrollLock(SW, SH, enabled=True)
    dwell = config.SCROLL_HANDLE_DWELL_MS / 1000
    t = 0.0
    for _ in range(int((dwell + 1) * FPS)):
        t += 1 / FPS
        lk.observe(*HANDLE, t, moving=False, in_band=False, engaged=False)
        assert lk.dwell_toggle(t, blink_on=True) is None
    t = feed(lk, 1 / FPS, HANDLE, t)
    assert lk.dwell_toggle(t, blink_on=False) is None
    t = feed(lk, dwell, HANDLE, t)
    assert lk.dwell_toggle(t, blink_on=False) == 'scroll_unlock'


def test_dwell_restarts_after_gap():
    # 1,5 s na alça, pausa (sem observações), volta olhando a alça
    lk = ScrollLock(SW, SH, enabled=True)
    dwell = config.SCROLL_HANDLE_DWELL_MS / 1000
    t = feed(lk, dwell - 0.5, HANDLE, 0)
    t = feed(lk, 1 / FPS, HANDLE, t + 10.0)
    assert lk.dwell_toggle(t, blink_on=False) is None
    t = feed(lk, dwell + 0.05, HANDLE, t)
    assert lk.dwell_toggle(t, blink_on=False) == 'scroll_unlock'


def test_looking_at_handle_counts_as_activity():
    # Destravado, lendo o meio da tela quase até a trava por ociosidade,
    # e então olhando a alça para travar: a ociosidade não pode disparar
    lk = ScrollLock(SW, SH, enabled=True)
    lk.unlock(0, 'teste')
    idle = config.SCROLL_IDLE_LOCK_MS / 1000
    t = feed(lk, idle - 1.0, MIDDLE, 0)
    for _ in range(int(3 * FPS)):
        t += 1 / FPS
        lk.observe(*HANDLE, t, moving=False, in_band=False, engaged=False)
        assert lk.tick(t, True) is None


def test_pause_carries_promise_through_blinks():
    lk = ScrollLock(SW, SH, enabled=True)
    t = feed(lk, 0.5, HANDLE, 0)
    for _ in range(int(1.0 * FPS)):              # 1 s de olhar bloqueado
        t += 1 / FPS
        lk.pause(t, zone_active=False, carry=True)
    assert lk.claim(t) == 'scroll_unlock'
    for _ in range(int(1.0 * FPS)):              # sem rosto: não repete
        t += 1 / FPS
        lk.pause(t, zone_active=False, carry=False)
    assert lk.claim(t) is None
