"""state.json 读写薄封装（tools 与 daemon 共用，避免循环 import）。"""
import json
from pathlib import Path

STATE_FILE = Path(__file__).resolve().parent / "state.json"


def load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(**kv):
    st = load_state()
    st.update(kv)
    try:
        STATE_FILE.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
