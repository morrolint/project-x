"""LLM 调用：OpenAI 兼容 /chat/completions（GLM / DeepSeek / Claude 均可，环境变量切换）。

- 默认智谱 GLM；国内端点直连（proxy="off"），需要代理的端点设 LLM_PROXY=on。
- web_search：智谱端点默认附带其官方 web_search 工具（LLM_WEB_SEARCH=off 可关），
  这是 HANDOFF §六 "搜索先用模型自带" 的落地。
"""

import json
import os

import _http

DEFAULT_BASE = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-5.3-flash"  # 与开发会话同款（2026-10-09 用户指定）；公开 API 不认此 id 时改回 glm-4.6


def base_url():
    return os.environ.get("LLM_BASE_URL", DEFAULT_BASE).rstrip("/")


def model_name():
    return os.environ.get("LLM_MODEL", DEFAULT_MODEL)


def _web_search_on(base):
    mode = os.environ.get("LLM_WEB_SEARCH", "auto").strip().lower()
    if mode in ("0", "off", "false", "no"):
        return False
    if mode in ("1", "on", "true"):
        return True
    # auto：智谱端点才开（其私有 web_search 工具，其他兼容端点不认）
    return "bigmodel.cn" in base or "zhipu" in base or model_name().lower().startswith("glm")


def chat(messages, tools=None):
    """一轮对话（非流式）。返回 (assistant 消息 dict, usage dict|None, 错误|None)。"""
    key = os.environ.get("LLM_API_KEY", "")
    if not key:
        return None, None, "缺 LLM_API_KEY（assistant/.secrets.env）"
    payload = {"model": model_name(), "messages": messages, "stream": False}
    out_tools = list(tools or [])
    if out_tools and _web_search_on(base_url()):
        out_tools.append({"type": "web_search", "web_search": {"enable": True}})
    if out_tools:
        payload["tools"] = out_tools
    use_proxy = os.environ.get("LLM_PROXY", "").strip().lower() in ("1", "on", "true")
    data, err = _http.request_json(
        "POST", base_url() + "/chat/completions",
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json.dumps(payload, ensure_ascii=False),
        timeout=180, proxy="on" if use_proxy else "off", retries=1)
    if err:
        return None, None, err
    if not isinstance(data, dict):
        return None, None, f"异常响应: {str(data)[:200]}"
    if data.get("error"):
        e = data["error"]
        msg = e if isinstance(e, str) else (e.get("message") or str(e))
        return None, None, f"API: {msg}"
    choices = data.get("choices") or []
    if not choices:
        return None, None, f"响应无 choices: {json.dumps(data, ensure_ascii=False)[:200]}"
    return choices[0].get("message") or {}, data.get("usage"), None
