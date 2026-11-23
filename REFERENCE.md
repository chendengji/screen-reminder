# screen-reminder 参考文档（变更与踩坑记录）

本文件记录 screen-reminder 的实现细节、踩坑与变更，供维护者参考。
**技能文档（SKILL）不重复这些内容**——需要细节看这里。

## 版本变更

### v0.1.2（2026-11-23）
- **恢复截图穿透**：重新启用 `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)`（每个 `_Layer` 窗口创建后调用）。
  - 效果：四边呼吸发光 + 顶部面板**不被截图/录屏捕获**（用户截屏、OBS、agent 截图都穿透它），屏幕上仍正常显示。
  - 验证：PrintWindow 捕获面板中心像素由深蓝 `(6,33,70)` 变 `(0,0,0)`（空/透明 = 穿透）。
  - 说明：此前为可视化演示曾移除 WDA；现按需求恢复（截图穿透）。

### v0.1.1（2026-11-23）
- **修复聊天误触发 bug**：daemon 监控 session 时，`offset` 重置为 `0` 会重新扫描整个文件，把历史 `automation_*` 调用（如 computer-use 演示留下的 `automation_keyboard`）再次检测到，导致**聊天时重复亮「正在键盘输入」**。
  - 修复：`_scan_new_toolcalls` 里 `size < offset` 时 `offset = size`（跳到文件尾）；`monitor_tick` 里换 session 时 `mon['offset'] = os.path.getsize(path)`（同样跳到尾）。
  - 效果：只对**之后新写入**的 `automation_*` 调用触发；历史调用永不重读 → 聊天（只写文本消息）不触发，computer-use 操作仍正常触发。
  - 验证：daemon 启动初始不触发（窗口 0/0）；`automation_windows` 正常亮「正在窗口操作」。
- 同步：本地 `screen_reminder.py` 与分发版一致。

### v0.1.0（2026-11-23，初始发布）
- 复用 Windows-MCP 视觉层（`wmcp_reminder/`），改造为动态文字 + 动态颜色 + WDA_EXCLUDEFROMCAPTURE（截图穿透）+ 无接管控制流。
- 守护自动感知：daemon 每 500ms 增量读 pi session 的 `automation_*`/`cua_*` 调用，自动亮+变文字+变颜色，30s 无操作自动隐藏。
- 分发版发布 GitHub：`github.com/chendengji/screen-reminder`（public）。

## 已踩坑（定稿修复）

1. **Segoe UI 中文显示不全**：`seguisb.ttf`/`segoeui.ttf` 不含中文字形 → 改微软雅黑 `msyh.ttc`（`_FONT_CN`）。
2. **`_NOTICE_SHORTCUT=''` 时 `partition('')` 抛 `ValueError: empty separator`**：清空快捷键后渲染会崩 → `_notice_bitmap` 判空跳过分割与徽章。
3. **「亮一下就没」**：启动时 `set_active(True)` 后主循环立即 `set_active(False)`（`hold_until=0.0`）→ 初始**不显示**，等 agent 操作（monitor/IPC）触发。
4. **快捷键徽章残留**：原版 `Ctrl+Alt+Shift+Backspace` 接管提示 → 清空 `_NOTICE_SHORTCUT`（`set_notice_text` 里设 `""`）。
5. **边框宽度**：用户要求翻倍 → `_BORDER 56 → 112`。
6. **聊天误触发**（v0.1.1）：offset 重置扫描历史 `automation_*` → 跳到文件尾，只对新调用生效。

## 设计要点

- **3 入口**：① pi 工具 `screen_reminder`（`screen-reminder.ts` 注册）；② 守护自动感知（daemon 读 session 的 `automation_*`，MCP 不被调用而是被感知，agent 零注意力）；③ Python API `screen_reminder_auto`（pywinauto 包装，import 即亮）。
- **无接管控制流**：只复制 Windows-MCP 的**视觉层**（`control_overlay.py`/`control_overlay_art.py`/`flash_overlay.py`/`overlay_bitmap.py`），未复制其 server 端（`uia/core.py`）的「申请确认弹窗」和「鼠标移动脱离 AI 控制」——本工具是被动文字提醒，不申请接管、不响应鼠标。
- **工具名前缀**：pi session 里工具名为 `mcp__windows_computer_use__automation_*`，需 `_short()` 剥离取末段匹配。
- **无黑窗口**：daemon 用 `CREATE_NO_WINDOW` 启动。
- **零注意力**：`set` 只原子写 `status.json` 即返回（fire-and-forget），daemon 每 100ms 轮询。

## 运行时文件

- IPC：`~/.pi/reminder/status.json`、`daemon.pid`、`daemon.log`（可 `SCREEN_REMINDER_RUNTIME_DIR` 覆盖）
- session 监控：`~/.pi/agent/sessions/*/*.jsonl`（daemon 增量读，offset 跳到尾）
