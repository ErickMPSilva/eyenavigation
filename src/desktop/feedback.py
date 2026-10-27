"""
Bipes de retorno, gerados como WAV e tocados sem bloquear o loop principal.
"""

import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import wave

from config import SOUND_ENABLED

_TONES = {                 # frequência inicial e final (Hz), duração (ms), volume
    'stage1':          (660,  660,  110, 0.35),
    'stage2':          (880,  880,  110, 0.35),
    'stage3':          (1100, 1100, 110, 0.35),
    'cancel':          (300,  300,  300, 0.35),
    'click':           (1400, 1400,  40, 0.35),
    'scroll_on':       (523,  1047, 180, 0.35),
    'scroll_off':      (1047, 523,  180, 0.35),
    'scroll_auto_off': (880,  440,  220, 0.20),
}
_RATE = 22050


def _write_tone(path: str, freq: float, ms: int, volume: float = 0.35,
                freq_end: float | None = None):
    n = int(_RATE * ms / 1000)
    f1 = freq if freq_end is None else freq_end
    fade = max(1, int(_RATE * 0.008))
    frames = bytearray()
    phase = 0.0
    for i in range(n):
        env = min(1.0, i / fade, (n - 1 - i) / fade)
        phase += 2 * math.pi * (freq + (f1 - freq) * i / max(n - 1, 1)) / _RATE
        v = volume * env * math.sin(phase)
        frames += struct.pack('<h', int(v * 32767))
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(_RATE)
        w.writeframes(bytes(frames))


class Sounds:
    def __init__(self, enabled: bool = SOUND_ENABLED):
        self._files: dict[str, str] = {}
        self._player = None
        if not enabled:
            return
        if sys.platform == 'win32':
            self._player = 'winsound'
        elif sys.platform == 'darwin':
            self._player = shutil.which('afplay')
        else:
            self._player = next((p for p in (shutil.which(c) for c in
                                 ('paplay', 'pw-play', 'aplay')) if p), None)
        if not self._player:
            print('[Sounds] Nenhum player de áudio encontrado — sons desativados.')
            return
        folder = tempfile.mkdtemp(prefix='eyenav_')
        for name, (f0, f1, ms, vol) in _TONES.items():
            path = os.path.join(folder, f'{name}.wav')
            _write_tone(path, f0, ms, vol, f1)
            self._files[name] = path

    def play(self, name: str):
        path = self._files.get(name)
        if not path:
            return
        try:
            if self._player == 'winsound':
                import winsound
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
            else:
                cmd = [self._player, path]
                if self._player.endswith('aplay'):
                    cmd.insert(1, '-q')
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except Exception:
            pass
