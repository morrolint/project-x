"""自进化引擎 v1（cap-self-evolution，ADR 见 proposals/2026-10-16-cap-self-evolution.md）。

闭环：任务完成 → 提炼 trace → LLM 判断"可复用模式？" → 产出 SKILL.md（skills/，宽口径免确认）
→ registry 程序化登记（LLM 不碰 registry，代码负责簿记）→ check_registry 过门 → 失败整体回滚。
安全：internal 口径执行；state 开关（self_evolve）；每日限 3 次；docs/ 与密钥由路径守卫永拦。
"""

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ASSISTANT_DIR = AGENT_DIR.parent
REGISTRY = ASSISTANT_DIR / "integrations" / "registry.json"
CHECKER = ASSISTANT_DIR / "integrations" / "check_registry.py"
EVOLUTION_LOG = ASSISTENT_LOG = ASSISTANT_DIR.parent / "docs" / "evolution.md"

MAX_PER_DAY = 3


def _llm(prompt):
    import llm
    return llm.chat([{"role": "system",
                      "content": "你是 Project X 的经验固化器：从任务轨迹中识别可复用模式，"
                                 "按仓库技能契约（纯方法 markdown）产出技能。拿不准就说 NO。"},
                     {"role": "user", "content": prompt}])


def trace_summary(msgs, cap=2600):
    """从对话消息提取工具调用轨迹摘要（喂给提炼 LLM）。"""
    lines = []
    for m in msgs:
        for c in m.get("tool_calls") or []:
            fn = c.get("function") or {}
            lines.append(f"工具 {fn.get('name')} 参数 {str(fn.get('arguments'))[:120]}")
        if m.get("role") == "tool":
            lines.append(f"  结果 {str(m.get('content'))[:100]}")
    text = "\n".join(lines)[:cap]
    return text or "（无可提取轨迹）"


def _parse(response):
    """解析 LLM 输出：NO → None；(NAME 行 + <SKILL>…</SKILL>) → (name, body)。"""
    t = (response or "").strip()
    if not t or t.upper().startswith("NO"):
        return None
    m_name = re.search(r"NAME:\s*([a-z0-9-]{3,40})", t)
    m_body = re.search(r"<SKILL>\n?(.*?)\n?</SKILL>", t, re.S)
    if not (m_name and m_body):
        return None
    body = m_body.group(1).strip()
    if "## 方法" not in body or "## 来源" not in body:
        return None  # 契约不齐视同 NO
    return m_name.group(1), body


def _registry_has(skill_id):
    try:
        d = json.loads(REGISTRY.read_text(encoding="utf-8"))
        return any(i.get("id") == skill_id for i in d.get("integrations", []))
    except (OSError, ValueError):
        return True  # 读不了当作已存在，宁可不写


def _registry_append(skill_id, skill_name, label):
    d = json.loads(REGISTRY.read_text(encoding="utf-8"))
    d["integrations"].append({
        "id": f"skill-{skill_id}",
        "type": "skill",
        "impl": f"../skills/{skill_id}/SKILL.md",
        "status": "active",
        "added": datetime.now().strftime("%Y-%m-%d"),
        "provenance": f"经验固化（cap-self-evolution v1）：来自任务「{label}」，自动提炼并过 check_registry 门",
    })
    REGISTRY.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def _check_pass():
    r = subprocess.run([sys.executable, str(CHECKER)], capture_output=True, timeout=60)
    return r.returncode == 0


def _evolution_log(entry):
    EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EVOLUTION_LOG, "a", encoding="utf-8") as f:
        f.write(f"- {entry}\n")


def crystallize(msgs, label, log=None):
    """主入口：提炼→落盘→登记→过门→日志。返回人类可读结果。"""
    today = datetime.now().strftime("%Y-%m-%d")
    from daemon_state import load_state
    st = load_state()
    if not st.get("self_evolve", True):
        return "自进化已关闭，跳过固化。"
    used = st.get("evolve_used", {}).get(today, 0)
    if used >= MAX_PER_DAY:
        return f"今日固化已达上限（{MAX_PER_DAY}），跳过。"

    prompt = (f"任务「{label}」的执行轨迹如下。判断其中是否包含**可复用的方法模式**"
              f"（同类任务会再次用到的步骤/管线/纪律）。\n若无可复用模式，只回答 NO。\n"
              f"若有，严格按两段输出：\n第一行 NAME: kebab-case-名\n"
              f"然后 <SKILL> 与 </SKILL> 之间输出完整 SKILL.md 内容，"
              f"必须含 frontmatter（name/description）与「## 方法」「## 来源」节，纯方法不含代码。\n\n"
              f"轨迹：\n{trace_summary(msgs)}")
    msg, usage, err = _llm(prompt)
    if err:
        return f"固化失败（LLM）：{err}"
    parsed = _parse((msg or {}).get("content"))
    if not parsed:
        if log:
            log.log("evolve", result="NO（无可复用模式或格式不合规）", label=label)
        return "本任务无可复用模式，不固化。"
    name, body = parsed
    if _registry_has(f"skill-{name}"):
        return f"技能 {name} 已存在（查重命中），不重复固化。"

    # 落盘
    skill_dir = ASSISTANT_DIR / "skills" / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"{body}\n\n## 来源\n\n经验固化（cap-self-evolution v1）：任务「{label}」，{datetime.now():%Y-%m-%d}。\n",
        encoding="utf-8")
    try:
        _registry_append(name, name, label)
    except (OSError, ValueError, KeyError) as e:
        import shutil
        shutil.rmtree(skill_dir, ignore_errors=True)
        return f"registry 登记失败已回滚：{e}"
    if not _check_pass():
        import shutil
        shutil.rmtree(skill_dir, ignore_errors=True)
        # registry 回滚
        d = json.loads(REGISTRY.read_text(encoding="utf-8"))
        d["integrations"] = [i for i in d["integrations"] if i.get("id") != f"skill-{name}"]
        REGISTRY.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"技能 {name} 未过 check_registry 门，已整体回滚。"

    # 记账 + 进化日志
    used += 1
    evolve_used = st.get("evolve_used", {})
    evolve_used[today] = used
    save = dict(st)
    save["evolve_used"] = evolve_used
    from daemon_state import save_state
    save_state(**save)
    _evolution_log(f"[{datetime.now():%Y-%m-%d %H:%M}] 经验固化：{name}（任务「{label}」）——"
                   f"skill 落盘 + registry 登记，check_registry 通过。参照系：契约校验器。")
    if log:
        log.log("evolve", result=f"固化 skill-{name}", label=label)
    return f"🧬 经验固化：新技能 {name} 已上线（过契约校验），见 docs/evolution.md"
