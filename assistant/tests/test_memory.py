"""记忆层 v0.2：打码 / 双层 / BM25 / 常备页。"""
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
import memory


class TestMemory(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        memory.MEMORY_DIR = self.tmp
        memory.MEMORY_DIR.mkdir(parents=True, exist_ok=True)

    def test_defend_redacts_keys(self):
        f, red = memory.retain("智谱 key 是 89220133.abcdef0123456789abcd 别弄丢", kind="fact")
        self.assertTrue(red)
        body = (self.tmp / "facts.md").read_text(encoding="utf-8")
        self.assertIn("[REDACTED", body)
        self.assertNotIn("89220133", body)

    def test_defend_sk_ghp(self):
        _, red = memory.retain("用 sk-abcdefghijklmnop123456 调用", kind="fact")
        self.assertTrue(red)

    def test_dual_layer_routing(self):
        memory.retain("用户偏好轻量方案", kind="fact")
        memory.retain("GitHub 直连超时走代理", kind="experience")
        self.assertTrue((self.tmp / "facts.md").exists())
        self.assertTrue(list(self.tmp.glob("????-??.md")))

    def test_bm25_recall(self):
        memory.retain("GitHub 直连超时走代理 7890", kind="experience")
        hits = memory.recall("代理端口")
        self.assertTrue(hits and "7890" in hits[0])

    def test_bm25_noise_dropped(self):
        memory.retain("早报每天 08:00 生成", kind="experience")
        self.assertEqual(memory.recall("zzz完全不相关qqq"), [])

    def test_profile_page(self):
        (self.tmp / "profile.md").write_text("# 档案\n- 中文交流\n", encoding="utf-8")
        self.assertIn("中文交流", memory.profile_text())
