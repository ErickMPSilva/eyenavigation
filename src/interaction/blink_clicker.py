"""
Piscada lenta → clique. O tempo de olhos fechados escolhe a ação (clique,
duplo, direito, cancelar), com um bipe a cada limiar. Com o olhar na alça
do scroll, ou a página rolando, a piscada vira a promessa da trava.
"""

from desktop import mouse_backend
from config import (BLINK_CLICK_MS, BLINK_DOUBLE_MS, BLINK_RIGHT_MS,
                    BLINK_CANCEL_MS, BLINK_COOLDOWN_MS, BLINK_POS_LOOKBACK_MS)

_STAGES  = (BLINK_CLICK_MS, BLINK_DOUBLE_MS, BLINK_RIGHT_MS, BLINK_CANCEL_MS)
_ACTIONS = {1: 'single', 2: 'double', 3: 'right'}
_SOUNDS  = {1: 'stage1', 2: 'stage2', 3: 'stage3', 4: 'cancel'}
_LABELS  = {'single': 'CLIQUE SIMPLES', 'double': 'DUPLO CLIQUE',
            'right': 'CLIQUE DIREITO'}
_FIRE    = {'single': 'click', 'double': 'double_click', 'right': 'right_click'}


def stage_for(closed_ms: float) -> int:
    """0 = nenhum limiar atingido; 1–3 = ação; 4 = cancelado."""
    return sum(closed_ms >= s for s in _STAGES)


def fire(action: str, x: int, y: int):
    if action not in _FIRE:
        return
    getattr(mouse_backend, _FIRE[action])(int(x), int(y))
    print(f'[BlinkClicker] {_LABELS[action]} → ({int(x)}, {int(y)})  '
          f'[{mouse_backend.BACKEND}]')


class BlinkClicker:
    def __init__(self, sounds=None):
        self._sounds = sounds
        self.cancelled = False
        self.reset()

    def update(self, eyes, t: float, locate, claim=None):
        self.cancelled = False
        t_ref = None if eyes.gate_since is None else \
            eyes.gate_since - BLINK_POS_LOOKBACK_MS / 1000
        if eyes.closed:
            st = stage_for((t - eyes.closed_since) * 1000)
            if st >= 1 and not self._claim_checked:
                self._claim_checked = True
                self._claim = claim(t_ref) if claim and t_ref is not None else None
            if st != self.stage:
                self.stage = st
                sound = self._sound(st)
                if self._sounds and sound:
                    self._sounds.play(sound)
            return None

        claimed, checked = self._claim, self._claim_checked
        self._claim, self._claim_checked = None, False
        self.stage = 0
        if not eyes.just_reopened:
            return None

        stage = stage_for(eyes.last_closed_ms)
        if not checked and 1 <= stage <= max(_ACTIONS):
            # O 1º limiar foi cruzado só no frame da reabertura
            claimed = claim(t_ref) if claim and t_ref is not None else None
        self.cancelled = stage > max(_ACTIONS)
        action = _ACTIONS.get(stage)
        if action is None:
            return None
        if (t - self._t_last) * 1000 < BLINK_COOLDOWN_MS:
            return None

        if claimed:
            self._t_last = t
            if self._sounds:
                self._sounds.play('click')
            return claimed, None, None

        pos = locate(t_ref) if t_ref is not None else None
        if pos is None:
            return None
        self._t_last = t
        if self._sounds:
            self._sounds.play('click')
        return action, int(pos[0]), int(pos[1])

    def _sound(self, stage: int) -> str | None:
        if self._claim:
            if stage == 1:
                return 'scroll_on' if self._claim == 'scroll_unlock' else 'scroll_off'
            return 'cancel' if stage == 4 else None
        return _SOUNDS.get(stage)

    @property
    def armed(self) -> str | None:
        """O que será executado se os olhos abrirem agora (ação ou promessa)."""
        if self._claim and 1 <= self.stage <= max(_ACTIONS):
            return self._claim
        return _ACTIONS.get(self.stage)

    def reset(self):
        self._claim = None
        self._claim_checked = False
        self.stage   = 0
        self._t_last = -1e9
