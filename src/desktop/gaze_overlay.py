"""
Janelas X11 transparentes a cliques: a bola que segue o olhar (cor por
estado) e a barra que marca a alça do scroll.
"""

import ctypes
import ctypes.util
import os
import sys

from config import (GAZE_DOT_ENABLED, GAZE_DOT_RADIUS, GAZE_DOT_COLOR,
                    GAZE_DOT_UNLOCKED_COLOR, GAZE_DOT_HANDLE_COLOR,
                    SCROLL_HANDLE_BAR, SCROLL_HANDLE_BAR_PX)

_Window  = ctypes.c_ulong
_Pixmap  = ctypes.c_ulong
_GC      = ctypes.c_void_p
_Display = ctypes.c_void_p

_CW_BACK_PIXEL        = 1 << 1
_CW_BORDER_PIXEL      = 1 << 3
_CW_OVERRIDE_REDIRECT = 1 << 9
_INPUT_OUTPUT         = 1
_SHAPE_SET            = 0
_SHAPE_BOUNDING       = 0
_SHAPE_INPUT          = 2
_UNSORTED             = 0


class _XSetWindowAttributes(ctypes.Structure):
    _fields_ = [
        ('background_pixmap', ctypes.c_ulong),
        ('background_pixel',  ctypes.c_ulong),
        ('border_pixmap',     ctypes.c_ulong),
        ('border_pixel',      ctypes.c_ulong),
        ('bit_gravity',       ctypes.c_int),
        ('win_gravity',       ctypes.c_int),
        ('backing_store',     ctypes.c_int),
        ('backing_planes',    ctypes.c_ulong),
        ('backing_pixel',     ctypes.c_ulong),
        ('save_under',        ctypes.c_int),
        ('event_mask',        ctypes.c_long),
        ('do_not_propagate_mask', ctypes.c_long),
        ('override_redirect', ctypes.c_int),
        ('colormap',          ctypes.c_ulong),
        ('cursor',            ctypes.c_ulong),
    ]


class _XColor(ctypes.Structure):
    _fields_ = [('pixel', ctypes.c_ulong),
                ('red',   ctypes.c_ushort),
                ('green', ctypes.c_ushort),
                ('blue',  ctypes.c_ushort),
                ('flags', ctypes.c_char),
                ('pad',   ctypes.c_char)]


