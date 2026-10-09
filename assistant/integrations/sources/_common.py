"""数据源插件共享设施：HTTP（系统 curl 子进程）与通用工具。

macOS 系统 Python 3.9 的 LibreSSL 与本地代理栈有 TLS 兼容问题，
故用 curl 而非 urllib（详见仓库 AGENTS.md）。
"""

import html as htmllib
import json
import os
import re
import subprocess
import time

DEFAULT_PROXY = "http://127.0.0.1:7892"  # SpeedCat VPN；环境变量 ASSISTANT_PROXY=off 可禁用
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def http_get(url, timeout=15, allow_proxy=True, extra_headers=None, retries=2):
    """GET 一个 URL 返回文本。直连失败走代理，每条路径重试一次。
    返回 (文本|None, 途径说明|None, 错误说明)。"""
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


def fmt_k(n):
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


def strip_tags(fragment):
    return htmllib.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def load_json(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None
