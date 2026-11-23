#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
screen_reminder.py — 屏幕操作提醒（复用 Windows-MCP 成熟控制指示器代码改造）

复用 CursorTouch/Windows-MCP 的 wmcp_reminder/control_overlay.py（成熟、已验证的
"AI 控制指示器"：四边呼吸发光 + 顶部居中通知面板 + 光标跟随 + 平滑动画），
在其基础上改造：
  - set_notice_text(title, hint)：把固定标题改为 agent 当前操作（动态文字）
  - set_accent(color)：颜色随操作类型变化（鼠标=橙红、键盘=蓝…）
  - 守护自行监控 pi session 的 automation_* 调用 -> 自动显示 + 变换文字/颜色
  - 空闲（无操作 hold 秒）自动隐藏

agent 使用方式（零注意力成本，fire-and-forget）:
  python screen_reminder.py start      # ① 常驻守护（CREATE_NO_WINDOW，无黑窗口）
  python screen_reminder.py set "正在点击「保存」"   # ② 更新提醒（零输出）
  python screen_reminder.py set "正在导出" --hold    #    任务级保持
  python screen_reminder.py stop                    # ③ 结束
"""
import os, sys, json, time, shutil, subprocess, tempfile

BASE = os.path.join(os.path.expanduser('~'), '.pi', 'reminder')
STATUS = os.path.join(BASE, 'status.json')
PIDFILE = os.path.join(BASE, 'daemon.pid')
LOGFILE = os.path.join(BASE, 'daemon.log')
PKG = os.path.dirname(os.path.abspath(__file__))

# 显示/隐藏参数
HOLD_MS = 4000
AUTO_IDLE_MS = 30000        # 无操作 30s 才隐藏（agent 操作期间持续亮）
CHECK_INTERVAL = 0.1

# 颜色随操作类型变化（active 显示色）
TOOL_COLOR = {
    'mouse': (255, 69, 0), 'keyboard': (64, 156, 255), 'windows': (76, 175, 80),
    'visual': (156, 39, 176), 'elements': (255, 152, 0), 'dialog': (255, 193, 7),
    'smart': (0, 188, 212), 'macro': (233, 30, 99),
}
DEFAULT_ACCENT = (0, 150, 255)
TOOL_MAP = {
    'mouse': '鼠标操作', 'keyboard': '键盘输入', 'windows': '窗口操作',
    'visual': '截图/OCR', 'elements': '界面元素', 'dialog': '文件对话框',
    'smart': '智能操作', 'mission': '自动化任务', 'task': '自动化任务',
    'watch': '等待事件', 'safety': '安全检查', 'system': '系统操作',
    'shortcut': '快捷键', 'assert': '校验', 'macro': '录制/重放',
}
AUTO_EXACT = {'get_desktop_state', 'get_window_state', 'analyze_winapp',
              'approve_automation'}
SESSIONS_ROOT = os.path.join(os.path.expanduser('~'), '.pi', 'agent', 'sessions')


# ----------------------------------------------------------------------
# 文件 IPC（原子写，fire-and-forget）
# ----------------------------------------------------------------------
def ensure_dir():
    os.makedirs(BASE, exist_ok=True)


def atomic_write(path, obj):
    ensure_dir()
    fd, tmp = tempfile.mkstemp(dir=BASE, suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def read_pid():
    d = read_json(PIDFILE)
    return d.get('pid') if isinstance(d, dict) else None


def daemon_alive():
    pid = read_pid()
    if not pid:
        return False
    import ctypes
    h = ctypes.windll.kernel32.OpenProcess(0x1000, False, int(pid))
    if h:
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    return False


# ----------------------------------------------------------------------
# agent 会话监控（守护自行读取，自动变换文字+颜色）
# ----------------------------------------------------------------------
def _short(name):
    """MCP 工具名带 mcp__windows_computer_use__ 前缀，剥离取末段"""
    return name.split('__')[-1] if '__' in name else name


def _is_auto_tool(name):
    s = _short(name)
    return (s.startswith('automation_') or s.startswith('cua_')
            or s in AUTO_EXACT)


def _describe(name, args=None):
    base = _short(name).replace('automation_', '').replace('cua_', '')
    if base in ('get_desktop_state', 'get_window_state'):
        return '正在读取界面状态'
    if base == 'analyze_winapp':
        return '正在分析应用'
    if base == 'approve_automation':
        return '正在授权自动化'
    for k, v in TOOL_MAP.items():
        if base.startswith(k):
            return '正在' + v
    return '正在执行 ' + base


def _accent_for(name):
    base = _short(name).replace('automation_', '').replace('cua_', '')
    for k, v in TOOL_COLOR.items():
        if base.startswith(k):
            return v
    return DEFAULT_ACCENT


def _find_latest_session():
    best, best_mt = None, 0
    try:
        dirs = os.listdir(SESSIONS_ROOT)
    except OSError:
        return None
    for d in dirs:
        sub = os.path.join(SESSIONS_ROOT, d)
        if not os.path.isdir(sub):
            continue
        try:
            files = os.listdir(sub)
        except OSError:
            continue
        for fn in files:
            if not fn.endswith('.jsonl'):
                continue
            p = os.path.join(sub, fn)
            try:
                mt = os.path.getmtime(p)
            except OSError:
                continue
            if mt > best_mt:
                best_mt, best = mt, p
    return best


def _scan_new_toolcalls(path, offset):
    try:
        size = os.path.getsize(path)
    except OSError:
        return offset, None
    if size < offset:
        offset = 0
    last = None
    try:
        with open(path, 'rb') as f:
            f.seek(offset)
            data = f.read()
    except OSError:
        return offset, None
    offset = size
    for line in data.decode('utf-8', 'ignore').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        m = d.get('message', {})
        if m.get('role') != 'assistant':
            continue
        for c in m.get('content', []):
            if isinstance(c, dict) and c.get('type') == 'toolCall':
                nm = c.get('name', '')
                if _is_auto_tool(nm):
                    last = (nm, c.get('arguments', {}))
    return offset, last


def find_uv():
    for cand in (shutil.which('uv'), shutil.which('uv.exe'),
                 os.path.expanduser('~/.local/bin/uv'),
                 os.path.expanduser('~/AppData/Roaming/uv/uv.exe')):
        if cand and os.path.exists(cand):
            return cand
    return None


# ----------------------------------------------------------------------
# client 命令
# ----------------------------------------------------------------------
def cmd_start():
    if daemon_alive():
        print('already running (pid %s)' % read_pid())
        return
    uv = find_uv()
    if not uv:
        print('ERROR: uv not found in PATH / ~/.local/bin/uv')
        sys.exit(1)
    cmd = [uv, 'run', '--with', 'pywin32', '--with', 'pillow', 'python',
           os.path.abspath(__file__), '--daemon']
    # CREATE_NO_WINDOW：隐藏控制台（修复"黑乎乎命令行弹窗"）
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(cmd, cwd=PKG, creationflags=flags,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True)
    for _ in range(200):
        if daemon_alive():
            print('started (pid %s)' % read_pid())
            return
        time.sleep(0.1)
    print('start failed — pidfile=%s — see %s' % (os.path.exists(PIDFILE), LOGFILE))
    sys.exit(1)


def cmd_set(text, hold=False):
    atomic_write(STATUS, {'cmd': 'set', 'text': text, 'hold': bool(hold),
                          'ts': time.time()})


def cmd_stop():
    atomic_write(STATUS, {'cmd': 'stop', 'ts': time.time()})


def cmd_status():
    alive = daemon_alive()
    print('daemon:', 'running (pid %s)' % read_pid() if alive else 'not running')
    st = read_json(STATUS)
    if st:
        print('last:', st.get('cmd'), '| text:', st.get('text', '')[:80])


# ----------------------------------------------------------------------
# daemon（复用 wmcp_reminder.control_overlay 成熟代码）
# ----------------------------------------------------------------------
def run_daemon():
    ensure_dir()
    log = open(LOGFILE, 'a', encoding='utf-8', buffering=1)
    sys.stdout = log
    sys.stderr = log
    atomic_write(PIDFILE, {'pid': os.getpid(), 'ts': time.time()})

    import wmcp_reminder.control_overlay as co
    co.start()                      # 启动显示线程（成熟代码）
    # 初始不显示；等 agent 操作（monitor/IPC）触发 set_active(True)

    state = {'hold_until': 0.0, 'mon': {'path': None, 'offset': 0, 'last': ''}}
    last_set_text = None

    def apply(text, accent, hold_until):
        nonlocal last_set_text
        co.set_notice_text(text, 'Agent 正在操作电脑')
        try:
            co.set_accent(accent)
        except Exception:
            pass
        if text != last_set_text:
            print('reminder: %s' % text, flush=True)
            last_set_text = text
        co.set_active(True)
        state['hold_until'] = hold_until

    def handle_ipc():
        st = read_json(STATUS)
        if not st:
            return False
        cmd = st.get('cmd')
        if cmd == 'stop':
            os.remove(STATUS)
            return 'stop'
        if cmd == 'set':
            text = (st.get('text') or '').strip() or '正在操作'
            hold_until = (float('inf') if st.get('hold')
                          else time.time() + HOLD_MS / 1000.0)
            apply(text, DEFAULT_ACCENT, hold_until)
        os.remove(STATUS)
        return 'set' if cmd == 'set' else None

    def monitor_tick():
        path = _find_latest_session()
        if not path:
            return
        mon = state['mon']
        if mon['path'] != path:
            mon['path'] = path
            mon['offset'] = 0
            mon['last'] = ''
        off, auto = _scan_new_toolcalls(path, mon['offset'])
        mon['offset'] = off
        if not auto:
            return
        name, args = auto
        text = _describe(name, args)
        if text == mon['last']:
            return
        mon['last'] = text
        apply(text, _accent_for(name), time.time() + AUTO_IDLE_MS / 1000.0)

    # 主循环：IPC + session 监控 + 空闲隐藏
    last_check = 0.0
    while True:
        if time.time() - last_check >= CHECK_INTERVAL:
            last_check = time.time()
            r = handle_ipc()
            if r == 'stop':
                break
            monitor_tick()
            if state['hold_until'] != float('inf') and time.time() >= state['hold_until']:
                co.set_active(False)   # 空闲自动隐藏
                state['hold_until'] = 0.0
        time.sleep(0.05)

    try:
        co.stop()
    except Exception:
        pass
    try:
        os.remove(PIDFILE)
    except OSError:
        pass


# ----------------------------------------------------------------------
if __name__ == '__main__':
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)
    cmd = args[0]
    if cmd == '--daemon':
        run_daemon()
    elif cmd == 'start':
        cmd_start()
    elif cmd == 'set':
        text = ' '.join(args[1:]) if '--hold' not in args else ' '.join(
            a for a in args[1:] if a != '--hold')
        cmd_set(text, hold='--hold' in args)
    elif cmd == 'stop':
        cmd_stop()
    elif cmd == 'status':
        cmd_status()
    else:
        print('unknown command: %s' % cmd)
        print(__doc__)
        sys.exit(1)
