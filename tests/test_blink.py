import pytest

from desktop import mouse_backend
from interaction.blink_clicker import BlinkClicker, fire, stage_for
from tracking.eye_state import EyeState, OPEN

FPS = 30
SH = 1080
OPEN_LVL = 0.8


class FakeSounds:
    def __init__(self):
        self.played = []

    def play(self, name):
        self.played.append(name)


@pytest.fixture
def clicks(monkeypatch):
    log = []
    for name in ('click', 'double_click', 'right_click'):
        monkeypatch.setattr(mouse_backend, name,
                            lambda x, y, _n=name: log.append((_n, x, y)))
    return log


class Sim:
    """Alimenta EyeState + BlinkClicker frame a frame."""

    def __init__(self, baselines=None):
        self.eyes = EyeState(SH, baselines)
        self.sounds = FakeSounds()
        self.blink = BlinkClicker(self.sounds)
        self.t = 0.0
        self.gaze_y = SH / 2
        self.results = []
        self.blocked = []

    def locate(self, t):
        # Antes de t=10 s o cursor estava em (100, 200); depois, em outro lugar
        return (100, 200) if t < 10 else (999, 999)

    def frames(self, seconds, openness):
        for _ in range(int(round(seconds * FPS))):
            self.t += 1 / FPS
            o = openness if openness is None or isinstance(openness, tuple) \
                else (openness, openness)
            self.blocked.append(self.eyes.update(o, self.gaze_y, self.t))
            r = self.blink.update(self.eyes, self.t, self.locate)
            if r:
                self.results.append(r)
                fire(*r)

    def blink_for(self, seconds, level=0.05):
        self.frames(1 / FPS, 0.5)          # pálpebra descendo
        self.frames(seconds, level)
        self.frames(1 / FPS, 0.5)          # subindo
        self.frames(0.5, OPEN_LVL)


def _warm(sim):
    sim.frames(10.0 - 0.6, OPEN_LVL)       # aprende a abertura normal


def test_stage_thresholds():
    assert stage_for(300) == 0
    assert stage_for(700) == 1
    assert stage_for(1500) == 2
    assert stage_for(2500) == 3
    assert stage_for(5000) == 4


def test_natural_blink_freezes_gaze_but_never_clicks(clicks):
    sim = Sim()
    _warm(sim)
    n = len(sim.blocked)
    sim.blink_for(0.2)
    assert any(sim.blocked[n:])            # olhar congelado durante a piscada
    assert not sim.blocked[-1]             # e liberado depois
    assert clicks == [] and sim.sounds.played == []


@pytest.mark.parametrize('seconds, action, sounds', [
    (0.8, 'click',        ['stage1', 'click']),
    (1.6, 'double_click', ['stage1', 'stage2', 'click']),
    (2.5, 'right_click',  ['stage1', 'stage2', 'stage3', 'click']),
    (4.0, None,           ['stage1', 'stage2', 'stage3', 'cancel']),
])
def test_slow_blink_ladder(clicks, seconds, action, sounds):
    sim = Sim()
    _warm(sim)
    sim.blink_for(seconds)
    if action:
        # Exatamente uma ação, na posição de ANTES da piscada
        assert clicks == [(action, 100, 200)]
    else:
        assert clicks == []
    assert sim.sounds.played == sounds


def test_looking_down_is_not_a_blink(clicks):
    # Calibração: olho mais fechado ao olhar para baixo
    sim = Sim(baselines=[[0.8, 0.8], [0.7, 0.7], [0.45, 0.45]])
    _warm(sim)
    sim.gaze_y = SH - 30
    n = len(sim.blocked)
    sim.frames(3.0, 0.45)
    assert not any(sim.blocked[n + 1:])
    # Piscada lenta olhando para baixo continua funcionando
    sim.blink_for(0.8, level=0.03)
    assert [c[0] for c in clicks] == ['click']


def test_looking_down_without_band_reference_recovers(clicks):
    sim = Sim()
    _warm(sim)
    sim.gaze_y = SH - 30
    sim.frames(3.0, 0.5)                   # 62 % da abertura normal
    assert not sim.blocked[-1]             # nova referência aprendida
    assert clicks == []


