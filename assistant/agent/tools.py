"""agent 工具集（v1 最小闭环 13 个）：收件箱 / 报告 / 文件与目录 / 活动 / 记忆。

契约对齐 assistant/integrations/README.md：
- 新增工具 = 本文件加一个 Tool 条目，schemas() 自动带给 LLM；
- confirm=True 的工具由 daemon 的确认门（NeedsConfirmation）拦截，须用户在 Telegram 回复「确认」；
- 路径守卫：一切读写限 assistant/ 内，docs/（敏感文件库）与密钥文件永远拒触。
"""

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
ASSISTANT_DIR = AGENT_DIR.parent
TASKS_FILE = ASSISTANT_DIR / "TASKS.md"
REPORT_PY = ASSISTANT_DIR / "scripts" / "report.py"
LOGS_DIR = AGENT_DIR / "logs"

READ_CAP = 16000      # read_file 单次最大字符（2026-10-14 调大：报告增强需整读增强后的报告）
RESULT_CAP = 4000     # 工具结果回传 LLM 的最大字符


# ---------------------------------------------------------------- 路径守卫

def _safe_path(path_str, for_write):
    """把相对路径锚到 assistant/，并拒绝越界、docs/ 与密钥文件。返回 (Path|None, 错误|None)。"""
    p = Path(str(path_str)).expanduser()
    if not p.is_absolute():
        p = ASSISTANT_DIR / p
    try:
        p = p.resolve()
    except OSError:
        return None, "路径无法解析"
    root = str(ASSISTANT_DIR.resolve())
    if str(p) == root or not str(p).startswith(root + "/"):
        return None, "路径必须在 assistant/ 目录内"
    parts = p.relative_to(root).parts
    if parts[0] == "docs":
        return None, "docs/ 是用户敏感文件库，工具禁止访问；用户明确要求时也应让用户自己操作"
    if parts[0] == ".git" or p.name == ".secrets.env" or p.suffix == ".pem":
        return None, "该路径含凭据或敏感信息，禁止访问"
    return p, None


# ---------------------------------------------------------------- 收件箱（协议同 scripts/report.py#read_inbox）

def _placeholder(s):
    return "（示例格式）" in s or "（暂无）" in s


def _section_idx(lines, title):
    for i, ln in enumerate(lines):
        if ln.strip() == title:
            return i
    return None


def _next_section(lines, from_idx):
    for i in range(from_idx, len(lines)):
        if lines[i].startswith("## "):
            return i
    return len(lines)


def _todo_items(lines):
    start = _section_idx(lines, "## 待办")
    if start is None:
        return []
    out = []
    for ln in lines[start + 1:_next_section(lines, start + 1)]:
        s = ln.strip()
        if s.startswith("- ") and not _placeholder(s):
            out.append(s[2:].strip())
    return out


def inbox_list():
    if not TASKS_FILE.exists():
        return "收件箱文件不存在（assistant/TASKS.md）。"
    items = _todo_items(TASKS_FILE.read_text(encoding="utf-8").splitlines())
    if not items:
        return "收件箱无待办。"
    return "当前待办：\n" + "\n".join(f"{i}. {t}" for i, t in enumerate(items, 1))


def inbox_add(text):
    text = str(text).strip()
    if not text:
        return "任务内容为空。"
    if not TASKS_FILE.exists():
        TASKS_FILE.write_text("# 任务收件箱\n\n## 待办\n\n## 已完成\n\n- （暂无）\n",
                              encoding="utf-8")
    lines = TASKS_FILE.read_text(encoding="utf-8").splitlines()
    start = _section_idx(lines, "## 待办")
    if start is None:
        lines += ["", "## 待办"]
        start = _section_idx(lines, "## 待办")
    end = _next_section(lines, start + 1)
    body = [ln for ln in lines[start + 1:end] if ln.strip() and not _placeholder(ln.strip())]
    body.append(f"- {text}")
    lines[start + 1:end] = [""] + body + [""]
    TASKS_FILE.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return f"已加入收件箱：{text}"


