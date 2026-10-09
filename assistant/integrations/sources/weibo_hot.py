"""数据源：微博热搜（主：官方接口；备：tophub 快照）"""

import re

from _common import http_get, strip_tags, load_json


ID = "source-weibo-hot"
NAME = "微博热搜"
KINDS = ("morning", "evening")


def fetch(target_date):
    """返回 ([{word,num,label}, ...] | None, 备注文本)。"""
    html, via, err = http_get(
        "https://weibo.com/ajax/side/hotSearch", timeout=10, allow_proxy=False,
        extra_headers={"Referer": "https://weibo.com/"})
    if html:
        data = load_json(html)
        if data and "data" in data:
            try:
                items = [it for it in data["data"]["realtime"] if not it.get("is_ad")]
                hot = [{"word": it["word"].strip().strip("#"),
                        "num": int(it.get("num") or 0),
                        "label": it.get("icon_desc") or ""} for it in items[:10]]
                if hot:
                    return hot, "[微博热搜](https://s.weibo.com/top/summary) 官方接口实时抓取 Top10"
            except (KeyError, TypeError, ValueError) as e:
                err = f"接口解析失败（{type(e).__name__}）"
    # 备用源 tophub（节点已多次失效，仅兜底）
    html2, _, err2 = http_get("https://tophub.today/n/KqndgxeLl9", timeout=10)
    if html2:
        tds = re.findall(r'<td class="al"[^>]*>(.*?)</td>', html2, re.S)
        words = []
        for td in tds:
            t = re.sub(r"\d+\.\s*", "", strip_tags(td)).strip()
            if t and "加载" not in t and "快照" not in t:
                words.append({"word": t, "num": 0, "label": ""})
        if words:
            return words[:10], "[tophub](https://tophub.today) 快照 Top10（备用源，无热度值）"
    return None, f"抓取失败（{err}；备用源也不可用：{err2}）"
