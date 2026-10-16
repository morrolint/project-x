"""控制台 v1：HTTP API 冒烟（页/status/brief/chat/无TG泄漏/404）。"""
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from helpers import FakeTG, isolate

import console
import daemon as dm
import daemon_state
import evolve
import llm
import memory
import tasks
import tools


class TestConsole(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        memory.MEMORY_DIR = cls.tmp / "memory"
        memory.MEMORY_DIR.mkdir(parents=True)
        tools.TASKS_FILE = cls.tmp / "TASKS.md"
        tools.TASKS_FILE.write_text("# 任务收件箱\n\n## 待办\n\n## 已完成\n", encoding="utf-8")
        tools.ASSISTANT_DIR = cls.tmp
        console.ASSISTANT_DIR = cls.tmp
        (cls.tmp / "reports").mkdir(exist_ok=True)
        (cls.tmp / "reports" / "2026-10-16-早报.md").write_text(
            "# 早报 · 10-16\n\n正文内容测试。", encoding="utf-8")
        dm.LOGS_DIR = cls.tmp / "logs"
        tasks.TASKS_DIR = cls.tmp / "tasks"
        tasks.TASKS_DIR.mkdir(parents=True)
        daemon_state.STATE_FILE = cls.tmp / "state.json"
        evolve.ASSISTANT_DIR = cls.tmp
        evolve.REGISTRY = cls.tmp / "r.json"
        evolve.CHECKER = Path(__file__).resolve().parent.parent / "integrations" / "check_registry.py"
        evolve.EVOLUTION_LOG = cls.tmp / "evolution.md"

        tg = FakeTG()
        llm.chat = lambda ms, t=None: (
            {"content": "控制台你好，办好了。", "role": "assistant"}, {"total_tokens": 9}, None)
        cls.daemon = dm.Daemon(tg)
        cls.srv = console.build_server(0, cls.daemon, tg)  # 端口 0=系统分配，避免冲突
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        time.sleep(0.3)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_console_page(self):
        body = urllib.request.urlopen(self.base + "/", timeout=5).read().decode("utf-8")
        self.assertIn("舰桥控制台", body)
        self.assertIn("/api/status", body)

    def test_status(self):
        st = json.loads(urllib.request.urlopen(self.base + "/api/status", timeout=5).read())
        self.assertEqual(st["daemon"], "online")
        self.assertIn("tokens_today", st)
        self.assertIn("next_shift", st)

    def test_brief(self):
        r = urllib.request.urlopen(self.base + "/api/brief", timeout=5).read().decode("utf-8")
        self.assertIn("正文内容测试", r)

    def test_chat_no_tg_leak(self):
        req = urllib.request.Request(
            self.base + "/api/chat",
            data=json.dumps({"text": "在吗"}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        self.assertEqual(resp["reply"], "控制台你好，办好了。")
        self.assertFalse(self.daemon.tg.sent if hasattr(self.daemon.tg, "sent") else False,
                         "console 对话不得推 Telegram")

    def test_404(self):
        try:
            urllib.request.urlopen(self.base + "/api/nope", timeout=5)
            self.fail("应 404")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)


if __name__ == "__main__":
    unittest.main()