def inbox_done(number):
    try:
        n = int(number)
    except (TypeError, ValueError):
        return "序号必须是整数。"
    if not TASKS_FILE.exists():
        return "收件箱文件不存在。"
    lines = TASKS_FILE.read_text(encoding="utf-8").splitlines()
    items = _todo_items(lines)
    if n < 1 or n > len(items):
        return f"序号超出范围（当前 1-{len(items)}）。"
    target = items[n - 1]
    start = _section_idx(lines, "## 待办")
    end = _next_section(lines, start + 1)
    for i in range(start + 1, end):
        if lines[i].strip() == f"- {target}":
            del lines[i]
            end -= 1
            break
    dstart = _section_idx(lines, "## 已完成")
    if dstart is None:
        lines += ["", "## 已完成"]
        dstart = _section_idx(lines, "## 已完成")
    dend = _next_section(lines, dstart + 1)
    body = [ln for ln in lines[dstart + 1:dend] if ln.strip() and not _placeholder(ln.strip())]
    body.append(f"- ✅ {target}（{datetime.now():%Y-%m-%d}）")
    lines[dstart + 1:dend] = [""] + body + [""]
    TASKS_FILE.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
    return f"已完成并移入「已完成」：{target}"


# ---------------------------------------------------------------- 报告 / 文件 / 记忆

def run_report(kind="morning", force=False):
    """调 scripts/report.py 生成报告；推送 Telegram 由脚本自身完成。"""
    if kind not in ("morning", "evening"):
        return "kind 只能是 morning 或 evening。"
    if CHANNEL is not None and hasattr(CHANNEL, "send"):
        CHANNEL.send(f"⏳ 正在生成{'早报' if kind == 'morning' else '晚间简报'}，通常需要 1-2 分钟…")
    cmd = [sys.executable, str(REPORT_PY), kind] + (["--force"] if force else [])
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=420)
    except subprocess.TimeoutExpired:
        return "报告生成超时（>420s），可稍后重试。"
    out = r.stdout.decode("utf-8", errors="replace")
    err = r.stderr.decode("utf-8", errors="replace").strip()
    tail = "\n".join(out.splitlines()[-12:])
    if err:
        tail += f"\n[stderr] {err[-400:]}"
    return (f"exit={r.returncode}\n{tail}\n"
            f"（报告在 assistant/reports/，Telegram 推送由脚本自动完成）")


def list_dir(path="."):
    """列出 assistant/ 下某目录内容（目录在前，各按名称排序，最多 100 项）。"""
    p, err = _safe_path(path, for_write=False)
    if err:
        return err
    if not p.exists():
        return f"路径不存在：{p}"
    if not p.is_dir():
        return f"不是目录（用 read_file 读它）：{p}"
    entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
    if not entries:
        return f"{p}：（空目录）"
    lines = []
    for e in entries[:100]:
        if e.is_dir():
            lines.append(f"[目录] {e.name}/")
        else:
            try:
                size = e.stat().st_size
            except OSError:
                size = -1
            lines.append(f"        {e.name}（{size} 字节）")
    if len(entries) > 100:
        lines.append(f"…（共 {len(entries)} 项，仅显示前 100）")
    return f"{p}：\n" + "\n".join(lines)


def _fmt_k(n):
    """1234 -> 1.2k；Telegram 紧凑显示。"""
    s = f"{n/1000:.1f}".rstrip("0").rstrip(".")
    return s + "k" if n >= 1000 else str(n)


