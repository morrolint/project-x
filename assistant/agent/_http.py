"""agent 共享 HTTP：系统 curl 子进程（系统 Python 3.9 的 LibreSSL 与本地代理 TLS 不兼容，见 AGENTS.md）。

与 integrations/sources/_common.py 同思路，但支持 POST 与三种代理模式：
- "auto"：先直连，失败转代理（默认，适合国内可达的 LLM API）
- "on"：仅走代理（Telegram 必须）
- "off"：仅直连
环境变量 ASSISTANT_PROXY=off 可全局禁用代理。
"""

import json
import os
import subprocess
import time

DEFAULT_PROXY = "http://127.0.0.1:7892"


def request_json(method, url, headers=None, body=None, timeout=30, proxy="auto", retries=2):
    """请求一个 JSON API。返回 (解析后的 JSON|None, 错误说明|None)。"""
    proxy_addr = os.environ.get("ASSISTANT_PROXY", DEFAULT_PROXY)
    proxy_off = not proxy_addr or proxy_addr.lower() in ("off", "none", "")
    px = [] if proxy_off else ["-x", proxy_addr]
    if proxy == "on":
        if proxy_off:
            return None, "需要代理但 ASSISTANT_PROXY=off"
        paths = [("代理", px)]
    elif proxy == "off" or proxy_off:
        paths = [("直连", [])]
    else:  # auto
        paths = [("直连", [])] + ([("代理", px)] if px else [])

    hdrs = []
    for k, v in (headers or {}).items():
        hdrs += ["-H", f"{k}: {v}"]

    last_err = "未知错误"
    for label, px_args in paths:
        for attempt in range(1, retries + 1):
            cmd = ["curl", "-sS", "--connect-timeout", "8", "--max-time", str(timeout),
                   *hdrs, *px_args]
            if body is not None:
                cmd += ["--data-binary", "@-"]  # 走 stdin，避免参数长度与转义问题
            cmd.append(url)
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=timeout + 5,
                                   input=(body or "").encode("utf-8"))
            except subprocess.TimeoutExpired:
                last_err = "curl 超时"
                continue
            out = r.stdout.decode("utf-8", errors="replace")
            if r.returncode == 0 and out:
                try:
                    return json.loads(out), None
                except ValueError:
                    return None, f"非 JSON 响应: {out[:160]}"
            detail = r.stderr.decode("utf-8", errors="replace").strip().splitlines()
            last_err = f"{label} curl exit {r.returncode}: {detail[-1] if detail else '无输出'}"
            if attempt < retries:
                time.sleep(1)
    return None, last_err
