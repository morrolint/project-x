"""任务线：五态生命周期 / WAITING_USER 落盘 / 僵尸恢复 / gc。"""
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import tasks


class TestTasks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        tasks.TASKS_DIR = self.tmp / "tasks"
        tasks.TASKS_DIR.mkdir(parents=True)

    def test_lifecycle(self):
        t = tasks.TaskLine(kind="chat", label="测试")
        self.assertEqual(t.state, "RUNNING")
        t.update(rounds=2, last_tools=["inbox_list"])
        t.wait_user({"messages": [], "calls": []})
        self.assertEqual(t.state, "WAITING_USER")
        t.finish("DONE", "3 次工具")
        rec = json.loads((self.tmp / "tasks" / f"{t.id}.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["state"], "DONE")
        self.assertEqual(rec["rounds"], 2)

    def test_recover_zombie_failed(self):
        t = tasks.TaskLine(kind="chat", label="僵尸")
        t.state = "RUNNING"
        t.save()
        tasks.recover(None)
        rec = json.loads((self.tmp / "tasks" / f"{t.id}.json").read_text(encoding="utf-8"))
        self.assertEqual(rec["state"], "FAILED")
        self.assertIn("重启", rec["note"])

    def test_recover_returns_latest_waiting(self):
        a = tasks.TaskLine(kind="chat", label="a"); a.wait_user({"calls": [1]})
        b = tasks.TaskLine(kind="chat", label="b"); b.wait_user({"calls": [2]})
        got = tasks.recover(None)
        self.assertEqual(got["task"].id, b.id)

    def test_gc_removes_finished(self):
        t = tasks.TaskLine(kind="chat", label="x")
        t.finish("DONE")
        f = self.tmp / "tasks" / f"{t.id}.json"
        f.write_text(json.dumps({"id": t.id, "state": "DONE", "msg_id": None,
                                 "rounds": 0, "last_tools": [], "note": "", "payload": None,
                                 "kind": "chat", "label": "x"}), encoding="utf-8")
        import os
        os.utime(f, (0, 0))
        tasks.gc(keep_days=3)
        self.assertFalse(f.exists())
