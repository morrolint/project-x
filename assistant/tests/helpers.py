"""测试公共设施：临时目录隔离 + FakeTG + LLM 脚桩。"""
import json
import sys
import tempfile
from pathlib import Path
from unittest import mock

AGENT_DIR = Path(__file__).resolve().parent.parent / "agent"
sys.path.insert(0, str(AGENT_DIR))


class FakeTG:
    """通道桩：记录发送/编辑/按钮，message_id 自增。"""
    def __init__(self):
        self.sent, self.edits, self.confirms, self.typings = [], [], [], []
        self._mid = 100

    def send_ex(self, t, reply_to=None):
        self._mid += 1
        self.sent.append((self._mid, t))
        return None, self._mid

    def send(self, t, reply_to=None):
        self.send_ex(t)
        return None

    def send_confirm(self, t, **kw):
        self._mid += 1
        self.confirms.append(t)
        return None, self._mid

    def edit_message(self, mid, t):
        self.edits.append((mid, t))
        return True, None

    def answer_callback(self, cid, text=""):
        pass

    def typing(self):
        self.typings.append(1)


def msg(c=None, calls=None):
    m = {"role": "assistant", "content": c}
    if calls:
        m["tool_calls"] = calls
    return m


def tc(i, n, **a):
    return {"id": i, "function": {"name": n, "arguments": json.dumps(a)}}


def isolate(tmp, modules=("dm", "tools", "memory", "daemon_state")):
    """把各模块的运行时路径指到临时目录。"""
    memory = sys.modules["memory"]
    memory.MEMORY_DIR = tmp / "memory"
    memory.MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    tools = sys.modules["tools"]
    tools.ASSISTANT_DIR = tmp
    tools.TASKS_FILE = tmp / "TASKS.md"
    tools.TASKS_FILE.write_text("# 任务收件箱\n\n## 待办\n\n## 已完成\n\n- （暂无）\n", encoding="utf-8")
    (tmp / "reports").mkdir(exist_ok=True)
    import tasks
    tasks.TASKS_DIR = tmp / "tasks"
    tasks.TASKS_DIR.mkdir(parents=True, exist_ok=True)
    import daemon_state
    daemon_state.STATE_FILE = tmp / "state.json"
    dm = sys.modules[modules] if modules in sys.modules else sys.modules["daemon"]
    dm.LOGS_DIR = tmp / "logs"


def stub_llm(script):
    """script: callable(messages) -> (msg, usage, err)"""
    import llm
    llm.chat = lambda ms, t=None: script(ms)
