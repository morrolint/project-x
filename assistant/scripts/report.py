#!/usr/bin/env python3
"""个人助手 v0 · 早报 / 晚间简报生成脚本。

用法：
    python3 report.py morning   [--date YYYY-MM-DD] [--output-dir DIR] [--force]
    python3 report.py evening   [--date YYYY-MM-DD] [--output-dir DIR] [--force]

约定（见 AGENTS.md）：
- 任一数据源失败就跳过，并在报告"数据源与备注"注明，绝不中断整个报告。
- 输出写到 <assistant>/reports/（默认），已存在同名报告则跳过（--force 覆盖）。
- 纯标准库，兼容系统 Python 3.9。
"""

import argparse
import html as htmllib
import json
import os
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ASSISTANT_DIR = SCRIPT_DIR.parent
DEFAULT_OUTPUT_DIR = ASSISTANT_DIR / "reports"
TASKS_FILE = ASSISTANT_DIR / "TASKS.md"

DEFAULT_PROXY = "http://127.0.0.1:7892"  # SpeedCat VPN；ASSISTANT_PROXY=off 可禁用
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

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


# ---------------------------------------------------------------- HTTP
# 用系统 curl 而非 urllib：macOS 系统 Python(LibreSSL) 与本地代理栈存在 TLS 兼容问题，
# curl 实测全部源直连/代理均稳定。

def http_get(url, timeout=15, allow_proxy=True, extra_headers=None, retries=2):
    """GET 一个 URL 返回文本。直连失败走代理，每条路径重试一次。返回 (文本|None, 途径说明|None, 错误说明)。"""
    import time
    proxy = os.environ.get("ASSISTANT_PROXY", DEFAULT_PROXY)
    if proxy and proxy.lower() in ("off", "none", ""):
        allow_proxy = False
    headers = ["-A", UA, "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8"]
    if extra_headers:
        for k, v in extra_headers.items():
            headers += ["-H", f"{k}: {v}"]
    paths = [("直连", [])]
    if allow_proxy and proxy:
        paths.append(("代理 " + proxy, ["-x", proxy]))
    last_err = "未知错误"
    for label, px_args in paths:
        for attempt in range(1, retries + 1):
            cmd = ["curl", "-sSL", "--connect-timeout", "8", "--max-time", str(timeout),
                   *headers, *px_args, url]
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=timeout + 5)
            except subprocess.TimeoutExpired:
                last_err = "curl 超时"
                continue
            if r.returncode == 0 and r.stdout:
                return r.stdout.decode("utf-8", errors="replace"), label, None
            err_detail = r.stderr.decode("utf-8", errors="replace").strip().splitlines()
            last_err = f"curl exit {r.returncode}: {err_detail[-1] if err_detail else '无输出'}"
            if attempt < retries:
                time.sleep(1)
    return None, None, last_err


# ---------------------------------------------------------------- 数据源

def fetch_60s(target_date):
    """每天60秒读懂世界。返回 (dict|None, note)。"""
    index_html, via, err = http_get("https://blog.intelexe.cn/")
    if index_html is None:
        return None, f"索引页抓取失败（{err}）"
    post_url = None
    for m in re.finditer(r'<a[^>]+href="(https://blog\.intelexe\.cn/archives/\d+)"[^>]*>(.*?)</a>',
                         index_html, re.S):
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if target_date.isoformat() in title and "读懂世界" in title:
            post_url = m.group(1)
            break
    if not post_url:
        return None, f"索引页未找到 {target_date.isoformat()} 的文章（可能尚未发布）"
    post_html, _, err = http_get(post_url)
    if post_html is None:
        return None, f"正文抓取失败（{err}）"
    seg = post_html.split('class="entry-content"', 1)
    if len(seg) < 2:
        return None, "正文结构变化：未找到 entry-content"
    body = seg[1]
    cut = body.find("<!-- .entry-content")
    if cut > 0:
        body = body[:cut]
    paras = []
    for pm in re.finditer(r"<p[^>]*>(.*?)</p>", body, re.S):
        text = htmllib.unescape(re.sub(r"<[^>]+>", "", pm.group(1))).strip()
        if text:
            paras.append(text)
    numbered = {}
    for p in paras:
        m = re.match(r"^(\d{1,2})、\s*(.*)", p)
        if m:
            text = m.group(2).rstrip("；;。") + "。"
            numbered.setdefault(int(m.group(1)), text)
    items = [numbered[d] for d in sorted(numbered)]
    weiyu = next((p for p in paras if p.startswith("【微语】")), "")
    weiyu = weiyu.replace("【微语】", "").strip()
    if not items:
        return None, "正文中未解析出编号条目（页面结构可能变化）"
    note = f"[每天60秒读懂世界]({post_url}) 完整 {len(items)} 条" + ("，含微语" if weiyu else "")
    if via and "直连" not in via:
        note += f"（经{via}）"
    return {"items": items, "weiyu": weiyu, "url": post_url}, note


