"""任务线（Alex 进度面板方案 v1 的核心）：每个用户消息/班次一条任务，五态状态机，
tasks/<id>.json 为唯一事实源——daemon 重启可凭文件恢复状态（治"挂起态丢失/重复投递"两个老 bug）。

状态机：RUNNING → WAITING_USER（确认门）→ RUNNING → DONE / FAILED / CANCELED
进度呈现：单条 Telegram 消息 editMessageText 原地刷新（不发消息洪水）。
"""

import json
import time
from datetime import datetime
from pathlib import Path

TASKS_DIR = Path(__file__).resolve().parent / "tasks"
STATE_ICON = {"RUNNING": "⏳", "WAITING_USER": "🔔", "DONE": "✅", "FAILED": "⚠️", "CANCELED": "🚫"}


def _new_id():
    return datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 10) % 10}"


class TaskLine:
    def __init__(self, kind="chat", label=""):
        self.id = _new_id()
        self.kind = kind            # chat / shift-morning / shift-evening / reflect
        self.label = label or ("早晚班" if kind.startswith("shift") else "对话")
        self.state = "RUNNING"
        self.msg_id = None          # Telegram 进度消息 id（None=无通道回退）
        self.rounds = 0
        self.last_tools = []
        self.note = ""
        self.payload = None         # WAITING_USER 时的恢复载荷 {"messages":…, "calls":…}
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        self.save()

    # ---- 状态迁移

    def update(self, rounds=None, last_tools=None, note=""):
        if rounds is not None:
            self.rounds = rounds
        if last_tools is not None:
            self.last_tools = list(last_tools)[-3:]
        if note:
            self.note = note
        self.save()

    def wait_user(self, payload):
        self.state, self.payload = "WAITING_USER", payload
        self.save()

    def finish(self, state="DONE", note=""):
        self.state, self.note, self.payload = state, note, None
        self.save()

    # ---- 呈现

    def render(self):
        head = f"{STATE_ICON.get(self.state, '·')} {self.label}"
        if self.state == "RUNNING":
            body = f"第 {max(self.rounds, 1)} 轮"
            if self.last_tools:
                body += "，正在：" + "、".join(self.last_tools)
            if self.note:
                body += f"\n{self.note}"
        elif self.state == "WAITING_USER":
            body = "等你确认（回复「确认」执行，其他内容取消）"
        else:
            body = self.note or {"DONE": "完成", "FAILED": "失败", "CANCELED": "已取消"}[self.state]
        return f"{head}\n{body}"[:1000]

    def push(self, channel, edit=True):
        """把当前状态刷到 Telegram 进度消息（无消息则发一条）。"""
        if channel is None or not hasattr(channel, "send_ex"):
            return
        try:
            if self.msg_id and edit and hasattr(channel, "edit_message"):
                ok, _ = channel.edit_message(self.msg_id, self.render())
                if ok:
                    return
            err, mid = channel.send_ex(self.render())
            if mid:
                self.msg_id = mid
                self.save()
        except Exception:  # noqa: BLE001 —— 进度呈现失败绝不影响主流程
            pass

    # ---- 持久化（唯一事实源）

    def save(self):
        f = TASKS_DIR / f"{self.id}.json"
        try:
            f.write_text(json.dumps(self.__dict__, ensure_ascii=False, indent=1), encoding="utf-8")
        except (OSError, TypeError):
            pass  # 含不可序列化载荷时容忍丢档（进度可重建，主流程不能断）

    @classmethod
    def load(cls, f):
        t = cls.__new__(cls)
        t.__dict__.update(json.loads(f.read_text(encoding="utf-8")))
        return t


def recover(channel):
    """daemon 启动时扫任务档案：收尾僵尸、复活等待用户的任务。
    返回最新一个 WAITING_USER 的载荷（供 daemon 恢复确认门挂起态）。"""
    if not TASKS_DIR.exists():
        return None
    waiting = []
    for f in sorted(TASKS_DIR.glob("*.json")):
        try:
            t = TaskLine.load(f)
        except (ValueError, OSError):
            continue
        if t.state == "RUNNING":
            t.finish("FAILED", "服务重启中断，请重发指令")
            t.push(channel)  # 把用户那条进度消息刷成失败态
        elif t.state == "WAITING_USER":
            waiting.append(t)
    if not waiting:
        return None
    latest = waiting[-1]
    payload = latest.payload
    if payload and isinstance(payload, dict):
        return {"task": latest, "payload": payload}
    latest.finish("FAILED", "挂起载荷丢失（旧档），请重发指令")
    latest.push(channel)
    return None


def gc(keep_days=3):
    """清理已终结的旧任务档案。"""
    if not TASKS_DIR.exists():
        return
    cutoff = time.time() - keep_days * 86400
    for f in TASKS_DIR.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                t = TaskLine.load(f)
                if t.state in ("DONE", "FAILED", "CANCELED"):
                    f.unlink()
        except (OSError, ValueError):
            continue
