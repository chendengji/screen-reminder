# screen-reminder — 界面操作状态提醒（Windows）

Agent 做 Windows GUI 自动化时，在屏幕**四边呼吸发光边框 + 顶部居中通知面板**亮起当前操作状态提醒。

**不抢焦点、鼠标点击穿透**，完全不干扰 agent 的 pywinauto 点击/输入，也不干扰用户手动操作。支持 **daemon 自动感知**：agent 调用 `automation_*` 工具时自动亮起并变换文字+颜色，agent **零注意力成本**（无需自己管理显示）。

## 界面

- **四边呼吸发光边框**（`_BORDER = 112px`，`_breath_opacity` 3s 呼吸周期）
- **顶部居中深蓝圆角面板**（标题 = 当前操作文字，副标题 =「Agent 正在操作电脑」）
- 标题使用**微软雅黑 `msyh.ttc`**（Segoe UI 不含中文字形，会导致中文显示不全/缺字）
- 颜色随操作类型变化（鼠标橙红 / 键盘蓝 / 窗口绿 / 截图紫 / 对话框黄 / 智能青 / 宏玫红）
- **无接管弹窗、无鼠标移动脱离**（只复制了 Windows-MCP 的视觉层，未复制其 server 端的人类接管控制流）

## 架构

```
screen_reminder.py        # 主入口：薄客户端（start/set/stop/status + 文件 IPC + session 监控 + CREATE_NO_WINDOW）
wmcp_reminder/            # 视觉层（复用 Windows-MCP control_overlay / control_overlay_art / flash_overlay / overlay_bitmap / uia）
screen_reminder_auto.py   # pywinauto 自动包装（import 即自动亮提醒 + task context manager）
```

**3 个调用入口**：

1. **命令行**：`python screen_reminder.py start|set|stop|status`（daemon 用 `CREATE_NO_WINDOW` 启动，无黑窗口）
2. **Python API**：`import screen_reminder_auto`（pywinauto 包装，`with task(...):` 自动亮/灭）
3. **守护自动感知**：daemon 每 500ms 增量读 pi session 的 `automation_*` / `cua_*` 工具调用，自动亮起 + 变换文字 + 变换颜色，30s 无操作自动隐藏（`AUTO_IDLE_MS = 30000`）

## 安装

```bash
# 依赖：pywin32 + pillow（建议用 uv 临时带包，不污染项目环境）
uv run --with pywin32 --with pillow python screen_reminder.py --help
```

## 用法

```bash
# 1) 启动常驻守护（一次；daemon 无黑窗口、自管生命周期）
python screen_reminder.py start

# 2) 每步一句提醒（fire-and-forget，零输出零等待，自动淡出）
python screen_reminder.py set "正在点击「保存」"

# 3) 任务级保持显示（直到 stop 或超时）
python screen_reminder.py set "正在执行论文批量导出" --hold

# 4) 结束
python screen_reminder.py stop

# 5) 状态查询
python screen_reminder.py status
```

**注意**：`set` 命令零输出、立即返回，不要等待/解析其 stdout；daemon 由 `start` 后台 detach 自管。

**Python API**（pywinauto 自动包装）：

```python
from screen_reminder_auto import reminder_task

with reminder_task("正在点击「保存」"):
    # 这里执行 GUI 自动化操作，提醒自动亮起/熄灭
    ...
```

## 守护自动感知（agent 零注意力）

daemon 每 500ms 增量扫描 pi 的 session JSONL，检测 assistant 消息里的 `automation_*` / `cua_*` 工具调用，自动：

- 变换面板文字（15 类操作映射：「正在点击」「正在键盘输入」「正在窗口操作」…）
- 变换边缘颜色（8 类操作配色）
- 30s 无操作自动隐藏

工具名可能带 `mcp__windows_computer_use__` 前缀，已用 `_short()` 剥离。**agent 无需调用 `set`**——操作 computer-use 即自动亮起。

## 文件 / IPC

- 运行时：`~/.pi/reminder/status.json`（IPC，daemon 每 100ms 轮询）、`daemon.pid`、`daemon.log`
- 会话监控：`~/.pi/agent/sessions/*/*.jsonl`（daemon 增量读）
- 环境变量：`SCREEN_REMINDER_RUNTIME_DIR`（可覆盖运行时目录，默认 `~/.pi/reminder`）

## 变更与踩坑

详细变更记录、已踩坑清单（6 条）、设计要点、运行时文件见 **[REFERENCE.md](REFERENCE.md)**。

- v0.1.1：修复**聊天误触发**（offset 重置扫描历史 `automation_*` → 跳到文件尾，只对新调用生效）
- v0.1.0：初始发布（复用 Windows-MCP 视觉层 + 守护自动感知）

## 许可

MIT。视觉层 `wmcp_reminder/` 基于 [CursorTouch/Windows-MCP](https://github.com/CursorTouch/Windows-MCP)（MIT）的 `desktop/control_overlay.py`、`control_overlay_art.py`、`flash_overlay.py`、`overlay_bitmap.py` 改造（动态文字、动态颜色、去 WDA_EXCLUDEFROMCAPTURE、无接管控制流）。