def _load_libs():
    x11  = ctypes.util.find_library('X11')  or 'libX11.so.6'
    xext = ctypes.util.find_library('Xext') or 'libXext.so.6'
    X  = ctypes.CDLL(x11)
    Xe = ctypes.CDLL(xext)

    X.XOpenDisplay.restype      = _Display
    X.XOpenDisplay.argtypes     = [ctypes.c_char_p]
    X.XDefaultScreen.argtypes   = [_Display]
    X.XRootWindow.restype       = _Window
    X.XRootWindow.argtypes      = [_Display, ctypes.c_int]
    X.XDefaultColormap.restype  = ctypes.c_ulong
    X.XDefaultColormap.argtypes = [_Display, ctypes.c_int]
    X.XAllocColor.argtypes      = [_Display, ctypes.c_ulong,
                                   ctypes.POINTER(_XColor)]
    X.XCreateWindow.restype     = _Window
    X.XCreateWindow.argtypes    = [_Display, _Window, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_uint, ctypes.c_uint, ctypes.c_uint,
                                   ctypes.c_int, ctypes.c_uint, ctypes.c_void_p,
                                   ctypes.c_ulong,
                                   ctypes.POINTER(_XSetWindowAttributes)]
    X.XCreatePixmap.restype     = _Pixmap
    X.XCreatePixmap.argtypes    = [_Display, _Window, ctypes.c_uint,
                                   ctypes.c_uint, ctypes.c_uint]
    X.XCreateGC.restype         = _GC
    X.XCreateGC.argtypes        = [_Display, ctypes.c_ulong, ctypes.c_ulong,
                                   ctypes.c_void_p]
    X.XSetForeground.argtypes   = [_Display, _GC, ctypes.c_ulong]
    X.XFillRectangle.argtypes   = [_Display, ctypes.c_ulong, _GC, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
    X.XFillArc.argtypes         = [_Display, ctypes.c_ulong, _GC, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                                   ctypes.c_int, ctypes.c_int]
    X.XFreeGC.argtypes          = [_Display, _GC]
    X.XFreePixmap.argtypes      = [_Display, _Pixmap]
    for fn in ('XMapRaised', 'XUnmapWindow', 'XRaiseWindow', 'XDestroyWindow',
               'XClearWindow'):
        getattr(X, fn).argtypes = [_Display, _Window]
    X.XSetWindowBackground.argtypes = [_Display, _Window, ctypes.c_ulong]
    X.XMoveWindow.argtypes      = [_Display, _Window, ctypes.c_int, ctypes.c_int]
    X.XFlush.argtypes           = [_Display]
    X.XCloseDisplay.argtypes    = [_Display]

    Xe.XShapeQueryExtension.argtypes = [_Display, ctypes.POINTER(ctypes.c_int),
                                        ctypes.POINTER(ctypes.c_int)]
    Xe.XShapeCombineMask.argtypes = [_Display, _Window, ctypes.c_int,
                                     ctypes.c_int, ctypes.c_int, _Pixmap,
                                     ctypes.c_int]
    Xe.XShapeCombineRectangles.argtypes = [_Display, _Window, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int,
                                           ctypes.c_void_p, ctypes.c_int,
                                           ctypes.c_int, ctypes.c_int]
    return X, Xe


_DWELL_STEPS = 5


def _palette(base: tuple) -> dict:
    green = (0, 220, 0)
    pal = {'normal': base, 'click': (0, 255, 0), 'closed': (255, 220, 0),
           'scroll': (255, 150, 0), 'paused': (128, 128, 128),
           'zoom': (0, 200, 255), 'unlocked': GAZE_DOT_UNLOCKED_COLOR,
           'handle': GAZE_DOT_HANDLE_COLOR, 'locked': (110, 110, 110)}
    for i in range(1, _DWELL_STEPS + 1):
        f = i / (_DWELL_STEPS + 1)
        pal[f'dwell{i}'] = tuple(int(b + (g - b) * f) for b, g in zip(base, green))
    return pal


def dwell_state(progress: float) -> str:
    i = int(progress * (_DWELL_STEPS + 1))
    return 'normal' if i <= 0 else f'dwell{min(i, _DWELL_STEPS)}'


def _x11_available() -> bool:
    return (sys.platform.startswith('linux') and bool(os.environ.get('DISPLAY'))
            and not os.environ.get('WAYLAND_DISPLAY'))


class _ShapedWindow:
    def __init__(self, w: int, h: int, round_: bool, palette: dict,
                 origin: tuple = (0, 0)):
        self.w, self.h = int(w), int(h)
        self.origin = origin
        self.visible = False
        self.state = None
        X, Xe = _load_libs()
        self.X = X
        dpy = X.XOpenDisplay(None)
        if not dpy:
            raise RuntimeError('XOpenDisplay falhou')
        self.dpy = dpy
        try:
            self._create(Xe, round_, palette)
        except Exception:
            X.XCloseDisplay(dpy)
            raise

    def _create(self, Xe, round_: bool, palette: dict):
        X, dpy = self.X, self.dpy
        ev, er = ctypes.c_int(), ctypes.c_int()
        if not Xe.XShapeQueryExtension(dpy, ctypes.byref(ev), ctypes.byref(er)):
            raise RuntimeError('extensão SHAPE indisponível')

        scr  = X.XDefaultScreen(dpy)
        root = X.XRootWindow(dpy, scr)

        cmap = X.XDefaultColormap(dpy, scr)
        self.pixels = {}
        for name, rgb in palette.items():
            xc = _XColor()
            xc.red, xc.green, xc.blue = (c * 257 for c in rgb)
            X.XAllocColor(dpy, cmap, ctypes.byref(xc))
            self.pixels[name] = xc.pixel

        attrs = _XSetWindowAttributes()
        attrs.background_pixel  = next(iter(self.pixels.values()))
        attrs.border_pixel      = 0
        attrs.override_redirect = 1
        mask = _CW_BACK_PIXEL | _CW_BORDER_PIXEL | _CW_OVERRIDE_REDIRECT
        self.win = X.XCreateWindow(dpy, root, 0, 0, self.w, self.h, 0, 0,
                                   _INPUT_OUTPUT, None, mask,
                                   ctypes.byref(attrs))

        if round_:
            pm = X.XCreatePixmap(dpy, self.win, self.w, self.h, 1)
            gc = X.XCreateGC(dpy, pm, 0, None)
            X.XSetForeground(dpy, gc, 0)
            X.XFillRectangle(dpy, pm, gc, 0, 0, self.w, self.h)
            X.XSetForeground(dpy, gc, 1)
            X.XFillArc(dpy, pm, gc, 0, 0, self.w, self.h, 0, 360 * 64)
            Xe.XShapeCombineMask(dpy, self.win, _SHAPE_BOUNDING, 0, 0, pm,
                                 _SHAPE_SET)
            X.XFreeGC(dpy, gc)
            X.XFreePixmap(dpy, pm)

        # Transparente a cliques: região de entrada vazia
        Xe.XShapeCombineRectangles(dpy, self.win, _SHAPE_INPUT, 0, 0,
                                   None, 0, _SHAPE_SET, _UNSORTED)
        X.XFlush(dpy)

    def move(self, x: int, y: int):
        self.X.XMoveWindow(self.dpy, self.win, int(x) + self.origin[0],
                           int(y) + self.origin[1])
        self.raise_()

    def raise_(self):
        self.X.XRaiseWindow(self.dpy, self.win)
        self.X.XFlush(self.dpy)

    def set_color(self, state: str):
        if state == self.state or state not in self.pixels:
            return
        self.state = state
        self.X.XSetWindowBackground(self.dpy, self.win, self.pixels[state])
        self.X.XClearWindow(self.dpy, self.win)
        self.X.XFlush(self.dpy)

    def show(self):
        if not self.visible:
            self.X.XMapRaised(self.dpy, self.win)
            self.X.XFlush(self.dpy)
            self.visible = True

    def hide(self):
        if self.visible:
            self.X.XUnmapWindow(self.dpy, self.win)
            self.X.XFlush(self.dpy)
            self.visible = False

    def close(self):
        self.X.XDestroyWindow(self.dpy, self.win)
        self.X.XCloseDisplay(self.dpy)


class GazeOverlay:
    def __init__(self, radius: int = GAZE_DOT_RADIUS,
                 color: tuple = GAZE_DOT_COLOR, origin: tuple = (0, 0)):
        self.r = radius
        self._win: _ShapedWindow | None = None

        if not GAZE_DOT_ENABLED:
            return
        if not _x11_available():
            print('[GazeOverlay] Marcador disponível apenas em X11 — desativado.')
            return
        try:
            self._win = _ShapedWindow(2 * radius, 2 * radius, True,
                                      _palette(color), origin)
            self._win.set_color('normal')
            print(f'[GazeOverlay] Marcador do olhar ativo (raio {radius} px).')
        except Exception as e:
            print(f'[GazeOverlay] Não foi possível criar o marcador: {e}')

    def move(self, x: int, y: int):
        if self._win is None:
            return
        self._win.show()
        self._win.move(int(x) - self.r, int(y) - self.r)

    def set_state(self, state: str):
        if self._win is not None:
            self._win.set_color(state)

    def show(self):
        if self._win is not None:
            self._win.show()

    def hide(self):
        if self._win is not None:
            self._win.hide()

    def close(self):
        if self._win is not None:
            self._win.close()
            self._win = None


class EdgeBar:
    _RAISE_EVERY_S = 1.0

    def __init__(self, sw: int, regions: list, origin: tuple = (0, 0),
                 thickness: int = SCROLL_HANDLE_BAR_PX):
        self.sw = sw
        self.thickness = thickness
        self.origin = origin
        self._wins: list = []
        self._t_raise = -1e9
        self._hidden = False
        self.set_regions(regions)

    def set_regions(self, regions: list):
        self.close()
        if not (SCROLL_HANDLE_BAR and _x11_available()):
            return
        pal = _palette(GAZE_DOT_COLOR)
        try:
            for x0, y0, x1, y1 in regions:
                win = _ShapedWindow(self.thickness, max(1, int(y1 - y0)), False,
                                    pal, self.origin)
                self._wins.append(win)
                win.move(0 if x0 <= 0 else self.sw - self.thickness, int(y0))
                win.set_color('locked')
        except Exception as e:
            print(f'[EdgeBar] Não foi possível criar a barra da alça: {e}')
            self.close()
            return
        if not self._hidden:
            self.show()

    def set_state(self, state: str, t: float):
        for w in self._wins:
            w.set_color(state)
        if self._wins and not self._hidden and t - self._t_raise > self._RAISE_EVERY_S:
            self._t_raise = t
            for w in self._wins:
                w.raise_()

    def show(self):
        self._hidden = False
        for w in self._wins:
            w.show()

    def hide(self):
        self._hidden = True
        for w in self._wins:
            w.hide()

    def close(self):
        for w in self._wins:
            try:
                w.close()
            except Exception:
                pass
        self._wins = []
