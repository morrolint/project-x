#!/usr/bin/env python3
"""个人助手 v0 · 早报 / 晚间简报生成脚本。

用法：
    python3 report.py morning   [--date YYYY-MM-DD] [--output-dir DIR] [--force]
    python3 report.py evening   [--date YYYY-MM-DD] [--output-dir DIR] [--force]

约定（见 AGENTS.md 与 assistant/integrations/README.md）：
- 数据源全部是 integrations/sources/ 下的插件，本脚本不认识任何具体源；
  新增数据源 = 放一个插件文件 + registry.json 加一行，本脚本零改动。
- 任一数据源失败就跳过，并在报告"数据源与备注"注明，绝不中断整个报告。
- Trending 每次抓取写入 reports/YYYY-MM-DD-trending.json（sidecar），
  晚间对比读 morning 键，不依赖 markdown 表格（早报的表格会被自动化改写成逐项目解读）。
- 输出写到 <assistant>/reports/（默认），已存在同名报告则跳过（--force 覆盖）。
- 纯标准库，兼容系统 Python 3.9。
"""

import argparse
import html as htmllib
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ASSISTANT_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = ASSISTANT_DIR / "reports"
TASKS_FILE = ASSISTANT_DIR / "TASKS.md"
SOURCES_DIR = ASSISTANT_DIR / "integrations" / "sources"
if str(SOURCES_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCES_DIR))

from _common import fmt_k  # noqa: E402  （共享工具与各源插件同目录）

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 要闻分类关键词（v0 关键词归类，允许误差，报告内已注明）
TECH_KW = ["AI", "人工智能", "大模型", "芯片", "半导体", "算力", "机器人", "智能",
           "科技", "互联网", "数字化", "卫星", "火箭", "航天", "量子", "自动驾驶",
           "新能源", "电池", "平台", "系统", "软件"]
INTL_KW = ["美国", "白宫", "俄罗斯", "乌克兰", "日本", "韩国", "朝鲜", "印度", "泰国",
           "越南", "缅甸", "以色列", "加沙", "伊朗", "沙特", "也门", "胡塞", "菲律宾",
           "巴基斯坦", "阿富汗", "欧盟", "法国", "德国", "英国", "加拿大", "澳大利亚",
           "巴西", "阿根廷", "土耳其", "叙利亚", "伊拉克", "黎巴嫩", "保加利亚",
           "匈牙利", "墨西哥", "柬埔寨", "马来西亚", "印尼", "联合国", "世卫", "国际"]
CN_KW = ["我国", "中国", "国内", "全国", "国家", "中央", "国务院", "铁路", "国庆",
         "中秋", "财政", "央行", "海关", "能源局", "农业农村部"]
SPORTS_KW = ["夺冠", "冠军", "决赛", "联赛", "世界杯", "奥运", "锦标赛", "进球",
             "晋级", "赛季", "男单", "女单", "男团", "女团", "连胜"]

# 语义槽位 → 插件 ID（渲染函数按槽位取数；新增槽位属架构变更，走提案）
SLOTS = {"news": "source-60s", "trending": "source-github-trending", "hot": "source-weibo-hot"}


# ---------------------------------------------------------------- 数据源插件加载

def load_source_plugins():
    """发现并加载 sources/*.py 插件（_ 开头的为共享工具，跳过）。"""
    plugins = []
    for p in sorted(SOURCES_DIR.glob("*.py")):
        if p.name.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"assistant_source_{p.stem}", p)
        mod = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(mod)
        except Exception as e:  # noqa: BLE001 —— 单个插件坏不拖垮其他源
            print(f"⚠️ 数据源插件 {p.name} 加载失败：{type(e).__name__}: {e}", file=sys.stderr)
            continue
        if hasattr(mod, "fetch") and hasattr(mod, "ID"):
            plugins.append(mod)
    return plugins


