"""Logger 日期滚动 + 周固化门禁。"""
import sys, unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import tempfile
import daemon
import scheduler


class FakeDT(datetime):
    _day = "2026-10-14"


class TestLoggerRoll(unittest.TestCase):
    def test_rolls_at_midnight(self):
        tmp = Path(tempfile.mkdtemp())
        daemon.LOGS_DIR = tmp
        lg = daemon.Logger()
        with mock.patch.object(daemon, "datetime", FakeDT):
            FakeDT._day = "2026-10-14"
            lg.log("boot", note="day1")
            FakeDT._day = "2026-10-15"
            lg.log("boot", note="day2")
        self.assertTrue((tmp / "2026-10-14.jsonl").exists())
        self.assertTrue((tmp / "2026-10-15.jsonl").exists())

    def test_reflect_weekday_gate(self):
        with mock.patch.object(scheduler, "datetime", FakeDT):
            FakeDT._day = "2026-10-14"  # 周三
            ran = []
            scheduler._weekly_reflect(type("D", (), {"run_reflect": lambda self: ran.append(1)})())
            self.assertFalse(ran, "周三不得触发固化")
            FakeDT._day = "2026-10-18"  # 周日
            scheduler._weekly_reflect(type("D", (), {"run_reflect": lambda self: ran.append(1)})())
            self.assertTrue(ran, "周日应触发")


def _now():
    y, m, d = map(int, FakeDT._day.split("-"))
    return datetime(y, m, d, 10, 0)


FakeDT.now = staticmethod(_now)
