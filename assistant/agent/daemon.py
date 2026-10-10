#!/usr/bin/env python3
"""Project X v1 · 常驻 agent daemon：Telegram 入站 + tool-use 循环 + markdown 记忆。

用法：
    python3 assistant/agent/daemon.py                 # 前台运行（调试）
    python3 assistant/agent/daemon.py --check         # 配置自检（不发任何网络请求）
    python3 assistant/agent/daemon.py --once "文本"   # 处理单条消息后退出（TG 未配置则回打到 stdout）

约定（AGENTS.md / assistant/integrations/README.md / HANDOFF.md）：
- 入站通道是 channels/ 下的插件（AGENT_CHANNEL 选择，默认 telegram；飞书=新增插件+registry 行），
  2026-10-09 定盘 Telegram 先行；
- LLM：OpenAI 兼容 /chat/completions，凭据走 assistant/.secrets.env（LLM_* 键）；
- 全部 HTTP 走 curl 子进程（系统 Python 3.9 LibreSSL 与本地代理 TLS 不兼容）；
- 安全：只响应 TELEGRAM_CHAT_ID 本人；docs/ 与 .secrets.env 永不可读写；
  write_file 走确认门，用户回复「确认」才执行；
- 日志 JSONL：agent/logs/YYYY-MM-DD.jsonl（含 LLM usage，为第二批成本记账留数据）；
- 对话状态仅存内存（近期窗口 + 确认门挂起态），重启即清；跨会话事实一律进 memory。
"""

import argparse
import json
import os
import re
import signal
import sys
import time
from collections import deque
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ASSISTANT_DIR = AGENT_DIR.parent
LOGS_DIR = AGENT_DIR / "logs"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

import _http  # noqa: E402
import llm  # noqa: E402
import memory  # noqa: E402
import tools as tools_mod  # noqa: E402

CHANNELS_DIR = AGENT_DIR / "channels"
CONFIRM_WORDS = {"确认", "确认执行", "同意", "好", "是的", "ok", "OK", "Ok", "yes", "y", "Y", "是"}
MAX_TOOL_ROUNDS = 8   # 单轮消息最多工具循环次数，防失控
HISTORY_MAX = 12      # 近期上下文窗口（内存态，仅 user/assistant 文本）


def load_channel(name):
    """发现并加载 channels/<name>.py 入站通道插件（数据源插件同款模式）。
    契约：ID 常量 + create() -> (client|None, err)；client 需实现 poll()/send(text, reply_to)/chat_id。"""
    import importlib.util
    f = CHANNELS_DIR / f"{name}.py"
    if not f.exists():
        avail = [p.stem for p in CHANNELS_DIR.glob("*.py") if not p.name.startswith("_")]
        return None, f"通道插件不存在：{f}（可用：{', '.join(avail) or '无'}）"
    spec = importlib.util.spec_from_file_location(f"assistant_channel_{name}", f)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        return None, f"通道插件加载失败：{type(e).__name__}: {e}"
    if not (hasattr(mod, "create") and hasattr(mod, "ID")):
        return None, f"通道插件缺 ID/create() 契约：{f}"
    return mod, None

SYSTEM_PROMPT = """你是 Project X 的常驻个人助手，跑在用户的 Mac 上，通过 Telegram 与用户（唯一管理员）对话。

铁律：
- 全程中文、简洁直接；不确定的事问用户，不要编造。
- 隐私边界：assistant/docs/ 是用户敏感文件库，read_file/write_file 一律会被拒绝，不要尝试；.secrets.env 与任何密钥内容不得读取或复述。
- 重大/不可逆操作（写文件）走确认门：你发起后，系统会把预览发给用户，等ta回复「确认」才真正执行。
- 收件箱协议：用户交代「以后要做的事」→ inbox_add；查待办 → inbox_list；完成 → inbox_done（序号以 inbox_list 输出为准）。
- 早报/晚间简报 → run_report（生成后自动推送 Telegram，无需你转述全文）。
- 长期记忆：值得跨会话记住的偏好/进展/约定 → memory_save；相关记忆已在下方自动召回。
- 集成纪律：新工具/新数据源必须走 assistant/integrations/ 的提案流程（先查 registry.json 查重），不得私自安装第三方代码；纯方法类知识可写成 assistant/skills/ 下的技能。
- 输出格式（Telegram 用户端不渲染 markdown 表格）：给用户的回复一律不用表格，改用编号列表+分行纯文本；大数字用紧凑写法（如 34.6k）。表格只允许出现在写入文件的报告里。
- 榜单/对比类数据优先 send_chart 出图（先读技能 diagram-design 的方法），配简短文字说明；用户明确要文本列表时才只给文本。
- 你的能力就是工具列表；没有的能力如实说，不装会。"""

WEEKDAY = "一二三四五六日"


