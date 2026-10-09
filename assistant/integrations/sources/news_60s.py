"""数据源：每天60秒读懂世界（blog.intelexe.cn）"""

import re

from _common import http_get, strip_tags


ID = "source-60s"
NAME = "每天60秒读懂世界"
KINDS = ("morning",)


def fetch(target_date):
    """返回 ({"items": [...], "weiyu": str, "url": str} | None, 备注文本)。"""
    iso = target_date.isoformat()
    index_html, via, err = http_get("https://blog.intelexe.cn/")
    if index_html is None:
        return None, f"索引页抓取失败（{err}）"
    post_url = None
    for m in re.finditer(r'<a[^>]+href="(https://blog\.intelexe\.cn/archives/\d+)"[^>]*>(.*?)</a>',
                         index_html, re.S):
        title = strip_tags(m.group(2))
        if iso in title and "读懂世界" in title:
            post_url = m.group(1)
            break
    if not post_url:
        return None, f"索引页未找到 {iso} 的文章（可能尚未发布）"
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
    paras = [strip_tags(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", body, re.S)]
    paras = [p for p in paras if p]
    numbered = {}
    for p in paras:
        m = re.match(r"^(\d{1,2})、\s*(.*)", p)
        if m:
            numbered.setdefault(int(m.group(1)), m.group(2).rstrip("；;。") + "。")
    items = [numbered[d] for d in sorted(numbered)]
    weiyu = next((p.replace("【微语】", "").strip() for p in paras if p.startswith("【微语】")), "")
    if not items:
        return None, "正文中未解析出编号条目（页面结构可能变化）"
    note = f"[每天60秒读懂世界]({post_url}) 完整 {len(items)} 条" + ("，含微语" if weiyu else "")
    if via and "直连" not in via:
        note += f"（经{via}）"
    return {"items": items, "weiyu": weiyu, "url": post_url}, note
