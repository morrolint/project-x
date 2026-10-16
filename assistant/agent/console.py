"""桌面控制台 v1（B 档活服务）：daemon 内嵌 HTTP 服务，本机回环访问。

- GET  /            控制台页（web/console/index.html，若存在则原样返回）
- GET  /api/status  活状态 JSON（daemon/任务线/收件箱/今日 token/下一班）
- POST /api/chat    网页对话（同步阻塞；与 Telegram 共用同一 daemon 循环/记忆/确认门）

安全：只绑 127.0.0.1（PM 卡取舍）；公网访问走 Tailscale 另议。仅本机回环不加鉴权。
"""

import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from daemon_state import load_state
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ASSISTANT_DIR = AGENT_DIR.parent
WEB_DIR = AGENT_DIR.parent / "web" / "console"
_lock = threading.Lock()


def build_server(port, daemon, tg_client):
    """构建控制台 HTTP 服务（daemon.run 调用；daemon/tg 以闭包注入，避免循环 import）。"""
    import tasks as tasks_mod
    import llm as llm_mod

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 静默默认访问日志（JSONL 才是事实源）
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            if path == "/":
                page = WEB_DIR / "index.html"
                if page.exists():
                    body = page.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self._json({"error": "控制台页未找到（web/console/index.html）"}, 404)
            elif path == "/api/status":
                self._json(self._status())
            elif path == "/api/brief":
                text, src = self._brief()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(text.encode("utf-8"))))
                self.end_headers()
                self.wfile.write(text.encode("utf-8"))
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self):
            if self.path.split("?")[0] != "/api/chat":
                self._json({"error": "not found"}, 404)
                return
            if not _lock.acquire(blocking=False):
                self._json({"error": "已有对话在处理中，稍候再试"}, 409)
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                req = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
                text = str(req.get("text", "")).strip()
                if not text:
                    self._json({"error": "text 为空"}, 400)
                    return
                reply = daemon.handle_console_text(text)
                self._json({"reply": reply,
                            "pending": daemon.pending is not None,
                            "time": datetime.now().isoformat(timespec="seconds")})
            except (ValueError, json.JSONDecodeError):
                self._json({"error": "请求体须为 JSON"}, 400)
            except Exception as e:  # noqa: BLE001
                self._json({"error": f"{type(e).__name__}: {e}"}, 500)
            finally:
                _lock.release()

        def _brief(self):
            """今日早报全文（无则最新一份报告）。返回 (文本, 来源文件名)。"""
            reports = ASSISTANT_DIR / "reports"
            today = datetime.now().strftime("%Y-%m-%d")
            for name in (f"{today}-早报.md", f"{today}-晚间简报.md"):
                f = reports / name
                if f.exists():
                    return f.read_text(encoding="utf-8"), name
            cands = sorted(reports.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
            if cands:
                return cands[0].read_text(encoding="utf-8"), cands[0].name
            return "（暂无报告）", "—"

        def _status(self):
            now = datetime.now()
            tokens_today, tasks_open = 0, []
            logf = AGENT_DIR / "logs" / f"{now:%Y-%m-%d}.jsonl"
            if logf.exists():
                for line in logf.read_text(encoding="utf-8").splitlines():
                    try:
                        r = json.loads(line)
                    except ValueError:
                        continue
                    if r.get("dir") == "llm":
                        tokens_today += (r.get("usage") or {}).get("total_tokens", 0)
            if tasks_mod.TASKS_DIR.exists():
                for f in sorted(tasks_mod.TASKS_DIR.glob("*.json"), reverse=True)[:8]:
                    try:
                        t = tasks_mod.TaskLine.load(f)
                        tasks_open.append({"state": t.state, "label": t.label, "note": t.note})
                    except (ValueError, OSError):
                        continue
            reg_n = 0
            try:
                reg_n = len(json.loads((ASSISTANT_DIR / "integrations" / "registry.json")
                                       .read_text(encoding="utf-8"))["integrations"])
            except (OSError, ValueError, KeyError):
                pass
            mem_n = len(list((ASSISTANT_DIR / "memory").glob("*.md"))) \
                if (ASSISTANT_DIR / "memory").exists() else 0
            inbox = []
            tf = ASSISTANT_DIR / "TASKS.md"
            if tf.exists():
                in_todo = False
                for line in tf.read_text(encoding="utf-8").splitlines():
                    t = line.strip()
                    if t.startswith("## "):
                        in_todo = t == "## 待办"
                        continue
                    if in_todo and t.startswith("- ") and "（示例格式）" not in t:
                        inbox.append(t[2:].strip())
            shifts = load_state().get("shifts", {})
            next_shift, eta = "早班 08:00", None
            for kind, hour in (("晚班", 21), ("早班", 8)):
                target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
                if target > now:
                    next_shift, eta = f"{kind} {hour:02d}:00", str(target - now).split(".")[0]
                    break
            return {"daemon": "online", "model": llm_mod.model_name(),
                    "time": now.isoformat(timespec="seconds"),
                    "tokens_today": tokens_today, "registry": reg_n, "memory": mem_n,
                    "inbox": inbox,
                    "tasks": tasks_open, "next_shift": next_shift, "next_eta": eta,
                    "shifts_done": shifts}

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server
