#!/usr/bin/env python3
"""registry.json 校验器：把四铁律从纪律变成机制。

用法：python3 assistant/integrations/check_registry.py
时机：改过 registry.json 或增删插件文件后跑一次（自动化收件箱巡检动 registry 前后也应各跑一次）。
退出码：0=全部通过，1=有问题（逐条列出）。

检查项（与 README.md 契约表同步维护）：
1. JSON 合法、id 唯一、type/status 在合法枚举内；
2. impl 指针：填了 impl 的条目，目标文件必须存在（`#函数名` 片段只查文件）；
   active 条目必须有 impl；
3. report-source 双向对账：sources/ 下每个插件（_ 开头为共享工具，跳过）的 ID 常量
   必须登记在册；登记条目的 impl 文件里的 ID 常量必须与 registry id 一致；
4. push-channel 双向对账：channels/ 下同上；
5. skill 条目：impl 文件须含 frontmatter(name/description) 与「## 方法」节，且不含可执行代码。
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # assistant/integrations/
REGISTRY = HERE / "registry.json"
SOURCES_DIR = HERE / "sources"
CHANNELS_DIR = HERE / "channels"

TYPES = {"report-source", "push-channel", "skill", "capability", "channel-inbound", "memory"}
STATUS = {"proposed", "evaluating", "active", "rejected", "retired"}

errors = []


def err(msg):
    errors.append(msg)
    print(f"  ✗ {msg}")


def resolve_impl(impl):
    """impl 相对 integrations/ 解析；`路径#函数名` 只查文件部分。"""
    return (HERE / impl.split("#", 1)[0]).resolve()


def plugin_ids(directory):
    """目录下非 _ 插件的 ID 常量。返回 {id 或 "??文件名": 文件名}。"""
    out = {}
    if not directory.exists():
        return out
    for f in sorted(directory.glob("*.py")):
        if f.name.startswith("_"):
            continue
        m = re.search(r'^ID\s*=\s*"([^"]+)"', f.read_text(encoding="utf-8"), re.M)
        out[m.group(1) if m else f"??{f.name}"] = f.name
    return out


def check():
    print(f"== registry 校验：{REGISTRY} ==")
    if not REGISTRY.exists():
        err("registry.json 不存在")
        return
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except ValueError as e:
        err(f"JSON 解析失败：{e}")
        return
    entries = data.get("integrations")
    if not isinstance(entries, list):
        err("缺 integrations 数组")
        return
    print(f"  共 {len(entries)} 条")

    seen_ids = set()
    for e in entries:
        eid = e.get("id", "??缺id")
        # 1) 基础字段与枚举
        if not e.get("id"):
            err("有条目缺 id")
            continue
        if eid in seen_ids:
            err(f"{eid}: id 重复")
        seen_ids.add(eid)
        if e.get("type") not in TYPES:
            err(f"{eid}: type 非法（{e.get('type')!r}），合法值：{sorted(TYPES)}")
        if e.get("status") not in STATUS:
            err(f"{eid}: status 非法（{e.get('status')!r}），合法值：{sorted(STATUS)}")
        # 2) impl 指针
        impl = e.get("impl")
        if impl:
            p = resolve_impl(impl)
            if not p.exists():
                err(f"{eid}: impl 文件不存在 {impl}")
            elif eid.startswith("source-") and re.search(r'^ID\s*=\s*"([^"]+)"',
                                                         p.read_text(encoding="utf-8"), re.M):
                got = re.search(r'^ID\s*=\s*"([^"]+)"', p.read_text(encoding="utf-8"), re.M).group(1)
                if got != eid:
                    err(f"{eid}: impl 文件里的 ID 常量是 {got!r}，与 registry id 不一致")
        elif e.get("status") == "active":
            err(f"{eid}: active 但没有 impl 指针")

    # 3) report-source 双向对账
    if SOURCES_DIR.exists():
        for pid, fname in plugin_ids(SOURCES_DIR).items():
            if pid.startswith("??"):
                err(f"sources/{fname}：缺 ID 常量")
            elif pid not in seen_ids:
                err(f"sources/{fname}（ID={pid}）：插件在目录里，registry 里没有登记")
    # 4) push-channel 双向对账
    if CHANNELS_DIR.exists():
        for pid, fname in plugin_ids(CHANNELS_DIR).items():
            if pid.startswith("??"):
                err(f"channels/{fname}：缺 ID 常量")
            elif pid not in seen_ids:
                err(f"channels/{fname}（ID={pid}）：插件在目录里，registry 里没有登记")

    # 5) skill 契约抽查
    for e in entries:
        if e.get("type") == "skill" and e.get("impl"):
            p = resolve_impl(e["impl"])
            if not p.exists():
                continue  # 上面已报
            t = p.read_text(encoding="utf-8")
            if not re.match(r"^---\n", t) or "name:" not in t.split("---")[1]:
                err(f"{e['id']}: skill 缺 frontmatter(name/description)")
            if "## 方法" not in t or "## 来源" not in t:
                err(f"{e['id']}: skill 缺「方法/来源」节")
            if re.search(r"^```python|^#!/usr/bin/env", t, re.M):
                err(f"{e['id']}: skill 含可执行代码（契约禁止）")

    if errors:
        print(f"== 未通过：{len(errors)} 个问题 ==")
        sys.exit(1)
    print("== 全部通过 ✅ ==")


if __name__ == "__main__":
    check()
