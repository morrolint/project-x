"""Telegram 入站通道插件（channel-inbound 契约见 ../../integrations/README.md）。

channels/ 下不以 _ 开头的文件按 AGENT_CHANNEL（默认 telegram）被 daemon 选择加载；
新增通道（如飞书）= 放一个同构插件 + registry.json 加一行 + 设 AGENT_CHANNEL，daemon 零改动。
出站沿用已验证的 bot（@m0rro_bot，凭据在 assistant/.secrets.env）；飞书为预留通道。
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 复用 agent/_http

import _http  # noqa: E402

API_BASE = "https://api.telegram.org"

ID = "telegram"
NAME = "Telegram 长轮询"


def _split(text, limit=3800):
    """Telegram 单条上限 4096 字符，按换行切段。"""
    text = text or ""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut].rstrip())
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks or [""]


class Telegram:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = str(chat_id)
        self.offset = 0  # getUpdates 游标：只收 offset 之后的新消息

    def api(self, method, curl_timeout=30, **params):
        """调一个 Bot API 方法。返回 (result|None, 错误|None)。"""
        body = json.dumps(params, ensure_ascii=False)
        data, err = _http.request_json(
            "POST", f"{API_BASE}/bot{self.token}/{method}",
            {"Content-Type": "application/json"}, body,
            timeout=curl_timeout, proxy="on")
        if err:
            return None, err
        if not data.get("ok"):
            return None, f"API: {data.get('description', str(data)[:200])}"
        return data.get("result"), None

    def poll(self, timeout_s=25):
        """长轮询取新消息。返回 (updates, err)。"""
        result, err = self.api("getUpdates", curl_timeout=timeout_s + 15,
                               timeout=timeout_s, offset=self.offset,
                               allowed_updates=["message", "callback_query"])
        if err:
            return [], err
        for u in result or []:
            self.offset = max(self.offset, u.get("update_id", 0) + 1)
        return result or [], None

    def send(self, text, reply_to=None):
        """发送纯文本。返回最后一个错误或 None（兼容旧调用方）。"""
        err, _ = self.send_ex(text, reply_to)
        return err

    def send_ex(self, text, reply_to=None):
        """发送纯文本。返回 (错误|None, 最后一条消息的 message_id|None)——进度面板要拿 id 做原地刷新。"""
        err, last_id = None, None
        for chunk in _split(text):
            params = {"chat_id": self.chat_id, "text": chunk,
                      "disable_web_page_preview": True}
            if reply_to:
                params["reply_to_message_id"] = reply_to
            result, err = self.api("sendMessage", curl_timeout=30, **params)
            if result:
                last_id = result.get("message_id", last_id)
        return err, last_id

    def send_confirm(self, text, yes="✅ 确认", no="🚫 取消"):
        """发送带内联按钮的确认消息。返回 (错误|None, message_id|None)。"""
        result, err = self.api(
            "sendMessage", curl_timeout=30, text=str(text)[:3800],
            chat_id=self.chat_id, disable_web_page_preview=True,
            reply_markup={"inline_keyboard": [[
                {"text": yes, "callback_data": "confirm:yes"},
                {"text": no, "callback_data": "confirm:no"}]]})
        return err, (result or {}).get("message_id")

    def answer_callback(self, callback_id, text=""):
        """应答回调（消掉客户端转圈）。"""
        self.api("answerCallbackQuery", curl_timeout=10,
                 callback_query_id=str(callback_id), text=text[:180])

    def edit_message(self, msg_id, text):
        """编辑自己发的消息（进度面板原地刷新）。返回 (ok, 错误|None)。"""
        result, err = self.api("editMessageText", curl_timeout=15,
                               chat_id=self.chat_id, message_id=int(msg_id),
                               text=str(text)[:3800], disable_web_page_preview=True)
        return err is None, err

    def typing(self):
        """发送"正在输入"状态（Telegram 端显示约 5 秒）。返回错误或 None。"""
        _, err = self.api("sendChatAction", curl_timeout=10,
                          chat_id=self.chat_id, action="typing")
        return err

    def send_photo(self, png_path, caption=""):
        """发送本地图片文件（multipart 上传）。返回错误或 None。"""
        import os
        import subprocess
        proxy = os.environ.get("ASSISTANT_PROXY", "")
        px = ["-x", proxy] if proxy and proxy.lower() not in ("off", "none", "") else []
        cmd = ["curl", "-sS", "--connect-timeout", "8", "--max-time", "60", *px,
               "-F", f"chat_id={self.chat_id}",
               "-F", f"caption={str(caption)[:900]}",
               "-F", f"photo=@{png_path}",
               f"{API_BASE}/bot{self.token}/sendPhoto"]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=70)
        except subprocess.TimeoutExpired:
            return "sendPhoto 超时"
        try:
            data = json.loads(r.stdout.decode("utf-8", errors="replace"))
            return None if data.get("ok") else f"API: {data.get('description', str(data)[:150])}"
        except ValueError:
            return f"非 JSON 响应: {r.stdout[:120]}"


def create():
    """契约工厂：从环境变量构建通道实例。返回 (client|None, 错误|None)。"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        return None, "缺 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID（.secrets.env）"
    return Telegram(token, chat_id), None