def _fmt_k(n):
    """278411 -> 278k；18097 -> 18.1k；1200000 -> 1.2M"""
    if n >= 1_000_000:
        s = f"{n / 1e6:.1f}M"
    elif n >= 100_000:
        s = f"{n / 1e3:.0f}k"
    else:
        s = f"{n / 1e3:.1f}k"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def fetch_trending():
    """GitHub Trending Top10。返回 (list|None, note)。"""
    page, via, err = http_get("https://github.com/trending", timeout=15)
    if page is None:
        return None, f"抓取失败（{err}）"
    rows = re.findall(r'<article class="Box-row">(.*?)</article>', page, re.S)
    repos = []
    for r in rows:
        name = re.search(r'<h2[^>]*>.*?href="/([^"]+)"', r, re.S)
        if not name:
            continue
        desc = re.search(r'<p class="col-9[^"]*">\s*(.*?)\s*</p>', r, re.S)
        lang = re.search(r'itemprop="programmingLanguage">([^<]+)<', r)
        stars = re.search(r'href="/[^"]+/stargazers[^"]*".*?</svg>\s*([\d,]+)', r, re.S)
        today = re.search(r"([\d,]+)\s+stars today", r)
        repos.append({
            "name": name.group(1),
            "url": "https://github.com/" + name.group(1),
            "desc": htmllib.unescape(re.sub(r"<[^>]+>", "", desc.group(1)).strip()) if desc else "",
            "lang": lang.group(1) if lang else "—",
            "stars_total": int(stars.group(1).replace(",", "")) if stars else 0,
            "stars_today": int(today.group(1).replace(",", "")) if today else 0,
        })
    repos.sort(key=lambda r: r["stars_today"], reverse=True)
    repos = repos[:10]  # 整页解析后按今日星数排序再截 Top10（页面顺序不按星数排，先截会漏高增速项目）
    for r in repos:  # 表格可读性：简介过长截断
        if len(r["desc"]) > 60:
            r["desc"] = r["desc"][:60].rstrip() + "…"
    if not repos:
        return None, "页面结构变化：未解析出任何仓库"
    note = "[github.com/trending](https://github.com/trending) 实时抓取 Top10"
    if via and "直连" not in via:
        note += f"（经{via}）"
    return repos, note