def test_wink_does_not_click(clicks):
    sim = Sim()
    _warm(sim)
    sim.frames(1.0, (0.05, OPEN_LVL))      # só um olho fechado
    sim.frames(1.0, OPEN_LVL)
    assert clicks == []


def test_face_lost_during_closure_cancels(clicks):
    sim = Sim()
    _warm(sim)
    sim.frames(0.7, 0.05)
    sim.frames(1.5, None)                  # rosto perdido
    sim.frames(0.5, OPEN_LVL)
    assert clicks == []
    assert sim.eyes.state == OPEN


def test_cancel_flag_on_too_long_closure(clicks):
    sim = Sim()
    _warm(sim)
    flags = []
    sim.frames(4.0, 0.05)
    for _ in range(3):
        sim.t += 1 / FPS
        sim.eyes.update((OPEN_LVL, OPEN_LVL), sim.gaze_y, sim.t)
        sim.blink.update(sim.eyes, sim.t, sim.locate)
        flags.append(sim.blink.cancelled)
    assert flags == [True, False, False]
    assert clicks == []



def _claiming(promise):
    """claim() que devolve `promise` para qualquer instante."""
    seen = []

    def claim(t_ref):
        seen.append(t_ref)
        return promise
    return claim, seen


@pytest.mark.parametrize('promise, sound', [('scroll_unlock', 'scroll_on'),
                                            ('scroll_lock', 'scroll_off'),
                                            ('scroll_brake', 'scroll_off')])
def test_claimed_blink_returns_promise_without_clicking(clicks, promise, sound):
    sim = Sim()
    _warm(sim)
    claim, seen = _claiming(promise)
    results = []
    orig = sim.blink.update
    sim.blink.update = lambda e, t, loc: orig(e, t, loc, claim)
    sim.frames(1 / FPS, 0.5)
    sim.frames(1.6, 0.05)          # passaria do duplo clique sem a promessa
    sim.frames(0.5, OPEN_LVL)
    results = sim.results
    assert results == [(promise, None, None)]
    assert clicks == []
    # Prévia no lugar do 1º bipe; sem 2º/3º bipe; tique ao executar
    assert sim.sounds.played == [sound, 'click']
    # A promessa é consultada uma vez, no instante de antes da piscada
    assert len(seen) == 1 and seen[0] < sim.eyes.gate_since


def test_claimed_blink_can_still_be_cancelled(clicks):
    sim = Sim()
    _warm(sim)
    claim, _ = _claiming('scroll_unlock')
    orig = sim.blink.update
    cancelled = []

    def upd(e, t, loc):
        r = orig(e, t, loc, claim)
        cancelled.append(sim.blink.cancelled)
        return r
    sim.blink.update = upd
    sim.blink_for(4.0)
    assert sim.results == [] and any(cancelled)
    assert sim.sounds.played == ['scroll_on', 'cancel']


def test_natural_blink_does_not_consult_claim(clicks):
    sim = Sim()
    _warm(sim)
    claim, seen = _claiming('scroll_unlock')
    orig = sim.blink.update
    sim.blink.update = lambda e, t, loc: orig(e, t, loc, claim)
    sim.blink_for(0.2)
    assert seen == [] and sim.results == []


def test_aborted_closure_drops_claim(clicks):
    sim = Sim()
    _warm(sim)
    claim, _ = _claiming('scroll_unlock')
    orig = sim.blink.update
    sim.blink.update = lambda e, t, loc: orig(e, t, loc, claim)
    sim.frames(0.8, 0.05)
    sim.frames(1.5, None)          # rosto perdido: fechamento cancelado
    sim.frames(0.5, OPEN_LVL)
    assert sim.blink.armed is None and sim.results == []
    # A próxima piscada, sem promessa, volta a ser clique
    sim.blink.update = orig
    sim.blink_for(0.8)
    assert [c[0] for c in clicks] == ['click']


def test_fire_ignores_promises(clicks):
    fire('scroll_unlock', None, None)
    assert clicks == []
