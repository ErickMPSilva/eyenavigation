import pytest

from desktop import mouse_backend
from interaction.edge_scroller import EdgeScroller

SW, SH, FPS = 1920, 1080, 30


@pytest.fixture
def wheel(monkeypatch):
    log = []
    monkeypatch.setattr(mouse_backend, 'scroll',
                        lambda n, x=None, y=None: log.append((n, x, y)))
    return log


def run(sc, seconds, y, t0=0.0, x=900, valid=True):
    t = t0
    for _ in range(int(seconds * FPS)):
        t += 1 / FPS
        if valid:
            sc.update(x, y(t) if callable(y) else y, t)
        else:
            sc.pause(t)
    return t


def test_middle_of_screen_never_scrolls(wheel):
    run(EdgeScroller(SW, SH), 5, SH / 2)
    assert wheel == []


def test_bottom_zone_scrolls_down_on_the_content(wheel):
    sc = EdgeScroller(SW, SH)
    run(sc, 2.0, SH - 0.06 * SH)          # meio da faixa inferior
    total = sum(n for n, _, _ in wheel)
    assert all(n < 0 for n, _, _ in wheel)
    assert -14 <= total <= -5
    # Roda enviada sobre o conteúdo, fora da faixa (não na barra de tarefas)
    for _, x, y in wheel:
        assert y < SH - sc.bottom_px and 0.1 * SW <= x <= 0.9 * SW


def test_activation_delay(wheel):
    sc = EdgeScroller(SW, SH)
    run(sc, 0.4, 10)
    assert wheel == []
    run(sc, 0.3, 10, t0=0.4)
    assert wheel and wheel[0][0] > 0       # topo → para cima


def test_jitter_at_zone_edge_keeps_scrolling(wheel):
    sc = EdgeScroller(SW, SH)
    edge = sc.top_px
    # Oscila ±25 px em torno da borda da faixa (dentro da histerese)
    run(sc, 3.0, lambda t: edge + (25 if int(t * FPS) % 2 else -25))
    assert sum(n for n, _, _ in wheel) >= 5


def test_deeper_is_faster(wheel):
    shallow, deep = EdgeScroller(SW, SH), EdgeScroller(SW, SH)
    run(shallow, 3.0, SH - 0.01 * SH * 11)
    n_shallow = -sum(n for n, _, _ in wheel)
    wheel.clear()
    run(deep, 3.0, SH - 2)
    assert -sum(n for n, _, _ in wheel) > 2 * n_shallow


def test_pause_stops_scroll_then_resumes(wheel):
    sc = EdgeScroller(SW, SH)
    t = run(sc, 1.5, SH - 5)
    before = len(wheel)
    t = run(sc, 1.0, SH - 5, t0=t, valid=False)
    assert len(wheel) == before
    run(sc, 1.0, SH - 5, t0=t)
    assert len(wheel) > before


def test_leaving_zone_stops(wheel):
    sc = EdgeScroller(SW, SH)
    t = run(sc, 1.5, 5)
    assert sc.active_zone == 'top'
    run(sc, 0.2, SH / 2, t0=t)
    assert sc.active_zone is None and sc.park_point is None


def test_continuous_run_is_limited(wheel):
    import config
    sc = EdgeScroller(SW, SH)
    limit = config.SCROLL_MAX_RUN_MS / 1000
    t = run(sc, limit + 2.0, SH - 5)
    n_before = len(wheel)
    t = run(sc, 2.0, SH - 5, t0=t)
    assert len(wheel) == n_before and sc.exhausted       # parou no limite
    assert sc.active_zone is None and sc.park_point is None
    t = run(sc, 0.3, SH / 2, t0=t)                       # sai da faixa
    run(sc, 1.5, SH - 5, t0=t)                           # e volta: rola de novo
    assert len(wheel) > n_before


def test_looking_off_screen_does_not_scroll(wheel):
    sc = EdgeScroller(SW, SH)
    t = 0.0
    for _ in range(int(3 * FPS)):
        t += 1 / FPS
        # Olhando o teclado: y estimado muito abaixo da tela, limitado à borda
        sc.update(900, SH - 1, t, raw=(900, SH * 1.4))
    assert sc.offscreen and not wheel


def test_brief_offscreen_glance_keeps_scrolling(wheel):
    sc = EdgeScroller(SW, SH)
    t = 0.0
    for i in range(int(3 * FPS)):
        t += 1 / FPS
        y = SH * 1.3 if i % 10 == 0 else SH - 5          # picos de 1 frame
        sc.update(900, SH - 5, t, raw=(900, y))
    assert not sc.offscreen and len(wheel) >= 5


def test_park_point_avoids_rectangle(wheel):
    sc = EdgeScroller(SW, SH)
    sc.avoid = [(1180, 580, 1930, 1040)]                 # janela de debug
    run(sc, 1.0, SH - 5, x=1500)
    x, y = sc.park_point
    assert not (1180 <= x <= 1930 and 580 <= y <= 1040)
    assert wheel and all(not (1180 <= wx <= 1930) for _, wx, _ in wheel)


def test_moving_includes_recent_notch(wheel):
    import config
    sc = EdgeScroller(SW, SH)
    t = run(sc, 1.0, SH - 5)
    assert sc.moving(t)
    t = run(sc, 0.2, SH / 2, t0=t)                       # saiu da faixa
    assert sc.active_zone is None
    assert sc.moving(t) == ((t - sc.last_notch_t) * 1000 < config.SCROLL_BRAKE_MS)
    t = run(sc, 1.0, SH / 2, t0=t)
    assert not sc.moving(t)
