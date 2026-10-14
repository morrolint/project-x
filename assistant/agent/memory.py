"""markdown 记忆层 v0.2：BM25 召回 + 双层结构 + 写入防护。

设计吸收自 vectorize-io/hindsight（2026-10-14 深读，见 research/2026-10-14-hindsight-深读.md）：
- 双层：facts（稳定事实/偏好，facts.md）+ experiences（时序日志，YYYY-MM.md）
- BM25 关键词评分（hindsight recall 四路中的 Keyword 路，agentmemory 基准实测 86%+ 的来源）
- Memory Defense 基础版：retain 前对密钥模式打码
- profile.md 常备页（hindsight mental model 极简版）：daemon 每轮注入，零检索成本
第二批后段（需调度器）：observations 后台固化——相关事实合并为带证据计数的"信念"，求精不覆盖。
"""

import math
import re
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).resolve().parent.parent / "memory"

BM25_K1 = 1.5
BM25_B = 0.75
MIN_SCORE_ABS = 0.15  # 绝对下限（防零分混入）；再叠加相对阈值 = 25% × 最高分（适配语料规模）

# Memory Defense 基础版：常见凭据形态（打码优先于拦截——保留记忆价值，去掉敏感本体）
_SECRET_RULES = [
    (re.compile(r"(sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|gho_[A-Za-z0-9]{20,}|xox[bpo]-[A-Za-z0-9-]{10,})"),
     "[REDACTED:key]"),
    (re.compile(r"(?i)\b((?:api[_-]?key|token|secret|password)\s*[=:]\s*)(\S{8,})"), r"\1[REDACTED]"),
    (re.compile(r"\b([0-9]{8}\.[A-Za-z0-9]{16,})\b"), "[REDACTED:key]"),  # 智谱 key 形态
]


def defend(text):
    """打码密钥形态，返回 (清洗后文本, 是否发生打码)。"""
    hit = False
    for rule, repl in _SECRET_RULES:
        new = rule.sub(repl, text)
        hit = hit or new != text
        text = new
    return text, hit


def retain(text, kind="experience"):
    """写入一条记忆。kind: experience（默认，月度日志）/ fact（稳定事实，facts.md）。
    返回 (文件名, 是否发生密钥打码)。"""
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    text, redacted = defend(str(text).strip())
    if not text:
        return "(空)", False
    ts = datetime.now()
    if kind == "fact":
        f = MEMORY_DIR / "facts.md"
        if not f.exists():
            f.write_text("# 稳定事实与偏好\n\n", encoding="utf-8")
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(f"- {text}\n")
        return f.name, redacted
    f = MEMORY_DIR / f"{ts:%Y-%m}.md"
    if not f.exists():
        f.write_text(f"# 记忆 · {ts:%Y-%m}\n", encoding="utf-8")
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(f"- [{ts:%m-%d %H:%M}] {text}\n")
    return f.name, redacted


def profile_text():
    """常备页内容（不存在则空串）。daemon 每轮注入——hindsight mental model 的零检索版。"""
    p = MEMORY_DIR / "profile.md"
    if not p.exists():
        return ""
    t = p.read_text(encoding="utf-8").strip()
    return t[:1500]


# ---------------------------------------------------------------- BM25 召回

def _tokens(text):
    """拉丁词 + 中文相邻字 bigram（多语言原生：中文实体不做转写，hindsight 同款原则）。"""
    latin = {t.lower() for t in re.findall(r"[A-Za-z0-9_]+", text)}
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    return latin | {cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1)}


def _docs():
    """全部可召回行：(文件名, 行号, 行文本)。facts 在前（同分时稳定事实优先）。"""
    if not MEMORY_DIR.exists():
        return []
    out = []
    files = ([MEMORY_DIR / "facts.md"] if (MEMORY_DIR / "facts.md").exists() else []) \
        + sorted(MEMORY_DIR.glob("????-??.md"))
    for f in files:
        try:
            for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
                s = line.strip()
                if s.startswith("- "):
                    out.append((f.name, i, s))
        except OSError:
            continue
    return out


def recall(query, top=5):
    """BM25 召回，返回 ['文件名#行号 内容', ...]（按相关性降序，低于 MIN_SCORE 丢弃）。"""
    docs = _docs()
    if not docs:
        return []
    want = _tokens(query)
    if not want:
        return []
    toks = [_tokens(d[2]) for d in docs]
    n = len(docs)
    avgdl = sum(len(t) for t in toks) / n
    df = {}
    for t in toks:
        for w in t:
            df[w] = df.get(w, 0) + 1
    scored = []
    for idx, dtoks in enumerate(toks):
        dl = len(dtoks) or 1
        score = 0.0
        for w in want:
            if w not in dtoks:
                continue
            tf = 1  # 词元集合无重复；命中即 1
            idf = math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
            score += idf * tf * (BM25_K1 + 1) / (tf + BM25_K1 * (1 - BM25_B + BM25_B * dl / avgdl))
        scored.append((score, idx))
    scored.sort(reverse=True)
    if not scored:
        return []
    cutoff = max(MIN_SCORE_ABS, 0.25 * scored[0][0])  # 相对阈值：与最相关结果差距过大的丢弃
    return [f"{docs[i][0]}#L{docs[i][1]} {docs[i][2]}"
            for sc, i in scored[:top] if sc >= cutoff]
