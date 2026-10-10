"""markdown 记忆层（v1 最小版）：按月归档 + 词元重合召回。

第二批计划（HANDOFF §六）：BM25 打分、四层分类（agentmemory）、写入前隐私过滤。
目录：assistant/memory/YYYY-MM.md，每条一行：- [MM-DD HH:MM] 内容
"""

import re
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"


def retain(text):
    """写入一条记忆，返回所在文件名。"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now()
    f = MEMORY_DIR / f"{ts:%Y-%m}.md"
    if not f.exists():
        f.write_text(f"# 记忆 · {ts:%Y-%m}\n", encoding="utf-8")
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(f"- [{ts:%m-%d %H:%M}] {text.strip()}\n")
    return f.name


def _tokens(text):
    """拉丁词按空格/标点切；中文取相邻字 bigram（召回够用，第二批换 BM25）。"""
    latin = {t.lower() for t in re.findall(r"[A-Za-z0-9_]+", text)}
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    return latin | {cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)}


def recall(query, top=5):
    """按词元重合度召回记忆行，返回 ['文件#行号 内容', ...]。"""
    if not MEMORY_DIR.exists():
        return []
    want = _tokens(query)
    if not want:
        return []
    scored = []
    for f in sorted(MEMORY_DIR.glob("*.md")):
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if not s.startswith("- "):
                continue
            score = len(want & _tokens(s))
            if score:
                scored.append((score, f.name, i, s))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    return [f"{name}#L{i} {line}" for _, name, i, line in scored[:top]]
