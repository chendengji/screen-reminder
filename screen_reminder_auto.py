#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
screen_reminder_auto.py — pywinauto 脚本自动亮角标

在你的自动化 py 脚本顶部一行 import，之后所有 pywinauto 鼠标/键盘操作
都会自动在屏幕右下角显示操作角标（不抢焦点、鼠标穿透、自动淡出），
无需改动你的操作代码：

    import screen_reminder_auto          # 自动包装 pywinauto
    from pywinauto import mouse
    mouse.click(...)                     # 自动亮角标「正在点击 left」

也提供 context manager（任务级，保持显示直到结束）：

    with screen_reminder_auto.task("正在执行论文批量导出"):
        ...  # 操作期间角标常亮，结束后自动关闭

依赖：本机 screen_reminder.py 守护（~/.pi/agent/scripts/screen_reminder.py）。
import 时自动确保守护在跑（幂等）。
"""
import os
import sys
import time
import subprocess

SCRIPT = os.path.join(os.path.expanduser('~'), '.pi', 'agent',
                      'scripts', 'screen_reminder.py')

_last = [0.0]


def _fire(args):
    """fire-and-forget 调 screen_reminder.py 客户端命令（零输出零等待）"""
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        subprocess.Popen(
            [sys.executable, SCRIPT] + args,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
    except Exception:
        pass


def remind(text, hold=False):
    """更新角标文本（节流 500ms，避免高频刷新）"""
    now = time.time()
    if now - _last[0] < 0.5:
        return
    _last[0] = now
    args = ['set', text] + (['--hold'] if hold else [])
    _fire(args)


# 确保守护常驻（幂等：已运行则复用）
_fire(['start'])


def _patch_pywinauto():
    """monkeypatch pywinauto 常用入口，操作时自动亮角标"""
    try:
        import pywinauto.mouse as mouse
        import pywinauto.keyboard as keyboard
    except Exception:
        return  # 未装 pywinauto，跳过（模块本身仍可用）

    if not getattr(mouse.click, '_reminder_wrapped', False):
        _orig = mouse.click
        def click(*a, **k):
            try:
                btn = k.get('button', a[0] if a else 'left')
            except Exception:
                btn = 'left'
            remind('正在点击 %s' % btn)
            return _orig(*a, **k)
        click._reminder_wrapped = True
        mouse.click = click

    if not getattr(mouse.move_to, '_reminder_wrapped', False):
        _orig = mouse.move_to
        def move_to(*a, **k):
            remind('正在移动鼠标')
            return _orig(*a, **k)
        move_to._reminder_wrapped = True
        mouse.move_to = move_to

    if not getattr(keyboard.type_keys, '_reminder_wrapped', False):
        _orig = keyboard.type_keys
        def type_keys(*a, **k):
            remind('正在输入文字')
            return _orig(*a, **k)
        type_keys._reminder_wrapped = True
        keyboard.type_keys = type_keys

    if not getattr(keyboard.send_keys, '_reminder_wrapped', False):
        _orig = keyboard.send_keys
        def send_keys(*a, **k):
            remind('正在发送按键')
            return _orig(*a, **k)
        send_keys._reminder_wrapped = True
        keyboard.send_keys = send_keys


_patch_pywinauto()


def task(text):
    """context manager：进入时保持显示，退出时关闭（任务级角标）"""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        remind(text, hold=True)
        try:
            yield
        finally:
            _fire(['stop'])
    return _cm()
