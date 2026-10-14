"""调度器：班次窗口 / 提醒到期 / offset 状态。"""
import sys, tempfile, time, unittest
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import daemon_state
import scheduler
import daemon


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        daemon_state.STATE_FILE = self.tmp / "state.json"

    def test_shift_window(self):
        dd = {"morning": "2026-10-14"}
        self.assertTrue(scheduler._should_fire_shift(datetime(2026, 10, 15, 8, 5), "morning", dd))
        self.assertFalse(scheduler._should_fire_shift(datetime(2026, 10, 14, 8, 5), "morning", dd))
        self.assertTrue(scheduler._should_fire_shift(datetime(2026, 10, 14, 21, 5), "evening", dd))
        self.assertFalse(scheduler._should_fire_shift(datetime(2026, 10, 14, 9, 5), "morning", {}))

    def test_reminders_push_and_consume(self):
        from helpers import FakeTG
        import tools
        r = tools.execute("remind_in", {"minutes": 1, "text": "测试提醒"})
        self.assertIn("已设提醒", r)
        rems = daemon_state.load_state()["reminders"]
        rems[0]["due"] = time.time() - 1
        daemon_state.save_state(reminders=rems)
        tg = FakeTG()
        scheduler._check_reminders(type("D", (), {"_say": lambda self, t, reply_to=None, assistant_out=None:
                                                 tg.sent.append(t), "log": None, "tg": tg})())
        self.assertTrue(any("⏰ 提醒：测试提醒" in t for t in tg.sent))
        self.assertFalse(daemon_state.load_state().get("reminders"))

    def test_offset_state(self):
        daemon.save_state(update_offset=12345)
        self.assertEqual(daemon.load_state()["update_offset"], 12345)
