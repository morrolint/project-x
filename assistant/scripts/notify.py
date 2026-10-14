#!/usr/bin/env python3
"""往 Telegram 发班次通知/汇报（工程侧专用；daemon 自己回话走 agent/channels/）。

复用 integrations/channels/telegram 插件（代理与重试逻辑继承，HTML 模式推送）。
markdown 自动转 Telegram HTML：**粗体**→<b>、[t](u)→可点击链接（URL 隐藏）、
#标题→加粗行、>引用→<blockquote>、`码`→<code>；内容先做 HTML 转义再注入标签。

推送纪律（发给用户手机的内容一律遵守）：
1. 只发产品不发过程：禁用产线词汇（重推/本班/N连杀/人肉班/见前条消息/实抓N条/本班处理）——
   工程账进会话与 HANDOFF，不进用户界面；抓取时点以一句话自然标注（诚实度要求，保留）。
2. 精选而非倾倒：要闻选 5-8 条按重要性，不全文转储；深读与科技动态可全文。
3. 排版干净：无 markdown 残留（#/``/**）；节标题用 emoji 起头。
4. 收件箱只推用户需行动或知悉的条目；内部记档不推。
5. meta 汇报只在有可行动项时发，且压缩为末尾一段。

用法：
    python3 assistant/scripts/notify.py "文本"
    python3 assistant/scripts/notify.py --file 路径      # 发整个文件
    python3 assistant/scripts/notify.py --section 路径 "起始标题" "结束标题"  # 发文件中一节
    加 --raw 表示已是 Telegram HTML，跳过转换
"""

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "integrations" / "channels"))


def load_secrets():
    p = ROOT / ".secrets.env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(s):
    s = _esc(s)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"(?<!\w)\*([^*]+)\*(?!\w)", r"<i>\1</i>", s)
    return s


def md2tghtml(t):
    """markdown → Telegram HTML（标题加粗、引用块、链接、粗斜体码）。"""
    out, in_quote = [], False
    for ln in t.split("\n"):
        m = re.match(r"^(#{1,6})\s*(.+)$", ln)
        q = re.match(r"^>\s?(.*)$", ln)
        if in_quote and not q:
            out.append("</blockquote>")
            in_quote = False
        if m:
            out.append(f"<b>{_esc(m.group(2))}</b>")
        elif q:
            if not in_quote:
                out.append("<blockquote>")
                in_quote = True
            out.append(_inline(q.group(1)))
        else:
            out.append(_inline(ln))
    if in_quote:
        out.append("</blockquote>")
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out))


def main():
    args = sys.argv[1:]
    raw = "--raw" in args
    args = [a for a in args if a != "--raw"]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--file":
        text = Path(args[1]).read_text(encoding="utf-8")
    elif args[0] == "--section":
        path, start, end = args[1], args[2], args[3]
        s = Path(path).read_text(encoding="utf-8")
        i = s.index(start)
        j = s.index(end, i) if end in s[i:] else len(s)
        text = s[i:j].strip()
    else:
        text = args[0]
    if not raw:
        text = md2tghtml(text)
    load_secrets()
    import telegram  # integrations/channels/telegram.py 插件
    ok, err = telegram.push(text)
    print("✅ 已发送" if ok else f"❌ 失败：{err}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
