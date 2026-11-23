"""Minimal uia substitute — only GetMonitorsRect is needed by control_overlay."""
import ctypes
from collections import namedtuple
from ctypes import wintypes

_MonitorRect = namedtuple('MonitorRect', 'left top right bottom')


class _Rect(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint32), ("rcMonitor", _Rect),
                ("rcWork", _Rect), ("dwFlags", ctypes.c_uint32)]


def GetMonitorsRect():
    """Return all monitor rects as MonitorRect(left, top, right, bottom) objects."""
    user32 = ctypes.windll.user32
    rects = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                        ctypes.POINTER(_Rect), wintypes.LPARAM)
    def _enum(hmon, hdc, lprect, lparam):
        if lprect:
            rects.append(_MonitorRect(lprect.contents.left, lprect.contents.top,
                                      lprect.contents.right, lprect.contents.bottom))
        return 1

    user32.EnumDisplayMonitors(None, None, _enum, 0)
    if not rects:
        sm = user32.GetSystemMetrics
        rects = [_MonitorRect(0, 0, sm(0), sm(1))]
    return rects
