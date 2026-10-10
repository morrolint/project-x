"""Telegram 推送插件（push-channel 契约见 ../README.md）。

channels/ 下不以 _ 开头即被 report.py 动态发现；新增推送通道 = 放一个同构插件
+ registry.json 加一行，report.py 零改动。凭据走环境变量（report.py 已加载 .secrets.env）。
"""

import json
import os
import subprocess

DEFAULT_PROXY = "http://127.0.0.1:7892"  # 与 sources/_common.py 同源；ASSISTANT_PROXY=off 可禁用

ID = "push-telegram"
NAME = "Telegram"


def push(text):
    """推送 HTML 文本到 Telegram。返回 (是否成功, 错误说明)；绝不抛异常。"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return False, "未配置（.secrets.env 缺 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID）"
    if len(text) > 4000:
        text = text[:4000].rstrip() + "…"
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
