import numpy as np

from tracking.gaze_model import GazeModel
import sim_user


def _error(model, data):
    return float(np.mean([np.hypot(*(np.array(model.predict(f)) - t))
                          for t, f in data]))


def test_head_phase_compensates_head_motion(capsys):
    rng = sim_user.np.random.default_rng(0)
    with_head = GazeModel()
    with_head.train(*sim_user.calibration(rng, head_phase=True))
    eye_only = GazeModel()
    eye_only.train(*sim_user.calibration(rng, head_phase=False))

    moving = sim_user.test_set(rng, head_motion=True)
    still  = sim_user.test_set(rng, head_motion=False)
    e_head, e_eye = _error(with_head, moving), _error(eye_only, moving)
    with capsys.disabled():
        print(f'\n  cabeça em movimento: com fase de cabeça {e_head:.0f} px | '
              f'sem {e_eye:.0f} px')
        print(f'  cabeça parada: {_error(with_head, still):.0f} px | '
              f'{_error(eye_only, still):.0f} px')
    assert with_head._p['use_head']
    assert e_head < 0.5 * e_eye
    assert _error(with_head, still) < 60


def test_save_load_roundtrip(tmp_path):
    rng = np.random.default_rng(1)
    m = GazeModel()
    m.train(*sim_user.calibration(rng), eye_baselines=[[0.8, 0.8]] * 3)
    path = tmp_path / 'calib.pkl'
    m.save(str(path))
    m2 = GazeModel()
    assert m2.load(str(path))
    _, f = sim_user.test_set(rng, n=1)[0]
    assert np.allclose(m.predict(f), m2.predict(f))
    assert m2.eye_baselines == [[0.8, 0.8]] * 3


def test_rejects_old_version(tmp_path):
    import pickle
    path = tmp_path / 'old.pkl'
    with open(path, 'wb') as fh:
        pickle.dump({'version': 2, 'model_x': None}, fh)
    assert not GazeModel().load(str(path))
