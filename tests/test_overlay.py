import pytest

from desktop import gaze_overlay
from desktop.gaze_overlay import EdgeBar


class FakeWin:
    created, closed = [], []

    def __init__(self, w, h, round_, palette, origin=(0, 0)):
        self.h = h
        FakeWin.created.append(self)

    def move(self, x, y):
        pass

    def set_color(self, s):
        pass

    def show(self):
        pass

    def hide(self):
        pass

    def raise_(self):
        pass

    def close(self):
        FakeWin.closed.append(self)


@pytest.fixture
def fake_x11(monkeypatch):
    FakeWin.created, FakeWin.closed = [], []
    monkeypatch.setattr(gaze_overlay, '_x11_available', lambda: True)
    monkeypatch.setattr(gaze_overlay, 'SCROLL_HANDLE_BAR', True)
    monkeypatch.setattr(gaze_overlay, '_ShapedWindow', FakeWin)


REGIONS = [(1860, 324, 1920, 756), (0, 324, 60, 756)]


def test_edge_bar_survives_x11_failure(fake_x11, monkeypatch):
    def broken(*a, **k):
        raise RuntimeError('XOpenDisplay falhou')
    monkeypatch.setattr(gaze_overlay, '_ShapedWindow', broken)
    bar = EdgeBar(1920, REGIONS)
    bar.set_regions(REGIONS)                   # após R/F: não pode derrubar o programa
    bar.set_state('locked', 0.0)
    bar.show()
    bar.hide()
    assert bar._wins == []


def test_edge_bar_partial_failure_closes_created_windows(fake_x11, monkeypatch):
    calls = []

    def second_fails(*a, **k):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('SHAPE indisponível')
        return FakeWin(*a, **k)
    monkeypatch.setattr(gaze_overlay, '_ShapedWindow', second_fails)
    bar = EdgeBar(1920, REGIONS)
    assert bar._wins == [] and FakeWin.closed == FakeWin.created


def test_set_regions_replaces_windows(fake_x11):
    bar = EdgeBar(1920, REGIONS[:1])
    first = list(bar._wins)
    bar.set_regions([(1830, 315, 1920, 765)])
    assert FakeWin.closed == first
    assert [w.h for w in bar._wins] == [450]


def test_no_x11_outside_linux(monkeypatch):
    monkeypatch.setenv('DISPLAY', ':0')
    monkeypatch.delenv('WAYLAND_DISPLAY', raising=False)
    monkeypatch.setattr(gaze_overlay.sys, 'platform', 'darwin')
    assert not gaze_overlay._x11_available()
