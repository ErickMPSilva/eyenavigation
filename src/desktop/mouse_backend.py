"""
Controle do mouse (ydotool, XTest, xdotool ou pynput). Todas as ações são
executadas em ordem, numa única thread.
"""

import ctypes
import ctypes.util
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import deque


_SESSION = os.environ.get('XDG_SESSION_TYPE', '').lower() or 'desconhecida'
_WAYLAND = bool(os.environ.get('WAYLAND_DISPLAY'))
_X11     = bool(os.environ.get('DISPLAY')) and sys.platform.startswith('linux')


class _XTest:
    def __init__(self):
        X = ctypes.CDLL(ctypes.util.find_library('X11') or 'libX11.so.6')
        T = ctypes.CDLL(ctypes.util.find_library('Xtst') or 'libXtst.so.6')
        # Necessário antes de qualquer outra chamada Xlib quando há várias
        # threads (o overlay usa outra conexão na thread principal)
        X.XInitThreads()
        X.XOpenDisplay.restype   = ctypes.c_void_p
        X.XOpenDisplay.argtypes  = [ctypes.c_char_p]
        X.XFlush.argtypes        = [ctypes.c_void_p]
        X.XSync.argtypes         = [ctypes.c_void_p, ctypes.c_int]
        X.XCloseDisplay.argtypes = [ctypes.c_void_p]
        T.XTestQueryExtension.argtypes = [ctypes.c_void_p] + \
            [ctypes.POINTER(ctypes.c_int)] * 4
        T.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int,
                                           ctypes.c_ulong]
        T.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                                           ctypes.c_int, ctypes.c_ulong]
        self.X, self.T = X, T
        dpy = self._connect()
        X.XCloseDisplay(dpy)
        self.dpy = None

    def _connect(self):
        dpy = self.X.XOpenDisplay(None)
        if not dpy:
            raise RuntimeError('XOpenDisplay falhou')
        a, b, c, d = (ctypes.c_int() for _ in range(4))
        if not self.T.XTestQueryExtension(dpy, ctypes.byref(a), ctypes.byref(b),
                                          ctypes.byref(c), ctypes.byref(d)):
            self.X.XCloseDisplay(dpy)
            raise RuntimeError('extensão XTest indisponível')
        return dpy

    def open(self):
        self.dpy = self._connect()

    def move(self, x, y):
        self.T.XTestFakeMotionEvent(self.dpy, -1, x, y, 0)
        self.X.XFlush(self.dpy)

    def _press(self, button):
        self.T.XTestFakeButtonEvent(self.dpy, button, 1, 0)
        self.T.XTestFakeButtonEvent(self.dpy, button, 0, 0)
        self.X.XFlush(self.dpy)

    def click(self, x, y, button, count):
        self.move(x, y)
        self.X.XSync(self.dpy, 0)
        time.sleep(0.02)
        b = 1 if button == 'left' else 3
        for i in range(count):
            if i:
                time.sleep(0.08)
            self._press(b)

    def scroll(self, clicks, x, y):
        if x is not None:
            self.move(x, y)
            self.X.XSync(self.dpy, 0)
        b = 4 if clicks > 0 else 5           # 4 = roda para cima, 5 = para baixo
        for i in range(abs(clicks)):
            if i:
                time.sleep(0.01)
            self._press(b)


def _run(cmd: list[str]):
    try:
        subprocess.run(cmd, timeout=1, capture_output=True)
    except Exception as e:
        print(f'[MouseBackend] Erro ao executar {cmd[0]}: {e}')


class _Xdotool:
    def open(self):
        pass

    def move(self, x, y):
        _run(['xdotool', 'mousemove', str(x), str(y)])

    def click(self, x, y, button, count):
        # Sem '--sync': ele espera o cursor se MOVER e trava quando o
        # cursor já está no destino (caso comum: o cursor segue o olhar)
        self.move(x, y)
        time.sleep(0.03)
        _run(['xdotool', 'click', '--clearmodifiers', '--repeat', str(count),
              '--delay', '80', '1' if button == 'left' else '3'])

    def scroll(self, clicks, x, y):
        if x is not None:
            self.move(x, y)
        _run(['xdotool', 'click', '--repeat', str(abs(clicks)), '--delay', '10',
              '4' if clicks > 0 else '5'])