def load_secrets():
    """加载 assistant/.secrets.env（KEY=VALUE）；已存在的环境变量优先。同 report.py。"""
    path = ASSISTANT_DIR / ".secrets.env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def skills_index():
    """扫描 assistant/skills/ 的 SKILL.md frontmatter，生成技能索引文本（找不到则返回空串）。
    演示实测教训：没有列目录能力时 agent 会瞎猜技能路径，索引自注入是硬需求。"""
    skills_dir = ASSISTANT_DIR / "skills"
    if not skills_dir.exists():
        return ""
    items = []
    for f in sorted(skills_dir.glob("*/SKILL.md")):
        try:
            fm = f.read_text(encoding="utf-8").split("---")
            desc = re.search(r"^description:\s*(.+)$", fm[1], re.M) if len(fm) > 1 else None
        except (OSError, IndexError):
            continue
        items.append(f"- {f.parent.name}：{(desc.group(1).strip() if desc else '')}")
    return "\n".join(items)


class Logger:
    def __init__(self):
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.path = LOGS_DIR / f"{datetime.now():%Y-%m-%d}.jsonl"

    def log(self, direction, **kv):
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "dir": direction}
        rec.update(kv)
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass


class Daemon:
    def __init__(self, tg_client):
        self.tg = tg_client  # None = --once 无 TG 配置时回打 stdout
        tools_mod.CHANNEL = tg_client  # send_chart 等需要出站的工具用（None 时只渲染不发送）
        self.log = Logger()
        self.history = deque(maxlen=HISTORY_MAX)
        self.pending = None  # 确认门挂起态：{"messages": [...], "calls": [{"id","name","args"}]}

    # ---- 对外入口

    def handle_text(self, text, reply_to=None):
        """处理一条用户文本：跑完整轮 agent 循环（含确认门），把最终回复发出去。"""
        self.history.append({"role": "user", "content": text})
        if self.pending:
            confirmed = text.strip().lower() in CONFIRM_WORDS
            msgs = self.pending["messages"]
            calls = self.pending["calls"]
            self.pending = None
            filler = "操作已执行，结果如下" if confirmed else "用户未确认，该操作已取消。"
            for c in calls:
                result = tools_mod.execute(c["name"], c["args"], self.log) if confirmed \
                    else "用户未确认，该操作已取消。"
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
            if not confirmed:
                msgs.append({"role": "user", "content": text})
            self.log.log("confirm", ok=confirmed, tools=[c["name"] for c in calls])
            return self._turn(msgs, reply_to)
        return self._turn(self._new_conversation(text), reply_to)

    # ---- 内部

    def _new_conversation(self, text):
        now = datetime.now()
        sys_prompt = (f"{SYSTEM_PROMPT}\n\n（今天：{now:%Y-%m-%d} 周{WEEKDAY[now.weekday()]}）")
        skills = skills_index()
        if skills:
            sys_prompt += ("\n\n可用技能（任务匹配时先 read_file 读取对应 "
                           "assistant/skills/<名字>/SKILL.md 并按其方法执行）：\n" + skills)
        recalled = memory.recall(text, top=3)
        if recalled:
            sys_prompt += "\n\n相关记忆召回：\n" + "\n".join(f"- {r}" for r in recalled)
        msgs = [{"role": "system", "content": sys_prompt}]
        msgs += list(self.history)[:-1]  # 近期上下文（不含刚这条，它在下面）
        msgs.append({"role": "user", "content": text})
        return msgs

    def _turn(self, msgs, reply_to):
        for rnd in range(MAX_TOOL_ROUNDS):
            msg, usage, err = llm.chat(msgs, tools_mod.schemas())
            if err:
                self.log.log("llm_err", err=err)
                return self._say(f"⚠️ LLM 调用失败：{err}", reply_to)
            if usage:
                self.log.log("llm", model=llm.model_name(), usage=usage)
            reasoning = (msg.get("reasoning_content") or "").strip()
            if reasoning:  # 思考型模型的推理文本：留档本地日志；不再回传（API 惯例：历史消息剥离 reasoning）
                self.log.log("reasoning", round=rnd, text=reasoning[:4000])
            msgs.append({k: v for k, v in msg.items() if k != "reasoning_content"})
            calls = msg.get("tool_calls") or []
            if not calls:
                content = (msg.get("content") or "").strip() or "（空回复）"
                return self._say(content, reply_to, assistant_out=content)
            # 先执行免确认工具；遇到需确认的，挂起并一次性问用户
            need_confirm = []
            for i, c in enumerate(calls):
                name, args = tools_mod.parse_call(c)
                cid = c.get("id") or f"call_{i}"
                if tools_mod.is_confirm(name):
                    need_confirm.append({"id": cid, "name": name, "args": args})
                    continue
                result = tools_mod.execute(name, args, self.log)
                msgs.append({"role": "tool", "tool_call_id": cid, "content": result})
            if need_confirm:
                self.pending = {"messages": msgs, "calls": need_confirm}
                lines = [f"• {c['name']}：{tools_mod.preview(c['name'], c['args'])}"
                         for c in need_confirm]
                return self._say("⚠️ 需要你确认：\n" + "\n".join(lines) +
                                 "\n\n回复「确认」执行；回复其他内容则取消该操作并按新指令处理。",
                                 reply_to)
        return self._say("⚠️ 工具循环轮次用尽，先回复到这里；需要细节可以再问我。", reply_to)

    def _say(self, text, reply_to, assistant_out=None):
        if assistant_out is not None:
            self.history.append({"role": "assistant", "content": assistant_out})
        self.log.log("out", text=text[:500])
        if self.tg is None:
            print(text)
            return None
        err = self.tg.send(text, reply_to=reply_to)
        if err:
            self.log.log("send_err", err=err)
        return err


