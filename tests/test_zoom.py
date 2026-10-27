import numpy as np
import pytest

cv2 = pytest.importorskip('cv2')

from interaction.zoom import ZoomView

SW, SH = 1920, 1080


@pytest.fixture(autouse=True)
def no_gui(monkeypatch):
    for fn in ('namedWindow', 'moveWindow', 'setWindowProperty', 'imshow',
               'destroyWindow', 'waitKey'):
        monkeypatch.setattr(cv2, fn, lambda *a, **k: -1)


def _shot():
    img = np.zeros((SH, SW, 3), np.uint8)
    img[500:520, 900:960] = 255           # "link" branco
    return img


def test_maps_zoomed_gaze_back_to_screen():
    z = ZoomView(SW, SH, factor=2.5, grab=_shot)
    assert z.open(930, 510, t=0)
    # O alvo real (930, 510) aparece em from_screen(...) na imagem ampliada
    zx, zy = z.from_screen(930, 510)
    assert z.to_screen(zx, zy) == (930, 510)
    # Erro de 100 px no olhar sobre o zoom vira 40 px na tela
    x, y = z.to_screen(zx + 100, zy)
    assert x - 930 == 40


def test_region_is_clamped_at_screen_edges():
    z = ZoomView(SW, SH, factor=2.5, grab=_shot)
    z.open(5, 5, t=0)
    assert z.to_screen(0, 0) == (0, 0)
    z.open(SW - 1, SH - 1, t=0)
    assert z.to_screen(SW, SH) == (SW, SH)


def test_unavailable_without_grabber_and_timeout():
    def broken():
        raise RuntimeError('sem tela')
    z = ZoomView(SW, SH, grab=broken)
    assert z.available and not z.open(100, 100, t=0)
    assert not z.available
    z2 = ZoomView(SW, SH, grab=_shot)
    z2.open(500, 500, t=0)
    assert not z2.expired(5) and z2.expired(60)
    z2.close()
    assert not z2.active