def trending_top(since="today"):
    """实时抓取 GitHub Trending（复用 integrations/sources/ 插件，与早晚报告同源同口径）。
    输出为 Telegram 友好的分行列表（Telegram 不渲染 markdown 表格）。"""
    import importlib.util
    from datetime import date as _date
    src = ASSISTANT_DIR / "integrations" / "sources" / "github_trending.py"
    if not src.exists():
        return "数据源插件不存在：github_trending.py"
    sources_dir = str(src.parent)
    if sources_dir not in sys.path:
        sys.path.insert(0, sources_dir)  # 插件依赖同目录的 _common
    spec = importlib.util.spec_from_file_location("assistant_src_github_trending", src)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        return f"插件加载失败：{type(e).__name__}: {e}"
    if since not in ("today", "weekly", "monthly"):
        since = "today"
    data, note = mod.fetch(_date.today(), since=since)
    if not data:
        return f"Trending 抓取失败：{note}"
    unit, label = {"today": ("日", "日榜"), "weekly": ("周", "周榜"),
                   "monthly": ("月", "月榜（近30天）")}[since]
    lines = [f"GitHub Trending {label} Top10（{note}）："]
    for i, r in enumerate(data, 1):
        lines.append(f"{i}. {r['name']}  +{_fmt_k(r['stars_today'])}/{unit}")
        lines.append(f"   总{_fmt_k(r['stars_total'])}★ · {r['lang']} · {r['desc']}")
    return "\n".join(lines)


CHANNEL = None  # daemon 启动时注入通道实例；--once 模式保持 None（send_chart 只渲染不发送）