def collect_sources(target_date, kind):
    """调用当班次所需插件。返回 (news, trending, hot, source_notes)。"""
    notes, results = [], {}
    for mod in load_source_plugins():
        if kind not in getattr(mod, "KINDS", ()):
            continue
        try:
            data, note = mod.fetch(target_date)
        except Exception as e:  # noqa: BLE001 —— 插件异常按该源失败处理
            data, note = None, f"插件异常（{type(e).__name__}: {e}）"
        results[mod.ID] = data
        if data:
            notes.append(f"✅ {note}")
        else:
            notes.append(f"⚠️ {mod.NAME}：{note}")
    if kind == "evening":
        notes.insert(0, "ℹ️ 中文要闻源为晨间聚合，晚间简报不含（白天动态以热搜晚间榜为准）")
    return (results.get(SLOTS["news"]), results.get(SLOTS["trending"]),
            results.get(SLOTS["hot"]), notes)


def trending_sidecar_path(out_dir, target_date):
    return Path(out_dir) / f"{target_date.isoformat()}-trending.json"


def update_trending_sidecar(out_dir, target_date, kind, trending):
    """把本次抓取合入 sidecar（morning/evening 各占一键），供晚间对比与将来复盘。"""
    path = trending_sidecar_path(out_dir, target_date)
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            data = {}
    data[kind] = {"fetched_at": datetime.now().isoformat(timespec="seconds"),
                  "repos": trending or []}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def load_morning_trending(out_dir, target_date):
    """读 sidecar 的 morning 键 → {name: (排名, 今日星数)}；缺失/损坏返回 None。"""
    path = trending_sidecar_path(out_dir, target_date)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    m = (data.get("morning") or {}).get("repos") or []
    if not m:
        return None
    return {r["name"]: (i, r.get("stars_today", 0)) for i, r in enumerate(m, 1)}


# ---------------------------------------------------------------- 推送