def run(tg_client, daemon):
    """主循环：长轮询 → 白名单过滤 → 逐条处理。SIGTERM/SIGINT 优雅退出。"""
    stop = {"flag": False}

    def _sig(_a, _b):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    daemon.log.log("boot", note="daemon 启动")
    print(f"daemon 已启动（chat={tg_client.chat_id}，model={llm.model_name()}），Ctrl-C 退出")
    fails = 0
    while not stop["flag"]:
        updates, err = tg_client.poll(timeout_s=25)
        if err:
            fails += 1
            daemon.log.log("poll_err", err=err, fails=fails)
            if "conflict" in err.lower():
                print("检测到其他 getUpdates 实例（409），60s 后重试——确认没有第二个 daemon 在跑",
                      file=sys.stderr)
                time.sleep(60)
            else:
                time.sleep(min(30, 3 + fails * 2))
            continue
        fails = 0
        for u in updates:
            msg = u.get("message") or {}
            chat_id = str((msg.get("chat") or {}).get("id", ""))
            if chat_id != tg_client.chat_id:
                daemon.log.log("deny", chat_id=chat_id, note="非管理员 chat，忽略")
                continue
            text = (msg.get("text") or "").strip()
            if not text:
                continue  # v0.1 只处理文本
            daemon.log.log("in", text=text[:500])
            try:
                daemon.handle_text(text, reply_to=msg.get("message_id"))
            except Exception as e:  # noqa: BLE001 —— 单条消息崩溃不拖垮 daemon
                daemon.log.log("err", err=f"{type(e).__name__}: {e}")
                try:
                    tg_client.send(f"⚠️ 内部错误：{type(e).__name__}: {e}")
                except Exception:  # noqa: BLE001
                    pass
    daemon.log.log("boot", note="daemon 退出")


def selfcheck():
    print("== Project X agent 自检（无网络请求）==")
    print(f"python: {sys.version.split()[0]}（需 3.9+）")
    sec = ASSISTANT_DIR / ".secrets.env"
    print(f"secrets 文件: {sec}{' ✓' if sec.exists() else ' ✗ 缺失（应在运行机上配置）'}")
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "LLM_API_KEY"):
        print(f"  {k}: {'✓ 已配置' if os.environ.get(k) else '✗ 未配置'}")
    print(f"LLM: {llm.model_name()} @ {llm.base_url()}，"
          f"web_search={'开' if llm._web_search_on(llm.base_url()) else '关'}")
    print(f"代理: {os.environ.get('ASSISTANT_PROXY', _http.DEFAULT_PROXY)}"
          f"（Telegram 走代理，LLM 默认直连，LLM_PROXY=on 可改）")
    print(f"记忆: {len(list(memory.MEMORY_DIR.glob('*.md')))} 个文件 @ {memory.MEMORY_DIR}")
    print(tools_mod.inbox_list())
    print("工具:", "、".join(t.name + ("（需确认）" if t.confirm else "") for t in tools_mod.TOOLS))
    chans = [p.stem for p in CHANNELS_DIR.glob("*.py") if not p.name.startswith("_")]
    print(f"入站通道插件: {', '.join(chans) or '无'}"
          f"（AGENT_CHANNEL={os.environ.get('AGENT_CHANNEL') or 'telegram（默认）'}）")
    print("日志目录:", LOGS_DIR)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Project X 常驻 agent daemon（v1 最小闭环）")
    ap.add_argument("--check", action="store_true", help="配置自检，不发网络请求")
    ap.add_argument("--once", metavar="TEXT", help="处理单条消息后退出（调试）")
    args = ap.parse_args()

    load_secrets()
    if args.check:
        return selfcheck()

    channel_name = os.environ.get("AGENT_CHANNEL", "telegram")
    channel_mod, cerr = load_channel(channel_name)
    if cerr:
        print(cerr, file=sys.stderr)
        return 1
    tg_client = None
    if args.once:
        tg_client, _ = channel_mod.create()  # 无凭据则回打 stdout
    else:
        tg_client, terr = channel_mod.create()
        if terr:
            print(f"{channel_mod.ID} 通道不可用：{terr}", file=sys.stderr)
            return 1
    if not os.environ.get("LLM_API_KEY"):
        print("缺 LLM_API_KEY（assistant/.secrets.env，OpenAI 兼容接口）", file=sys.stderr)
        return 1

    daemon = Daemon(tg_client)
    if args.once:
        daemon.handle_text(args.once)
        return 0
    run(tg_client, daemon)
    return 0


if __name__ == "__main__":
    sys.exit(main())