class _Ydotool:
    def open(self):
        pass

    def move(self, x, y):
        _run(['ydotool', 'mousemove', '--absolute', '-x', str(x), '-y', str(y)])

    def click(self, x, y, button, count):
        # Sintaxe do ydotool 1.x: 0xC0 = clique esquerdo (down+up),
        # 0xC1 = clique direito (down+up)
        self.move(x, y)
        time.sleep(0.05)
        code = '0xC0' if button == 'left' else '0xC1'
        for i in range(count):
            if i:
                time.sleep(0.08)
            _run(['ydotool', 'click', code])

    def scroll(self, clicks, x, y):
        if x is not None:
            self.move(x, y)
        _run(['ydotool', 'mousemove', '--wheel', '-x', '0', '-y', str(clicks)])


class _Pynput:
    def __init__(self):
        from pynput.mouse import Controller, Button
        self._m, self._B = Controller(), Button

    def open(self):
        pass

    def move(self, x, y):
        self._m.position = (x, y)

    def click(self, x, y, button, count):
        self._m.position = (x, y)
        time.sleep(0.02)
        self._m.click(self._B.left if button == 'left' else self._B.right, count)

    def scroll(self, clicks, x, y):
        if x is not None:
            self._m.position = (x, y)
            time.sleep(0.01)
        self._m.scroll(0, clicks)


def _choose():
    if _WAYLAND and shutil.which('ydotool'):
        return 'ydotool', _Ydotool()
    if _X11:
        try:
            return 'xtest', _XTest()
        except Exception as e:
            print(f'[MouseBackend] XTest indisponível ({e}).')
        if shutil.which('xdotool'):
            return 'xdotool', _Xdotool()
    try:
        return 'pynput', _Pynput()
    except Exception:
        return 'none', None


BACKEND, _impl = _choose()

print(f'[MouseBackend] Sessão: {_SESSION} '
      f'({"Wayland" if _WAYLAND else "X11/outra"}) | Backend: {BACKEND}')
if BACKEND == 'none':
    print('[MouseBackend] AVISO: nenhum backend de mouse disponível!')
    print('  X11:     sudo apt install libxtst6   (ou xdotool)')
    print('  Wayland: sudo apt install ydotool  (e inicie o ydotoold)')
    print('  Qualquer SO: pip install pynput')


def available() -> bool:
    return BACKEND != 'none'


class _Worker(threading.Thread):
    def __init__(self, impl):
        super().__init__(daemon=True, name='mouse-backend')
        self._impl  = impl
        self._cond  = threading.Condition()
        self._queue: deque = deque()
        self._move  = None
        self._error_shown = set()

    def post(self, cmd: tuple):
        if not self.is_alive():
            return
        with self._cond:
            self._queue.append(cmd)
            self._cond.notify()

    def post_move(self, x: int, y: int):
        if not self.is_alive():
            return
        with self._cond:
            self._move = (x, y)
            self._cond.notify()

    def run(self):
        try:
            self._impl.open()
        except Exception as e:
            print(f'[MouseBackend] Falha ao iniciar {BACKEND}: {e}')
            return
        while True:
            with self._cond:
                self._cond.wait_for(lambda: self._queue or self._move)
                if self._queue:
                    cmd = self._queue.popleft()
                else:
                    cmd, self._move = ('move',) + self._move, None
            if cmd[0] == 'quit':
                return
            try:
                getattr(self._impl, cmd[0])(*cmd[1:])
            except Exception as e:
                if cmd[0] not in self._error_shown:
                    self._error_shown.add(cmd[0])
                    print(f'[MouseBackend] Erro em {cmd[0]}: {e}')


_worker: _Worker | None = None
_origin = (0, 0)


def _get_worker() -> _Worker | None:
    global _worker
    if _worker is None and available():
        _worker = _Worker(_impl)
        _worker.start()
    return _worker


def set_origin(x: int, y: int):
    global _origin
    _origin = (int(x), int(y))


def _abs(x, y) -> tuple[int, int]:
    return int(x) + _origin[0], int(y) + _origin[1]


def move(x: int, y: int):
    w = _get_worker()
    if w:
        w.post_move(*_abs(x, y))


def click(x: int, y: int):
    w = _get_worker()
    if w:
        w.post(('click', *_abs(x, y), 'left', 1))


def double_click(x: int, y: int):
    w = _get_worker()
    if w:
        w.post(('click', *_abs(x, y), 'left', 2))


def right_click(x: int, y: int):
    w = _get_worker()
    if w:
        w.post(('click', *_abs(x, y), 'right', 1))


def scroll(clicks: int, x: int | None = None, y: int | None = None):
    """Rola a página. clicks > 0 = para cima; clicks < 0 = para baixo."""
    w = _get_worker()
    if w and clicks:
        px, py = _abs(x, y) if x is not None else (None, None)
        w.post(('scroll', int(clicks), px, py))


def shutdown():
    if _worker is not None:
        _worker.post(('quit',))
        _worker.join(timeout=1.0)
