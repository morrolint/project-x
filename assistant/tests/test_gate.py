"""确认门分级与路径守卫。"""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import tools


class TestGate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "reports").mkdir()
        tools.ASSISTANT_DIR = self.tmp

    def test_chat_narrow(self):
        self.assertTrue(tools.auto_approve("write_file", {"path": "reports/x.md"}))
        self.assertFalse(tools.auto_approve("write_file", {"path": "notes/x.md"}))
        self.assertFalse(tools.auto_approve("write_file", {"path": "skills/x.md"}))

    def test_wide_scope(self):
        self.assertTrue(tools.auto_approve("write_file", {"path": "skills/x/SKILL.md"}, wide=True))
        self.assertTrue(tools.auto_approve("write_file", {"path": "integrations/registry.json"}, wide=True))
        self.assertTrue(tools.auto_approve("write_file", {"path": "TASKS.md"}, wide=True))
        self.assertTrue(tools.auto_approve("write_file", {"path": "memory/obs.md"}, wide=True))

    def test_redlines_never(self):
        for p in ("docs/证件.md", ".secrets.env", "../outside.md", "x.pem"):
            self.assertFalse(tools.auto_approve("write_file", {"path": p}, wide=True), p)

    def test_safe_path_read_denies(self):
        self.assertIn("docs/", tools.execute("read_file", {"path": "docs/a.txt"}))
        self.assertIn("assistant/", tools.execute("read_file", {"path": "/etc/passwd"}))