def fetch_weibo_hot():
    """微博热搜 Top10。主源：微博官方接口；备用：tophub。返回 (list|None, note)。"""
    html, via, err = http_get(
        "https://weibo.com/ajax/side/hotSearch", timeout=10, allow_proxy=False,
        extra_headers={"Referer": "https://weibo.com/"})
    if html:
        try:
            data = json.loads(html)
            items = [it for it in data["data"]["realtime"] if not it.get("is_ad")]
            hot = [{"word": it["word"].strip().strip("#"),
                    "num": int(it.get("num") or 0),
                    "label": it.get("icon_desc") or ""} for it in items[:10]]
            if hot:
                return hot, "[微博热搜](https://s.weibo.com/top/summary) 官方接口实时抓取 Top10"
        except (ValueError, KeyError, TypeError) as e:
            err = f"接口解析失败（{type(e).__name__}）"
    # 备用源 tophub
    html2, _, err2 = http_get("https://tophub.today/n/KqndgxeLl9", timeout=10)
    if html2:
        tds = re.findall(r'<td class="al"[^>]*>(.*?)</td>', html2, re.S)
        words = []
        for td in tds:
            t = htmllib.unescape(re.sub(r"<[^>]+>", "", td)).strip()
            t = re.sub(r"\d+\.\s*", "", t).strip()
            if t and "加载" not in t and "快照" not in t:
                words.append({"word": t, "num": 0, "label": ""})
        if words:
            return words[:10], "[tophub](https://tophub.today) 快照 Top10（备用源，无热度值）"
    return None, f"抓取失败（{err}；备用源也不可用：{err2}）"


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
                     f"{fire}+{r['stars_today']:,} / {_fmt_k(r['stars_total'])} |")
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


# ---- 晚间简报：与早报 Trending 对比 ----

def _parse_morning_trending(morning_path):
    """从早报 markdown 解析 trending 表：{name: (rank, stars_today:int)}。"""
    if not morning_path.exists():
        return None
    try:
        text = morning_path.read_text(encoding="utf-8")
    except OSError:
        return None
    result = {}
    rank = 0
    for line in text.splitlines():
        m = re.match(r"\|\s*(\d+)\s*\|\s*\[([^\]]+)\]\(https://github\.com/[^)]+\)\s*\|", line)
        if m:
            rank = int(m.group(1))
            stars = 0
            sm = re.search(r"\+\s*([\d,]+)\s*/", line)
            if sm:
                stars = int(sm.group(1).replace(",", ""))
            result[m.group(2)] = (rank, stars)
    return result or None


def render_evening(target_date, trending, hot, morning_trending, morning_path, notes):
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
        lines.append(f"（未找到今日早报，无法对比；以下为晚间实时 Top10）")
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
        lines.append(f"- Trending 对比基准：[{morning_path.name}]({morning_path.name}) 表格")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 主流程

def collect_sources(target_date, kind):
    """抓取本报告需要的源。返回 (news, trending, hot, source_notes)。"""
    source_notes, news, trending, hot = [], None, None, None
    if kind == "morning":
        news, note = fetch_60s(target_date)
        source_notes.append(("✅ " if news else "⚠️ 中文要闻：") + note)
    else:
        source_notes.append("ℹ️ 中文要闻源为晨间聚合，晚间简报不含（白天动态以热搜晚间榜为准）")
    trending, note = fetch_trending()
    source_notes.append(("✅ GitHub Trending：" if trending else "⚠️ GitHub Trending：") + note)
    hot, note = fetch_weibo_hot()
    source_notes.append(("✅ 热搜：" if hot else "⚠️ 热搜：") + note)
    return news, trending, hot, source_notes


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
    pending, has_tasks_file = read_inbox()
    notes = {"output_dir": str(out_dir), "pending": pending,
             "has_tasks_file": has_tasks_file, "sources": source_notes}

    if args.kind == "morning":
        content = render_morning(target_date, news, trending, hot, notes)
    else:
        morning_path = out_dir / f"{target_date.isoformat()}-早报.md"
        morning_trending = _parse_morning_trending(morning_path)
        content = render_evening(target_date, trending, hot, morning_trending,
                                 morning_path, notes)

    out_path.write_text(content, encoding="utf-8")
    ok = sum(1 for n in source_notes if n.startswith("✅"))
    print(f"完成：{out_path}")
    print(f"数据源 {ok}/{len(source_notes)} 可用；收件箱待办 {len(pending)} 条")
    for n in source_notes:
        print("  " + n.split("（")[0][:80])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001 —— 未预期异常才非零退出
        import traceback
        traceback.print_exc()
        sys.exit(1)
