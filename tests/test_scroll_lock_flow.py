"""
Integração EyeState + BlinkClicker + ScrollLock na mesma ordem do main,
para piscadas na alça e no freio (cenários reproduzidos na revisão).
"""

import pytest

from desktop import mouse_backend
from interaction.blink_clicker import BlinkClicker, fire
from tracking.eye_state import EyeState
from interaction.scroll_lock import ScrollLock

SW, SH, FPS = 1920, 1080, 30
OPEN_LVL = 0.8


@pytest.fixture
def clicks(monkeypatch):
    log = []
    for name in ('click', 'double_click', 'right_click'):
        monkeypatch.setattr(mouse_backend, name,
                            lambda x, y, _n=name: log.append((_n, x, y)))
    return log


class Flow:
    def __init__(self, pos=(1919, 540), moving=False):
        self.eyes = EyeState(SH)
        self.lock = ScrollLock(SW, SH, enabled=True)
        self.blink = BlinkClicker()
        self.pos, self.moving = pos, moving
        self.t = 0.0
        self.results = []

    def frame(self, openness, dt=1 / FPS):
        self.t += dt
        o = (openness, openness)
        blocked = self.eyes.update(o, self.pos[1], self.t)
        if not blocked:
            self.lock.observe(*self.pos, self.t, moving=self.moving,
                              in_band=False, engaged=False)
        else:
            self.lock.pause(self.t, zone_active=self.moving, carry=True)
        r = self.blink.update(self.eyes, self.t, lambda t: self.pos,
                              self.lock.claim)
        if r:
            self.results.append(r)
            fire(*r)

    def run(self, seconds, openness):
        for _ in range(int(round(seconds * FPS))):
            self.frame(openness)


@pytest.mark.parametrize('first_ms, open_ms', [(470, 130), (520, 230), (580, 100)])
def test_retry_blink_keeps_handle_promise(clicks, first_ms, open_ms):
    # Abriu cedo demais (antes do bipe) e tentou de novo logo em seguida
    f = Flow()
    f.run(1.0, OPEN_LVL)                       # aprende a abertura e acende a alça
    f.run(first_ms / 1000, 0.05)
    f.run(open_ms / 1000, OPEN_LVL)
    f.run(0.9, 0.05)
    f.run(0.5, OPEN_LVL)
    assert f.results == [('scroll_unlock', None, None)] and clicks == []


def test_retry_blink_keeps_brake_promise(clicks):
    f = Flow(pos=(960, 1079), moving=True)
    f.lock.unlock(0, 'teste')
    f.run(1.0, OPEN_LVL)
    f.run(0.5, 0.05)
    f.run(0.15, OPEN_LVL)
    f.run(0.9, 0.05)
    f.run(0.5, OPEN_LVL)
    assert f.results == [('scroll_brake', None, None)] and clicks == []


def test_threshold_crossed_on_reopening_frame(clicks):
    # Último frame fechado em 590 ms, reabertura em 633 ms: o 1º limiar só é
    # cruzado no frame da reabertura e a promessa ainda vale
    f = Flow()
    f.run(1.0, OPEN_LVL)
    f.frame(0.05)                              # fecha (closed_since)
    for _ in range(5):
        f.frame(0.05, dt=0.1)                  # +500 ms
    f.frame(0.05, dt=0.09)                     # +590 ms
    f.frame(OPEN_LVL, dt=0.043)                # reabre em +633 ms
    f.run(0.5, OPEN_LVL)
    assert f.results == [('scroll_unlock', None, None)] and clicks == []
