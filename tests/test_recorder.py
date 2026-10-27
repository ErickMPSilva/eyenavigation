import numpy as np

from diagnostics.recorder import SessionRecorder


def test_record_and_reload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = SessionRecorder()
    r.add(0.0, None, None, (1, 1), 'aberto', False)        # inativo: ignorado
    r.start({'tela': (1920, 1080)})
    feat = {'eye': np.arange(6.0), 'head': np.arange(4.0), 'openness': (0.8, 0.7)}
    r.add(1.0, feat, (100.0, 200.0), (110, 210), 'aberto', False)
    r.add(1.1, None, None, (110, 210), 'fechado', True)    # sem rosto
    r.event(1.2, 'zoom_click', estimado=[1, 2], real=(3, 4))
    path = r.stop()
    d = np.load(path, allow_pickle=True)
    assert d['t'].tolist() == [1.0, 1.1]
    assert d['eye'][0].tolist() == list(range(6)) and np.isnan(d['eye'][1]).all()
    assert d['raw'][0].tolist() == [100, 200] and d['state'].tolist() == [0, 2]
    meta = d['meta'].item()
    assert meta['tela'] == (1920, 1080) and meta['eventos'][0]['tipo'] == 'zoom_click'
    assert r.stop() is None