def load_secrets():
    """加载 assistant/.secrets.env（KEY=VALUE），已存在的环境变量优先。"""
    path = ASSISTANT_DIR / ".secrets.env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def push_telegram(text):
    """推送 HTML 文本到 Telegram。返回 (是否成功, 错误说明)。未配置则返回 (False, '未配置')。"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False, "未配置（.secrets.env 缺 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID）"
    if len(text) > 4000:
        text = text[:4000].rstrip() + "…"
    from _common import DEFAULT_PROXY
    proxy = os.environ.get("ASSISTANT_PROXY", DEFAULT_PROXY)
    px_args = ["-x", proxy] if proxy and proxy.lower() not in ("off", "none", "") else []
    payload = json.dumps({"chat_id": int(chat_id), "text": text, "parse_mode": "HTML",
                          "disable_web_page_preview": True})
    cmd = ["curl", "-sS", "--connect-timeout", "8", "--max-time", "20", *px_args,
           "-H", "Content-Type: application/json", "-d", payload,
           f"https://api.telegram.org/bot{token}/sendMessage"]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=25)
    except subprocess.TimeoutExpired:
        return False, "curl 超时"
    out = r.stdout.decode("utf-8", errors="replace")
    try:
        resp = json.loads(out)
        if resp.get("ok"):
            return True, ""
        return False, f"API: {resp.get('description', out[:120])}"
    except ValueError:
        return False, f"非 JSON 响应: {out[:120] or r.stderr.decode('utf-8', errors='replace')[:120]}"


def _esc(s):
    return htmllib.escape(str(s), quote=False)


def build_push_text(kind, target_date, out_path, news, trending, hot, pending):
    """构造推送摘要（HTML）。"""
    icon, title = ("🌅 早报", "早报") if kind == "morning" else ("🌙 晚间简报", "晚间简报")
    lines = [f"{icon} <b>{title} · {target_date.isoformat()}（{WEEKDAY_CN[target_date.weekday()]}）</b>", ""]
    if kind == "morning" and news:
        lines.append("🗞️ <b>要闻速览</b>")
        lines += [f"• {_esc(t[:60])}" for t in news["items"][:3]]
        lines.append("")
    if kind == "evening" and hot:
        lines.append("🔥 <b>热搜 Top3</b>")
        lines += [f"• {_esc(w['word'][:40])}" for w in hot[:3]]
        lines.append("")
    if trending:
        lines.append("🐙 <b>GitHub Trending Top3</b>")
        lines += [f"• {_esc(r['name'])} +{r['stars_today']:,} — {_esc(r['desc'][:50])}"
                  for r in trending[:3]]
        lines.append("")
    lines.append(f"📥 收件箱：{'无待办' if not pending else f'{len(pending)} 条待办'}")
    lines.append(f"📄 全文：<code>{_esc(out_path.name)}</code>")
    return "\n".join(lines)


# ---------------------------------------------------------------- 收件箱

def read_inbox():
    """读 TASKS.md 待办区。返回 (待办列表, 是否读到文件)。"""
    if not TASKS_FILE.exists():
        return [], False
    lines = TASKS_FILE.read_text(encoding="utf-8").splitlines()
    pending, in_todo = [], False
    for line in lines:
        if line.startswith("## "):
            in_todo = line.strip() == "## 待办"
            continue
        if in_todo and line.strip().startswith("- "):
            t = line.strip()[2:].strip()
            if t and "（示例格式）" not in t and "（暂无）" not in t:
                pending.append(t)
    return pending, True


# ---------------------------------------------------------------- 渲染

def classify(item):
    if any(k in item for k in SPORTS_KW):
        return "sports"
    has_tech = any(k in item for k in TECH_KW)
    has_intl = any(k in item for k in INTL_KW)
    has_cn = any(k in item for k in CN_KW)
    if has_tech and not has_intl:
        return "tech"
    if has_intl and not has_cn:
        return "intl"
    return "domestic"


def _trending_table(repos):
    lines = ["| # | 项目 | 简介 | 语言 | 今日 / 总星 |",
             "|---|---|---|---|---|"]
    for i, r in enumerate(repos, 1):
        fire = "🔥 " if i == 1 else ""
        desc = r["desc"].replace("|", "/")
        lines.append(f"| {i} | [{r['name']}]({r['url']}) | {desc} | {r['lang']} | "
                     f"{fire}+{r['stars_today']:,} / {fmt_k(r['stars_total'])} |")
    return lines


def _inbox_section(pending, has_file, empty_hint):
    if not has_file:
        return ["- ⚠️ 未找到 TASKS.md 收件箱文件。"]
    if not pending:
        return [f"- TASKS.md 无待办任务。有活就往里写一行，{empty_hint}。"]
    out = [f"- TASKS.md 有 {len(pending)} 条待办："]
    out += [f"  - （待处理）{t}" for t in pending]
    return out


def render_morning(target_date, news, trending, hot, notes):
    filename = f"{target_date.isoformat()}-早报.md"
    reports = Path(notes["output_dir"])
    issue = sum(1 for p in reports.glob("*-早报.md") if p.name < filename) + 1
    lines = [
        f"# 早报 · {target_date.isoformat()}（{WEEKDAY_CN[target_date.weekday()]}）",
        "",
        f"> 个人助手 · 第 {issue} 期（脚本版）",
        "",
        "## 🗞️ 要闻速览",
        "",
    ]
    if news:
        groups = {"domestic": [], "intl": [], "tech": [], "sports": []}
        for it in news["items"]:
            groups[classify(it)].append(it)
        lines.append("**国内**")
        lines += [f"- {t}" for t in groups["domestic"]] or ["- （本源今日无归入此类的条目）"]
        lines.append("")
        if groups["intl"]:
            lines.append("**国际**")
            lines += [f"- {t}" for t in groups["intl"]]
            lines.append("")
        if groups["tech"]:
            lines.append("**科技 / AI**")
            lines += [f"- {t}" for t in groups["tech"]]
            lines.append("")
        if groups["sports"]:
            lines.append(f"**体育**：{groups['sports'][0]}")
            lines.append("")
    else:
        lines += ["- ⚠️ 中文要闻源今日不可用，见文末备注。", ""]
    if hot:
        words = " / ".join(w["word"] for w in hot[:5])
        lines.append(f"**热搜快照**（微博实时）：{words}")
        lines.append("")
    lines += ["## 🐙 GitHub Trending 今日 Top 10", ""]
    if trending:
        lines += _trending_table(trending)
        langs = {}
        for r in trending:
            langs[r["lang"]] = langs.get(r["lang"], 0) + 1
        top_lang = max(langs, key=langs.get)
        lines.append("")
        lines.append(f"**点评**（脚本版）：Top10 中 {top_lang} 项目最多（{langs[top_lang]} 个）；"
                     f"增速第一为 [{trending[0]['name']}]({trending[0]['url']})"
                     f"（+{trending[0]['stars_today']:,} 星/日）。")
    else:
        lines.append("- ⚠️ GitHub Trending 今日不可用，见文末备注。")
    lines += ["", "## 🤖 AI 一句话", ""]
    if news and news.get("weiyu"):
        opener = f"「{news['weiyu']}」"
    else:
        opener = ""
    if hot and trending:
        closer = (f"今天的数据面：微博热搜第一「{hot[0]['word']}」；GitHub 热榜 "
                  f"{trending[0]['name']} 以 +{trending[0]['stars_today']:,} 星领跑。")
    else:
        closer = "今日部分数据源不可用，数据面见文末备注。"
    lines.append(f"{opener}——{closer}（v0 为脚本生成，观点层待 LLM 接入后增强）")
    lines += ["", "## 📥 收件箱", ""]
    lines += _inbox_section(notes["pending"], notes["has_tasks_file"],
                            "明早的我会自动处理（平时在会话里喊我处理也行）")
    lines += ["", "## 数据源与备注", ""]
    lines += [f"- {n}" for n in notes["sources"]]
    lines.append("- ℹ️ 要闻分组为关键词自动归类（脚本 v0），可能有误差；"
                 "科技/AI 深度条目由早报自动化以联网搜索补充。")
    return "\n".join(lines) + "\n"


def render_evening(target_date, trending, hot, morning_trending, notes):
    lines = [
        f"# 晚间简报 · {target_date.isoformat()}（{WEEKDAY_CN[target_date.weekday()]}）",
        "",
        "> 个人助手 · 晚间简报（脚本版）",
        "",
        "## 🌙 白天动态",
        "",
    ]
    if hot:
        lines.append("**微博热搜 · 晚间 Top10**")
        lines.append("")
        for i, w in enumerate(hot, 1):
            tag = f"（{w['label']}）" if w["label"] else ""
            num = f" · 热度 {w['num']:,}" if w["num"] else ""
            lines.append(f"{i}. {w['word']}{tag}{num}")
        lines.append("")
    else:
        lines.append("- ⚠️ 热搜源晚间抓取失败，见文末备注。")
        lines.append("")
    lines += ["## 🐙 Trending 复盘", ""]
    if not trending:
        lines.append("- ⚠️ GitHub Trending 晚间抓取失败，见文末备注。")
    elif morning_trending is None:
        lines.append("（未找到今日早报数据，无法对比；以下为晚间实时 Top10）")
        lines += _trending_table(trending)
    else:
        lines.append("| # | 项目 | 早间 → 晚间排名 | 变化 | 今日星数（早 → 晚） |")
        lines.append("|---|---|---|---|---|")
        new_names = []
        for i, r in enumerate(trending, 1):
            m = morning_trending.get(r["name"])
            if m is None:
                change = "🆕 NEW"
                new_names.append(r["name"])
                stars = f"— → +{r['stars_today']:,}"
            else:
                mrank, mstars = m
                diff = mrank - i
                if diff > 0:
                    change = f"↑{diff}"
                elif diff < 0:
                    change = f"↓{-diff}"
                else:
                    change = "＝"
                stars = f"+{mstars:,} → +{r['stars_today']:,}"
            lines.append(f"| {i} | [{r['name']}]({r['url']}) | {m[0] if m else '—'} → {i} "
                         f"| {change} | {stars} |")
        kept = sum(1 for r in trending if r["name"] in morning_trending)
        lines.append("")
        summary = (f"**复盘**（脚本版）：早间 Top10 有 {kept} 个晚间仍在榜；"
                   f"新进 {len(new_names)} 个"
                   + (f"（{ '、'.join(new_names[:3]) }{'…' if len(new_names) > 3 else ''}）" if new_names else "")
                   + f"；晚间增速第一 [{trending[0]['name']}]({trending[0]['url']})"
                     f"（+{trending[0]['stars_today']:,} 星/日）。")
        lines.append(summary)
    lines += ["", "## 📥 收件箱巡检", ""]
    lines += _inbox_section(notes["pending"], notes["has_tasks_file"],
                            "今晚的自动化会巡检处理")
    lines += ["", "## 数据源与备注", ""]
    lines += [f"- {n}" for n in notes["sources"]]
    if trending and morning_trending is not None:
        lines.append(f"- Trending 对比基准：{target_date.isoformat()}-trending.json · morning 键")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 主流程

def main():
    parser = argparse.ArgumentParser(description="个人助手 早报/晚间简报 生成脚本")
    parser.add_argument("kind", choices=["morning", "evening"])
    parser.add_argument("--date", default=date.today().isoformat(), help="YYYY-MM-DD，默认今天")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--force", action="store_true", help="覆盖已存在的报告")
    args = parser.parse_args()

    try:
        target_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"错误：日期格式应为 YYYY-MM-DD，得到 {args.date}", file=sys.stderr)
        return 1
    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{target_date.isoformat()}-{'早报' if args.kind == 'morning' else '晚间简报'}.md"
    out_path = out_dir / filename
    if out_path.exists() and not args.force:
        print(f"跳过：{out_path} 已存在（--force 可覆盖）")
        return 0

    print(f"抓取数据源（{args.kind} · {target_date.isoformat()}）…")
    news, trending, hot, source_notes = collect_sources(target_date, args.kind)
    update_trending_sidecar(out_dir, target_date, args.kind, trending)
    pending, has_tasks_file = read_inbox()
    notes = {"output_dir": str(out_dir), "pending": pending,
             "has_tasks_file": has_tasks_file, "sources": source_notes}

    if args.kind == "morning":
        content = render_morning(target_date, news, trending, hot, notes)
    else:
        morning_trending = load_morning_trending(out_dir, target_date)
        content = render_evening(target_date, trending, hot, morning_trending, notes)

    out_path.write_text(content, encoding="utf-8")
    ok = sum(1 for n in source_notes if n.startswith("✅"))
    print(f"完成：{out_path}")
    print(f"数据源 {ok}/{len(source_notes)} 可用；收件箱待办 {len(pending)} 条")
    for n in source_notes:
        print("  " + n.split("（")[0][:80])
    # Telegram 推送（未配置则静默跳过；失败不阻断，备注进报告与 stdout）
    load_secrets()
    push_ok, push_err = push_telegram(
        build_push_text(args.kind, target_date, out_path, news, trending, hot, pending))
    if push_ok:
        print("Telegram 推送成功")
    else:
        warn = f"⚠️ Telegram 推送失败：{push_err}"
        print(warn)
        with open(out_path, "a", encoding="utf-8") as f:
            f.write(f"\n- {warn}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 —— 未预期异常才非零退出
        import traceback
        traceback.print_exc()
        sys.exit(1)
