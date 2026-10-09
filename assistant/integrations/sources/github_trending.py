"""数据源：GitHub Trending（整页解析，按今日星数降序取 Top10）"""

import re

from _common import http_get, strip_tags


ID = "source-github-trending"
NAME = "GitHub Trending"
KINDS = ("morning", "evening")


def fetch(target_date):
    """返回 ([{name,url,desc,lang,stars_total,stars_today}, ...] | None, 备注文本)。"""
    page, via, err = http_get("https://github.com/trending", timeout=15)
    if page is None:
        return None, f"抓取失败（{err}）"
    repos = []
    for r in re.findall(r'<article class="Box-row">(.*?)</article>', page, re.S):
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
            "desc": strip_tags(desc.group(1)) if desc else "",
            "lang": lang.group(1) if lang else "—",
            "stars_total": int(stars.group(1).replace(",", "")) if stars else 0,
            "stars_today": int(today.group(1).replace(",", "")) if today else 0,
        })
    if not repos:
        return None, "页面结构变化：未解析出任何仓库"
    # 整页解析后按今日星数排序再截 Top10（页面顺序不按星数排，先截会漏高增速项目）
    repos.sort(key=lambda x: x["stars_today"], reverse=True)
    repos = repos[:10]
    for r in repos:  # 表格可读性：简介过长截断
        if len(r["desc"]) > 60:
            r["desc"] = r["desc"][:60].rstrip() + "…"
    note = "[github.com/trending](https://github.com/trending) 实时抓取 Top10"
    if via and "直连" not in via:
        note += f"（经{via}）"
    return repos, note
