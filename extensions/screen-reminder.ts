import { type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { spawn } from "node:child_process";
import * as path from "node:path";
import * as os from "node:os";

// 屏幕悬浮提醒角标脚本（不抢焦点 / 鼠标穿透 / 置顶 / 自动淡出）
const SCRIPT = path.join(os.homedir(), ".pi", "agent", "scripts", "screen_reminder.py");

// 自动感知已由守护进程承担（screen_reminder.py 自行监控 pi session，
// 检测 automation_* 工具调用并自动变换提示文字）——扩展只负责：
//   ① init 时确保守护常驻；② 注册显式工具 screen_reminder。

function runScript(args: string[]) {
  // fire-and-forget：detach + unref，零输出零等待
  const trySpawn = (cmd: string) =>
    spawn(cmd, [SCRIPT, ...args], { detached: true, stdio: "ignore", windowsHide: true }).unref();
  try {
    trySpawn("python");
  } catch {
    try {
      trySpawn("py");
    } catch {
      try {
        trySpawn("python3");
      } catch {
        /* ignore */
      }
    }
  }
}

export default function (pi: ExtensionAPI) {
  // 启动时确保常驻守护在跑（幂等：已运行则直接复用）
  runScript(["start"]);

  // ① 注册可显式调用的工具（agent 可手动 start/set/stop/status）
  pi.registerTool({
    name: "screen_reminder",
    label: "Screen Reminder",
    description:
      "屏幕悬浮提醒角标（右下角置顶、不抢焦点、鼠标点击穿透、自动淡出）。" +
      "action: start 启动常驻守护；set \"文本\" 更新提醒（fire-and-forget 零输出，默认 4 秒自动淡出，" +
      "hold=true 则保持显示）；stop 停止；status 查询。用于 agent 做 Windows GUI 自动化时提示当前操作。",
    promptSnippet: "Show a corner reminder badge on screen",
    promptGuidelines: [
      "Use screen_reminder when starting a Windows GUI automation task to show a corner badge, and stop when done.",
    ],
    parameters: Type.Object({
      action: Type.String({ description: "start | set | stop | status" }),
      text: Type.Optional(Type.String({ description: "提醒文本（action=set 时必填）" })),
      hold: Type.Optional(Type.Boolean({ description: "set 时保持显示不自动淡出" })),
    }),
    async execute(_toolCallId, params) {
      const action = params.action;
      if (action === "set") {
        const t = (params.text || "").trim();
        if (!t) return { content: [{ type: "text", text: "text required" }], details: {} };
        const args = ["set", t];
        if (params.hold) args.push("--hold");
        runScript(args);
        return { content: [{ type: "text", text: "" }], details: {} };
      }
      runScript([action]);
      return { content: [{ type: "text", text: "" }], details: {} };
    },
  });

  // ② 自动感知由守护进程自行监控 session 承担，无需在此触发
  // （保留占位注释：若需扩展级快速触发可在此加 pi.on("tool_call")）
}
