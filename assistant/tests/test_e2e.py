"""端到端（FakeTG + LLM 脚桩）：任务线生命周期 / 确认门按钮与分级 / 错误态 / 恢复。"""
import json, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
from helpers import FakeTG, msg, tc, isolate
import daemon as dm
import llm, tools, memory, tasks, daemon_state


class TestE2E(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        isolate(self.tmp)
        self.tg = FakeTG()

    def run_script(self, script):
        llm.chat = lambda ms, t=None: script(ms)

    def test_tool_turn_finishes_done_with_edits(self):
        self.run_script(lambda ms: (msg(calls=[tc("1", "inbox_list")]), {"total_tokens": 5}, None)
                        if not done(ms) else (msg("办好了"), {"total_tokens": 5}, None))
        d = dm.Daemon(self.tg)
        d.handle_text("看看收件箱")
        self.assertEqual(d.task.state, "DONE")
        self.assertTrue(self.tg.edits, "进度应原地刷新")
        self.assertTrue(self.tg.sent[-1][1].endswith("办好了"))

    def test_confirm_gate_button_flow(self):
        self.run_script(lambda ms: (msg(calls=[tc("2", "write_file", path="notes/x.md", content="s")]),
                                    None, None) if not done(ms) else (msg("写好了"), None, None))
        d = dm.Daemon(self.tg)
        d.handle_text("写个笔记")
        self.assertIsNotNone(d.pending)
        self.assertTrue(self.tg.confirms, "确认应走按钮消息")
        self.assertFalse((self.tmp / "notes" / "x.md").exists())
        d.handle_text("确认")
        self.assertTrue((self.tmp / "notes" / "x.md").exists())
        self.assertIsNone(d.pending)

    def test_confirm_cancel_by_text(self):
        self.run_script(lambda ms: (msg(calls=[tc("3", "write_file", path="notes/y.md", content="y")]),
                                    None, None) if not done(ms) else (msg("已取消"), None, None))
        d = dm.Daemon(self.tg)
        d.handle_text("写个文件")
        d.handle_text("算了别写")
        self.assertFalse((self.tmp / "notes" / "y.md").exists())
        self.assertIsNone(d.pending)

    def test_reports_dir_auto_approved(self):
        self.run_script(lambda ms: (msg(calls=[tc("4", "write_file", path="reports/r.md", content="x")]),
                                    None, None) if not done(ms) else (msg("班次完成"), None, None))
        d = dm.Daemon(self.tg)
        d.handle_text("写报告")
        self.assertIsNone(d.pending)
        self.assertTrue((self.tmp / "reports" / "r.md").exists())

    def test_llm_error_marks_failed(self):
        self.run_script(lambda ms: (None, None, "网络错误"))
        d = dm.Daemon(self.tg)
        d.handle_text("在吗")
        self.assertEqual(d.task.state, "FAILED")
        self.assertIn("LLM 调用失败", self.tg.sent[-1][1])

    def test_recover_restores_waiting(self):
        self.run_script(lambda ms: (msg(calls=[tc("5", "write_file", path="notes/z.md", content="z")]),
                                    None, None) if not done(ms) else (msg("写好了"), None, None))
        d = dm.Daemon(self.tg)
        d.handle_text("写笔记")
        waiting_id = d.task.id
        # 模拟重启
        d2 = dm.Daemon(FakeTG())
        rec = tasks.recover(d2.tg)
        self.assertIsNotNone(rec)
        d2.restore_pending(rec)
        d2.handle_text("确认")
        self.assertTrue((self.tmp / "notes" / "z.md").exists())


def done(ms):
    return any(x.get("role") == "tool" for x in ms)


if __name__ == "__main__":
    unittest.main()
