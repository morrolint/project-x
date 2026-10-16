"""本体知识库检索（self-knowledge base）：让 daemon 能检索自己的架构/决策/技能/调研知识。

覆盖（L1-L3 知识文件，全部为助手自身的知识，不含用户敏感 docs/）：
- assistant/ARCHITECTURE.md · HANDOFF.md · HANDOFF-DOTS.md · docs/evolution.md（仓库根）
- docs/adr/*.md（决策记录）
- assistant/skills/*/SKILL.md（方法）
- assistant/research/*.md（调研档案）

实现：复用 memory.py 的 BM25 词元与评分思路（参数同款），文件集不同。
不覆盖：memory/（已有 memory.recall）、reports/（时效走 trending/activity）、docs/（宪法不变量 1）。
"""

import re
from pathlib import Path

from memory import _tokens as tokens  # 词元器与记忆层同源（拉丁词 + 中文 bigram）

ASSISTANT_DIR = Path(__file__).resolve().parent.parent
ROOT = ASSISTANT_DIR.parent
BM25_K1 = 1.5
BM25_B = 0.75
MIN_SCORE_ABS = 0.15
READ_CAP = 2500


def kb_files():
    """收集知识文件绝对路径列表（存在才收）。"""
    out = []
    for p in (ROOT / "assistant" / "ARCHITECTURE.md",
              ROOT / "HANDOFF.md",
              ROOT / "HANDOFF-DOTS.md",
              ROOT / "docs" / "evolution.md"):
        if p.exists():
            out.append(p)
    for pat in (ROOT / "docs" / "adr" , ROOT / "assistant" / "skills", ROOT / "assistant" / "research"):
        if pat.exists():
            out += sorted(pat.glob("*.md")) + sorted(pat.glob("*/SKILL.md"))
    seen, uniq = set(), []
    for p in out:
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp)
            uniq.append(rp)
    return uniq


def _relname(p):
    try:
        return str(p.relative_to(ROOT))
    except ValueError:
        return p.name


def kb_search(query, top=5):
    """BM25 检索知识文件，按行返回 ['相对路径#行号 行文本', ...]。无命中返回空串。"""
    files = kb_files()
    if not files:
        return "知识库为空。"
    docs = []  # (relname, lineno, line_text)
    for f in files:
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                s = line.strip()
                if s:
                    docs.append((_relname(f), i, s))
        except OSError:
            continue
    if not docs:
        return "知识库为空。"
    toks = tokens
    want = toks(query)
    if not want:
        return "查询词无法分词。"
    doc_toks = [toks(d[2]) for d in docs]
    n = len(docs)
    avgdl = sum(len(t) for t in doc_toks) / n
    df = {}
    for tset in doc_toks:
        for w in tset:
            df[w] = df.get(w, 0) + 1
    import math
    scored = []
    for idx, dt in enumerate(doc_toks):
        dl = len(dt) or 1
        score = 0.0
        for w in want:
            if w not in dt:
                continue
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            score += idf * (BM25_K1 + 1) / (1 + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl))
        scored.append((score, idx))
    scored = [s for s in scored if s[0] >= MIN_SCORE_ABS]
    if not scored:
        return ""
    scored.sort(reverse=True)
    cutoff = max(MIN_SCORE_ABS, 0.25 * scored[0][0])
    hits = [docs[i] for sc, i in scored[:top] if sc >= cutoff]
    if not hits:
        return ""
    return "\n".join(f"{name}#L{i} {line[:200]}" for name, i, line in hits)
