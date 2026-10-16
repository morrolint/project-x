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
import threading
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
from daemon_state import STATE_FILE, load_state, save_state  # noqa: E402
import llm  # noqa: E402
import memory  # noqa: E402
import scheduler as scheduler_mod  # noqa: E402
import evolve as evolve_mod  # noqa: E402
import tasks as tasks_mod  # noqa: E402
import tools as tools_mod  # noqa: E402

CHANNELS_DIR = AGENT_DIR / "channels"
PROMPTS_DIR = AGENT_DIR / "prompts"       # 班次 prompt 外置（shift-morning/evening.md）

SHIFT_PROMPTS = {
    "morning": """执行今天的早班（你是 Project X 个人助手，本条为内部班次指令）：
1. 调 run_report 生成 morning 早报（已存在则跳过）。
2. read_file 读生成的早报，把「GitHub Trending」节升级为逐项目解读（先读技能 github-trending-deep-read 的方法；对榜上不熟的项目先 trending_top 拿数据、凭简介与已知知识写，不编造），再 write_file 整体写回报告文件。
3. 用 web 搜索补 2-3 条科技/AI 动态进「科技 / AI」节（带日期来源），并重写「AI 一句话」。
4. 处理收件箱：inbox_list 查看，能办的用工具办，办完 inbox_done；【待批复/待重排】类只汇报不执行。
5. 最后给用户发一段早班汇报（精选要闻 5 条内、Trending 头条、收件箱一句话），并注明报告文件路径。全程中文，禁用 markdown 表格。""",
    "evening": """执行今天的晚班（你是 Project X 个人助手，本条为内部班次指令）：
1. 调 run_report 生成 evening 晚间简报（自动与早报 sidecar 对比 ↑↓/NEW）。
2. read_file 简报，在「Trending 复盘」节后追加两三句点评（口径披露：对比基准时点；换血/稳定/绝对值三个角度）。
3. 用 web 搜索补 2-3 条白天科技动态进「白天动态」节。
4. 收件箱巡检同早班（能办的办，等批复的汇报）。
5. 最后发晚班汇报（对比亮点、白天动态精选、收件箱一句话）。全程中文，禁用 markdown 表格。""",
}
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


PERSONAS_DIR = AGENT_DIR / "personas"