def send_chart(svg, caption=""):
    """把按 diagram-design 技能生成的自包含 SVG 渲染成 PNG（macOS 自带 qlmanage，零安装）
    并以图片消息发送；无通道时只渲染并返回文件路径。"""
    import subprocess
    import tempfile
    svg = str(svg).strip()
    if not svg.startswith("<"):
        return "参数应是完整 SVG 文本（以 <svg 开头）。"
    tmpdir = Path(tempfile.mkdtemp(prefix="chart_"))
    svg_path = tmpdir / "chart.svg"
    svg_path.write_text(svg, encoding="utf-8")
    try:
        r = subprocess.run(["qlmanage", "-t", "-s", "1400", "-o", str(tmpdir), str(svg_path)],
                           capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        return "qlmanage 渲染超时"
    png_path = tmpdir / "chart.svg.png"
    if r.returncode != 0 or not png_path.exists():
        return f"qlmanage 渲染失败：{r.stderr.decode('utf-8', errors='replace')[:200]}"
    if CHANNEL is not None and hasattr(CHANNEL, "send_photo"):
        err = CHANNEL.send_photo(png_path, caption=str(caption)[:900])
        if err:
            return f"渲染成功但发送失败：{err}（PNG 已保留：{png_path}）"
        return f"图表已发送：{str(caption)[:80]}"
    return f"已渲染图表（当前无通道，未发送）：{png_path}"


def read_file(path):
    p, err = _safe_path(path, for_write=False)
    if err:
        return err
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"读取失败：{e}"
    more = f"\n…（已截断，全文 {len(text)} 字符）" if len(text) > READ_CAP else ""
    return f"{p}：\n{text[:READ_CAP]}{more}"


def write_file(path, content=""):
    p, err = _safe_path(path, for_write=True)
    if err:
        return err
    content = str(content)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        existed = p.exists()
        p.write_text(content, encoding="utf-8")
    except OSError as e:
        return f"写入失败：{e}"
    return f"已写入 {p}（{'覆盖' if existed else '新建'}，{len(content)} 字符）"


def activity_recent(days=1):
    """汇总最近 N 天 daemon 活动日志（对话轮次/工具调用/token/错误/任务态）。"""
    import json as _json
    from datetime import datetime as _dt, timedelta as _td
    if not LOGS_DIR.exists():
        return "暂无活动日志。"
    lines_out, turns, tools_n, tokens, errs, states = [], 0, 0, 0, 0, {}
    until = _dt.now().date() + _td.timedelta(1)
    since = _dt.now().date() - _td.timedelta(int(days) - 1)
    d = since
    while d < until:
        f = LOGS_DIR / f"{d:%Y-%m-%d}.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    r = _json.loads(line)
                except ValueError:
                    continue
                dr = r.get("dir")
                if dr == "in":
                    turns += 1
                    lines_out.append(f"{r['ts'][11:16]} ▶ {str(r.get('text',''))[:40]}")
                elif dr == "tool":
                    tools_n += 1
                elif dr == "llm":
                    tokens += (r.get("usage") or {}).get("total_tokens", 0)
                elif dr in ("llm_err", "err", "send_err"):
                    errs += 1
                elif dr == "task":
                    states[r.get("state", "?")] = states.get(r.get("state", "?"), 0) + 1
        d += _td.timedelta(1)
    if not lines_out:
        return f"近 {days} 天无活动。"
    head = (f"近 {days} 天活动：{turns} 轮对话 / {tools_n} 次工具 / {tokens:,} tokens / {errs} 个错误"
            + (f" / 任务态 {states}" if states else ""))
    return head + "\n" + "\n".join(lines_out[-15:])


def remind_in(minutes, text):
    """设一个相对提醒（分钟后的推送提醒）。调度器到期经 Telegram 推送。"""
    import time as _time
    try:
        m = int(minutes)
    except (TypeError, ValueError):
        return "minutes 需是整数。"
    if m <= 0 or m > 60 * 24 * 30:
        return "分钟数需在 1 分钟到 30 天之间。"
    import json as _json
    from daemon_state import load_state, save_state  # 薄封装，避免循环 import
    rems = load_state().get("reminders") or []
    rems.append({"due": _time.time() + m * 60, "text": str(text)[:200]})
    save_state(reminders=rems)
    from datetime import datetime as _dt
    return f"已设提醒：{_dt.now() + __import__('datetime').timedelta(minutes=m):%m-%d %H:%M} —— {text[:60]}"


def memory_save(text):
    from memory import retain
    return f"已写入记忆（{retain(str(text))}）：{str(text)[:80]}"


def memory_search(query):
    from memory import recall
    hits = recall(str(query), top=5)
    return "\n".join(hits) if hits else "没有相关记忆。"


# ---------------------------------------------------------------- 工具注册与调度

class Tool:
    def __init__(self, name, desc, props, required, fn, confirm=False):
        self.name, self.desc, self.props = name, desc, props
        self.required, self.fn, self.confirm = required, fn, confirm


TOOLS = [
    Tool("inbox_list", "查看 TASKS.md 收件箱当前待办（带序号）",
         {}, [], inbox_list),
    Tool("inbox_add", "把一件事写进收件箱待办（一行一条；自动化早班每天会处理）",
         {"text": {"type": "string", "description": "任务内容，写清「要什么」"}},
         ["text"], inbox_add),
    Tool("inbox_done", "把待办按序号标记完成，移入「已完成」区",
         {"number": {"type": "integer", "description": "inbox_list 输出的序号"}},
         ["number"], inbox_done),
    Tool("run_report", "生成早报(morning)或晚间简报(evening)；脚本完成后自动推送 Telegram",
         {"kind": {"type": "string", "enum": ["morning", "evening"]},
          "force": {"type": "boolean", "description": "同名报告已存在时是否覆盖，默认否"}},
         ["kind"], run_report),
    Tool("trending_top", "实时抓取 GitHub Trending 榜单 Top10；用户问'最近30天/月榜'用 monthly，'本周'用 weekly",
         {"since": {"type": "string", "enum": ["today", "weekly", "monthly"],
                     "description": "时间窗口，默认 today"}},
         [], trending_top),
    Tool("send_chart", "把榜单/对比类数据做成编辑级图表以图片消息发送。先 read_file 读 "
                      "assistant/skills/diagram-design/SKILL.md，按其方法产出完整自包含 SVG 文本"
                      "（宽约 1000 的 viewBox；paper/ink/muted/accent 语义色；accent 只给最重要的 1-2 项）",
         {"svg": {"type": "string", "description": "完整 SVG 文档文本（<svg> 开头）"},
          "caption": {"type": "string", "description": "随图发送的一行说明"}},
         ["svg"], send_chart),
    Tool("read_file", "读 assistant/ 下的文本文件（docs/ 与密钥文件禁读；单次最多 8000 字符）",
         {"path": {"type": "string", "description": "assistant/ 内相对路径或绝对路径"}},
         ["path"], read_file),
    Tool("list_dir", "列出 assistant/ 下某目录的内容（查技能/提案/报告用什么文件时先用它探路）",
         {"path": {"type": "string", "description": "assistant/ 内相对路径，默认当前目录 ."}},
         [], list_dir),
    Tool("write_file", "写 assistant/ 下的文本文件（docs/ 与密钥文件禁写）。需用户确认",
         {"path": {"type": "string", "description": "assistant/ 内相对路径或绝对路径"},
          "content": {"type": "string", "description": "完整文件内容（整体覆盖）"}},
         ["path", "content"], write_file, confirm=True),
    Tool("memory_save", "往长期记忆写一条（用户偏好、项目进展、约定、教训）",
         {"text": {"type": "string", "description": "一句话记忆"}},
         ["text"], memory_save),
    Tool("remind_in", "设提醒：N 分钟后经 Telegram 推送一条提醒文本",
         {"minutes": {"type": "integer", "description": "多少分钟后提醒"},
          "text": {"type": "string", "description": "提醒内容"}},
         ["minutes", "text"], remind_in),
    Tool("activity", "查看助手最近的活动日志（干了什么/花了多少 token/有无错误）",
         {"days": {"type": "integer", "description": "回看天数，默认 1"}},
         [], activity_recent),
    Tool("memory_search", "按关键词检索长期记忆",
         {"query": {"type": "string"}},
         ["query"], memory_search),
]


def schemas():
    return [{"type": "function", "function": {"name": t.name, "description": t.desc,
             "parameters": {"type": "object", "properties": t.props, "required": t.required}}}
            for t in TOOLS]


def find(name):
    for t in TOOLS:
        if t.name == name:
            return t
    return None


def parse_call(call):
    """解析 LLM 的 tool_call。返回 (name, args dict)。"""
    fn = call.get("function") or {}
    try:
        args = json.loads(fn.get("arguments") or "{}")
    except ValueError:
        args = {}
    return fn.get("name", ""), (args if isinstance(args, dict) else {})


# 确认门分级：这些路径是机器产物区/班次操作区，写它们免确认（对话轮次窄口径）
_AUTO_PATHS_CHAT = ("reports/",)
# 班次/内勤轮次的宽口径：技能、提案、registry、收件箱也是自动化合法工作区
_AUTO_PATHS_WIDE = _AUTO_PATHS_CHAT + ("skills/", "integrations/proposals/",
                                       "integrations/registry.json", "TASKS.md", "memory/")


def auto_approve(name, args, wide=False):
    """确认门分级：命中免确认路径区的写操作返回 True（详见 Alex 进度面板方案 / Dots Custom Rules）。
    wide=True 为班次/内勤上下文（技能/提案/registry 也免确认）。"""
    if name != "write_file":
        return False
    p, err = _safe_path(args.get("path", ""), for_write=True)
    if err:
        return False
    rel = str(p.relative_to(ASSISTANT_DIR.resolve()))
    rules = _AUTO_PATHS_WIDE if wide else _AUTO_PATHS_CHAT
    return any(rel == r.rstrip("/") or rel.startswith(r) for r in rules)


def is_confirm(name):
    t = find(name)
    return bool(t and t.confirm)


def preview(name, args):
    """确认门给用户看的预览。"""
    if name == "write_file":
        content = str(args.get("content", ""))
        return (f"写入 {args.get('path')}（{len(content)} 字符）\n"
                f"开头预览：{content[:300]}")
    return json.dumps(args, ensure_ascii=False)[:400]


def execute(name, args, log=None):
    """执行工具并返回文本结果（绝不抛异常，与数据源插件同一约定）。"""
    t = find(name)
    if not t:
        out = f"未知工具：{name}"
    else:
        try:
            out = str(t.fn(**{k: v for k, v in args.items() if k in t.props}))
        except Exception as e:  # noqa: BLE001
            out = f"工具执行失败：{type(e).__name__}: {e}"
    out = out[:RESULT_CAP]
    if log:
        log.log("tool", name=name, args=args, result=out[:300])
    return out