def personas_index():
    """扫描 agent/personas/*.md 的 frontmatter，生成人设索引文本。"""
    if not PERSONAS_DIR.exists():
        return ""
    items = []
    for f in sorted(PERSONAS_DIR.glob("*.md")):
        try:
            fm = f.read_text(encoding="utf-8").split("---")
            sec = fm[1] if len(fm) > 1 else ""
            name = re.search(r"^name:\s*(.+)$", sec, re.M)
            vibe = re.search(r"^vibe:\s*(.+)$", sec, re.M)
        except OSError:
            continue
        items.append(f"- {f.stem}：{name.group(1).strip() if name else '？'}"
                     f"——{vibe.group(1).strip() if vibe else ''}")
    return "\n".join(items)


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

    def log(self, direction, **kv):
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "dir": direction}
        rec.update(kv)
        try:  # 路径每次取当日：常驻 daemon 跨天必须换文件（2026-10-16 修复：曾把 10-15/16 事件全写进 10-14）
            with open(LOGS_DIR / f"{datetime.now():%Y-%m-%d}.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError:
            pass


class Daemon:
    def __init__(self, tg_client):
        self.tg = tg_client  # None = --once 无 TG 配置时回打 stdout
        tools_mod.CHANNEL = tg_client  # send_chart 等需要出站的工具用（None 时只渲染不发送）
        self.log = Logger()
        self.history = deque(maxlen=HISTORY_MAX)
        self.pending = None  # 确认门挂起态：{"messages": [...], "calls": [...], "task": TaskLine|None}
        self.task = None     # 当前任务线（进度面板）
        self._internal = False  # 班次/内勤轮次：宽口径免确认 + 不进对话历史

    def restore_pending(self, recovered):
        """启动恢复：把磁盘上 WAITING_USER 的任务重新挂回确认门。"""
        payload = recovered["payload"]
        self.pending = {"messages": payload.get("messages") or [],
                        "calls": payload.get("calls") or [],
                        "task": recovered["task"]}
        self.log.log("recover", note=f"恢复挂起任务 {recovered['task'].id}")
        recovered["task"].push(self.tg)  # 刷新进度消息：仍在等你确认

    # ---- 对外入口

    def handle_text(self, text, reply_to=None):
        """处理一条用户文本：跑完整轮 agent 循环（含确认门），把最终回复发出去。"""
        self._internal = False
        self.history.append({"role": "user", "content": text})
        self.task = tasks_mod.TaskLine(kind="chat", label=text[:24])
        self.task.push(self.tg, edit=False)
        return self._dispatch(text, reply_to)

    def _dispatch(self, text, reply_to):
        if self.pending:
            confirmed = text.strip().lower() in CONFIRM_WORDS
            task = self.pending.get("task")
            if task:
                task.state = "RUNNING"
                task.note = "确认执行中" if confirmed else "按新指令处理"
                task.push(self.tg)
            msgs = self.pending["messages"]
            calls = self.pending["calls"]
            self.pending = None
            for c in calls:
                result = tools_mod.execute(c["name"], c["args"], self.log) if confirmed \
                    else "用户未确认，该操作已取消。"
                msgs.append({"role": "tool", "tool_call_id": c["id"], "content": result})
            if not confirmed:
                msgs.append({"role": "user", "content": text})
            self.log.log("confirm", ok=confirmed, tools=[c["name"] for c in calls])
            return self._turn(msgs, reply_to)
        return self._turn(self._new_conversation(text), reply_to)

    def run_reflect(self):
        """记忆固化（周日）：LLM 归并月度日志+facts → memory/observations.md（带证据计数）。"""
        self._internal = True
        self.task = tasks_mod.TaskLine(kind="reflect", label="记忆固化")
        self.task.push(self.tg, edit=False)
        self.log.log("shift", kind="reflect", note="记忆固化启动")
        try:
            prompt = ("整理长期记忆（内部维护任务）：read_file 读 assistant/memory/ 下当月与上月日志及 facts.md，"
                      "把重复/相关条目归并为'观察'——每条带出现次数（证据计数）与时间范围，"
                      "写成 assistant/memory/observations.md（write_file，标题注明生成时间）；"
                      "只归并不改原始日志；过时条目标注'已过时'不删除。中文，完成后一句话汇报即可。")
            self._turn(self._new_conversation(prompt, use_history=False), None)
        except Exception as e:  # noqa: BLE001
            self.log.log("err", err=f"reflect: {type(e).__name__}: {e}")
        finally:
            self._internal = False

    def run_shift(self, kind):
        """内部班次（调度器或 --shift 触发）：独立于用户对话历史，宽口径免确认。
        prompt 外置于 prompts/shift-<kind>.md（与 personas/skills 同哲学）。"""
        prompt_file = PROMPTS_DIR / f"shift-{kind}.md"
        if not prompt_file.exists():
            self.log.log("err", err=f"班次 prompt 不存在：{prompt_file}")
            return
        self._internal = True
        self.task = tasks_mod.TaskLine(kind=f"shift-{kind}",
                                       label="早班" if kind == "morning" else "晚班")
        self.task.push(self.tg, edit=False)
        self.log.log("shift", kind=kind, note="班次启动")
        try:
            self._turn(self._new_conversation(prompt_file.read_text(encoding="utf-8"),
                                              use_history=False), None)
        except Exception as e:  # noqa: BLE001 —— 班次崩溃要有尸检记录
            self.log.log("err", err=f"shift {kind}: {type(e).__name__}: {e}")
            if self.tg:
                self.tg.send(f"⚠️ {kind} 班次内部错误：{type(e).__name__}")
        finally:
            self._internal = False

    # ---- 内部

    def _new_conversation(self, text, use_history=True):
        now = datetime.now()
        sys_prompt = (f"{SYSTEM_PROMPT}\n\n（今天：{now:%Y-%m-%d} 周{WEEKDAY[now.weekday()]}）")
        skills = skills_index()
        if skills:
            sys_prompt += ("\n\n可用技能（任务匹配时先 read_file 读取对应 "
                           "assistant/skills/<名字>/SKILL.md 并按其方法执行）：\n" + skills)
        profile = memory.profile_text()
        if profile:
            sys_prompt += ("\n\n用户档案（常备页，当前世界观的底座；与眼前任务冲突时以眼前为准）：\n" + profile)
        # 人设层：AGENT_PERSONA 强制注入；否则给索引由模型按任务性质自选
        forced = os.environ.get("AGENT_PERSONA", "").strip()
        if forced and (PERSONAS_DIR / f"{forced}.md").exists():
            sys_prompt += ("\n\n【当前人设（强制）——以此身份与标准工作，系统铁律仍最高】\n"
                           + (PERSONAS_DIR / f"{forced}.md").read_text(encoding="utf-8")[:6000])
        else:
            pidx = personas_index()
            if pidx:
                sys_prompt += ("\n\n可用人设（任务性质匹配时先 read_file 读取 "
                               "assistant/agent/personas/<名>.md 并以其身份与标准工作；铁律冲突时铁律优先）：\n" + pidx)
        recalled = memory.recall(text, top=3)
        if recalled:
            sys_prompt += "\n\n相关记忆召回：\n" + "\n".join(f"- {r}" for r in recalled)
        msgs = [{"role": "system", "content": sys_prompt}]
        if use_history:
            msgs += list(self.history)[:-1]  # 近期上下文（不含刚这条，它在下面）
        msgs.append({"role": "user", "content": text})
        return msgs

    def _heartbeat_loop(self):
        """长任务期间：typing 心跳（4.5s 续）+ 任务线进度保活（约 75s 重刷）。"""
        beats = 0
        while not self._hb_stop.wait(4.5):
            if self.tg is not None and hasattr(self.tg, "typing"):
                self.tg.typing()
            beats += 1
            if beats % 17 == 0 and self.task and self.task.state == "RUNNING":
                self.task.push(self.tg)

    def _turn(self, msgs, reply_to):
        self._hb_stop = threading.Event()
        threading.Thread(target=self._heartbeat_loop, daemon=True).start()
        try:
            return self._turn_inner(msgs, reply_to)
        finally:
            self._hb_stop.set()

    def _turn_inner(self, msgs, reply_to):
        for rnd in range(MAX_TOOL_ROUNDS):
            if self.task:
                done_names = [tools_mod.parse_call(c)[0]
                              for m in msgs if m.get("role") == "assistant"
                              for c in (m.get("tool_calls") or [])]
                self.task.update(rounds=rnd + 1, last_tools=done_names)
                if rnd >= 1:  # 首轮秒回的不刷屏，从第 2 轮起原地刷新进度
                    self.task.push(self.tg)
            msg, usage, err = llm.chat(msgs, tools_mod.schemas())
            if err:
                self.log.log("llm_err", err=err)
                if self.task:
                    self.task.finish("FAILED", f"LLM 调用失败：{err[:80]}")
                    self.task.push(self.tg)
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
                tool_n = len([1 for m in msgs if m.get("role") == "tool"])
                if self.task:
                    self.task.finish("DONE", f"{tool_n} 次工具，{len(content)} 字交付")
                    self.task.push(self.tg)
                # 经验固化：非平凡任务（工具≥3）且非班次/内勤 → 异步提炼（cap-self-evolution）
                if tool_n >= 3 and not self._internal:
                    label = (self.history[-1]["content"][:24] if self.history else "任务")
                    tg_ref, log_ref, msgs_ref = self.tg, self.log, list(msgs)

                    def _evolve():
                        try:
                            result = evolve_mod.crystallize(msgs_ref, label, log_ref)
                            if tg_ref and ("🧬" in result or "失败" in result):
                                tg_ref.send(result)
                        except Exception as ee:  # noqa: BLE001 —— 固化失败绝不断主流程
                            log_ref.log("err", err=f"evolve: {ee}")
                    threading.Thread(target=_evolve, daemon=True).start()
                return self._say(content, reply_to, assistant_out=content)
            # 确认门分级：免确认路径（reports/ 等机器产物区）直行；班次轮次宽口径
            need_confirm = []
            for i, c in enumerate(calls):
                name, args = tools_mod.parse_call(c)
                cid = c.get("id") or f"call_{i}"
                if tools_mod.is_confirm(name) and not tools_mod.auto_approve(name, args, wide=self._internal):
                    need_confirm.append({"id": cid, "name": name, "args": args})
                    continue
                result = tools_mod.execute(name, args, self.log)
                msgs.append({"role": "tool", "tool_call_id": cid, "content": result})
            if need_confirm:
                self.pending = {"messages": msgs, "calls": need_confirm, "task": self.task}
                if self.task:  # WAITING_USER 落盘（tasks/<id>.json 唯一事实源，重启可恢复）
                    self.task.wait_user({"messages": msgs, "calls": need_confirm})
                    self.task.push(self.tg)
                lines = [f"• {c['name']}：{tools_mod.preview(c['name'], c['args'])}"
                         for c in need_confirm]
                confirm_text = ("⚠️ 需要你确认：\n" + "\n".join(lines) +
                                "\n\n点下方按钮，或回复「确认」；其他内容视为取消并按新指令处理。")
                if self.tg is not None and hasattr(self.tg, "send_confirm"):
                    err, _mid = self.tg.send_confirm(confirm_text)
                    if err:
                        return self._say(confirm_text, reply_to)
                    return None
                return self._say(confirm_text, reply_to)
        if self.task:
            self.task.finish("FAILED", "工具循环轮次用尽")
            self.task.push(self.tg)
        return self._say("⚠️ 工具循环轮次用尽，先回复到这里；需要细节可以再问我。", reply_to)

    def _say(self, text, reply_to=None, assistant_out=None):
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
    """主循环：长轮询 → 白名单过滤 → 逐条处理；offset 落盘；调度器随行。SIGTERM/SIGINT 优雅退出。"""
    stop = {"flag": False}

    def _sig(_a, _b):
        stop["flag"] = True

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)
    # 启动恢复：任务线收尾/复活 + offset 续读（治重启丢挂起态与重复投递）
    recovered = tasks_mod.recover(tg_client)
    if recovered:
        daemon.restore_pending(recovered)
    saved = load_state().get("update_offset")
    if saved and getattr(tg_client, "offset", 0) < saved:
        tg_client.offset = saved
    scheduler_mod.start(tg_client, daemon, stop)
    daemon.log.log("boot", note="daemon 启动（调度器+任务线已挂载）")
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
        if updates:
            save_state(update_offset=tg_client.offset)  # 消费即落盘
        for u in updates:
            cb = u.get("callback_query") or {}
            if cb:  # 内联按钮回调：等价于发送对应指令文本
                cmd = {"confirm:yes": "确认", "confirm:no": "取消本次操作"}.get(
                    cb.get("data", ""), "")
                if cmd:
                    daemon.log.log("in", text=f"[按钮]{cmd}")
                    try:
                        tg_client.answer_callback(cb.get("id"))
                        daemon.handle_text(cmd)
                    except Exception as e:  # noqa: BLE001
                        daemon.log.log("err", err=f"callback: {e}")
                continue
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
                if daemon.task:
                    daemon.task.finish("FAILED", f"内部错误：{type(e).__name__}")
                    daemon.task.push(tg_client)
                try:
                    tg_client.send(f"⚠️ 内部错误：{type(e).__name__}: {e}")
                except Exception:  # noqa: BLE001
                    pass
    tasks_mod.gc()
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
    print("任务线:", tasks_mod.TASKS_DIR, f"（在档 {len(list(tasks_mod.TASKS_DIR.glob('*.json')))} 条）")
    print(f"调度器: 08:00 早班 / 21:00 晚班（内置，--shift 可手动触发）")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Project X 常驻 agent daemon（v1 最小闭环）")
    ap.add_argument("--check", action="store_true", help="配置自检，不发网络请求")
    ap.add_argument("--once", metavar="TEXT", help="处理单条消息后退出（调试）")
    ap.add_argument("--shift", choices=["morning", "evening"], help="手动触发一个班次后退出（调度器同款流程）")
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
    if args.shift:
        recovered = tasks_mod.recover(tg_client)
        if recovered:
            daemon.restore_pending(recovered)
        daemon.run_shift(args.shift)
        return 0
    run(tg_client, daemon)
    return 0


if __name__ == "__main__":
    sys.exit(main())
