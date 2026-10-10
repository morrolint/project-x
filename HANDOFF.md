# Project X 交接文档

> 生成于 2026-10-09。本文件是**时点快照**，帮新会话/新人快速接管；长期有效的约定以
> [AGENTS.md](AGENTS.md) 为准（工作区指令，每次会话自动加载），集成细则以
> [assistant/integrations/README.md](assistant/integrations/README.md) 为准。三者冲突时以 AGENTS.md 为最高。
> 另有 [HANDOFF-DOTS.md](HANDOFF-DOTS.md)：给 OpenAI Dots 的功能迁移规格书——Dots 上运行本助手的**独立第二实例**，与本地实例互不通信（2026-10-10）。

## 一、这是什么项目

个人 AI 助手（自建轻量版）：飞书通道（未动工）+ agent 循环（v1）+ 记忆层（v1）+ 定时汇报（✅ 已运行）。
Python，Mac 本地，用户中文交流、偏轻量方案。开发策略是**演进式**：prompt 层先跑稳，哪个环节不稳再固化成脚本。

## 二、当前状态（2026-10-09）

**已在生产运行：**

| 组件 | 状态 | 位置 |
|---|---|---|
| 两班倒自动化 | ✅ 每天 08:00 早报 / 21:00 晚间简报（**2026-10-10 迁至本机**，另一台 mini 随退役停摆） | 本机 ZCode workspace 的 automation（cron `0 8,21 * * *`，prompt 内按小时分支；原实例 `automation-30c63702…` 已废弃） |
| 报告脚本 v0 | ✅ 纯标准库 + 系统 curl，数据源插件化 | `assistant/scripts/report.py`（`morning`/`evening`，`--date/--output-dir/--force`，幂等） |
| 数据源插件 ×3 | ✅ 60秒读懂世界 / GitHub Trending / 微博热搜官方接口 | `assistant/integrations/sources/`（report.py 动态发现，新增源零改动） |
| Trending sidecar | ✅ `reports/YYYY-MM-DD-trending.json`，晚间对比读 morning 键 | 呈现层（早报逐项目解读）与数据层解耦 |
| Telegram 推送 | ✅ bot [@m0rro_bot](https://t.me/m0rro_bot)（chat_id 8941473962） | `assistant/.secrets.env`（git 忽略）；报告生成后自动推，失败不阻断 |
| 集成子系统 | ✅ registry + 契约 + 生命周期 | `assistant/integrations/`（四铁律：注册表唯一事实来源 / report.py 不认识具体源 / 不私自安装代码 / 失效即退役） |
| 技能库 | ✅ 3 个技能：Trending 逐项目深读 / 图表设计（diagram-design 提炼）/ 近 30 天调研法（last30days 提炼） | `assistant/skills/` |
| v1 常驻 agent | 🚧 最小闭环已写完（Telegram 入站 + tool-use 循环 + 确认门 + markdown 记忆），单测/冒烟全过；**待运行机配 LLM key 后实测** | `assistant/agent/`（README 含部署步骤；launchd 模板 `com.project-x.agent.plist`） |

**Git**：main 分支，最新 `11eebe8`；**有远端 `origin`（github.com/morrolint/project-x）但从未推送**——推送需用户明确说一声。凭据文件已被 `.gitignore` 排除，推送前无需处理。

## 三、自动化怎么运转

1. 08:00 触发 → 跑 `report.py morning` 生成骨架并推 Telegram → 用 Edit 增强（WebSearch 补科技动态、按 skill 做逐项目解读）→ 处理 TASKS.md 收件箱 → 汇报。
2. 21:00 触发 → 跑 `report.py evening`（自动与早报 sidecar 对比 ↑↓/NEW）→ 收件箱巡检 → 汇报。
3. **集成发现是早班职责**：⭐ 项目 → 查 registry → 纯方法类直写技能 / 需装代码的写 `proposals/` 提案（等你批准）。
4. **批准一个集成**：在 `assistant/TASKS.md` 待办写一行 `批准 <id>`，下一次自动化收件箱巡检时执行。

手动跑：`python3 assistant/scripts/report.py morning|evening [--date] [--output-dir] [--force]`。

## 四、悬而未决（按优先级）

1. **08:00 漏班**（已随旧 mini 退役转移阵地）：10-08 早班触发了但无产出（会话早死，原因未查明）；10-09 早班根本没触发（旧 mini 睡眠）。问题本体转移到本机（**本机也是 mini，实测当前 sleep=1，同样会睡**）：`sudo pmset -c sleep 0` + `sudo pmset -c autorestart 1` 一步根治，无合盖问题。ZCode 自动化触发还依赖本机 ZCode 应用在运行。
2. **旧工作区清理**（随 mini 退役基本消解）：mini 上新旧两个自动化（`automation-5a22a4f5…` 旧 / `automation-30c63702…` 新）随其关机自然停摆，重复简报问题消失；两班倒已于 2026-10-10 在本机重建，mini 无需再清理（若开机撞出重复简报，去其 ZCode Automations 页删掉即可）。
3. **三条集成提案待批**：`cap-last30days`（2026-10-09 用户新增；**第一步零安装方法论提炼已完成**——落地 `skill-fresh-30d-research` 并产出吸收档案，只剩"装引擎"档待批，需 Python 3.12+）、`cap-agent-reach`（早报新源保险，与 last30days 定位重叠，建议二选一）、`cap-pageindex`（v2 文档检索，注意敏感文件排除）——后两条 registry 有条目但提案文件仍未落盘，批准前应先补齐。`harness-octop` 已定盘：**不试装不安装，降级为源码级设计参考**（2026-10-09，用户改 Telegram 后其飞书通道价值缩水），registry 已标 rejected 留档。
   另：knowledge-work-plugins 的"抄作业清单"已落盘 `research/2026-10-09-knowledge-work-plugins-抄作业清单.md`（2026-10-09 用户批准吸收）——其中**双层记忆**与**收件箱四区制**是 v1 第二批记忆层/收件箱升级的具体蓝图；10-09 早报 5 个 ⭐ 项目的消化账：diagram-design ✅ 技能、knowledge-work-plugins ✅ 清单、claude-mem ✅ 设计参照、mattpocock/skills（素材库按需取用）、rea（等 v1 支持 MCP）。
4. **v1 agent 部署**（2026-10-09 动工，代码已在本仓库 `assistant/agent/`；**2026-10-10 载体定盘：部署在本机这台 mini**）：本机上需 ① `.secrets.env` 补 Telegram 凭据（**从退役那台 mini 拷，它关机前办**）——LLM key/端点/代理已就绪；② `python3 assistant/agent/daemon.py --check` 自检；③ 按 plist 模板装 launchd。稳定前 ZCode 两班倒自动化照跑（并存），稳定后 daemon 接管定时任务。Telegram 收发走 VPN（本机 7890），断网 = 通道断（daemon 自动重连）。
5. **推送依赖 VPN**：Telegram 全程走 127.0.0.1:7892，VPN 不开则推送失败（报告仍会生成并在文末备注）。通道改 Telegram 后此依赖变重（v1 入站也靠它）。

## 五、踩坑记录（别再踩）

- **macOS 系统 Python 3.9 的 LibreSSL 与本地代理 TLS 不兼容**（urllib 握手被断）→ 一律用 curl 子进程（已封装在 `integrations/sources/_common.py#http_get`：直连→代理→重试）。
- **GitHub 直连超时是常态**，走代理 `127.0.0.1:7892`（SpeedCat VPN）；VPN 不开则 GitHub 系全挂，微博/60s 不受影响（国内直连）。
- **tophub 微博榜节点已失效**（"无效的快照ID"），主源是微博官方 `ajax/side/hotSearch`，tophub 仅兜底。
- **GitHub Trending 全天漂移**：页面顺序≠星数序（脚本已按星数重排）；榜单结论必须标注抓取时点；晚间对比是同源同时段口径，外部榜单（如知乎精选）数字不可对账。
- **60s 源要按标题日期匹配 archives 链接**（站内最新文章可能是其他栏目，如 3161）。
- **ZCode 平台：一个会话只能创建一个自动化**（第二次 CronCreate 报错）；多班次用单 cron 双触发 + prompt 内 `date +%H` 分支。CronUpdate 改 cron 必须同步改 title。
- **Telegram bot 收不到 /start 的排查路径**：getWebhookInfo 看 pending → getMe 确认 bot 身份 → setMyName 改名验证客户端聊天对象与 token 同源（本次 chat 对了但消息延迟可见，重发即解决）。

## 六、v1 / v2 路线图（已验证的设计输入）

- **v1（Telegram 常驻 bot + agent 循环 + 记忆层，2026-10-09 动工）**：通道抽象参考 Octop Gateway（消息归一化，源码级借鉴不安装）/ openhuman（邮件=通道之一）；重大操作必须返回 NeedsConfirmation（✅ 已实现：write_file 确认门）；运行日志可回放 + 成本记账（日志 JSONL 已埋 usage，回放/记账在第二批）；记忆层吸收 agentmemory 四层分类 + hindsight retain/recall/reflect 命名 + 写入前隐私过滤 + BM25 起步不上向量库（✅ v0.1 已实现按月归档 + 词元召回）；LLM 走 OpenAI 兼容接口 + 环境变量（GLM/DeepSeek/Claude 可切换，✅ 已实现）。最小闭环已写完，待运行机实测。
- **v2（文档检索 + 邮件入站 + Tailscale）**：PageIndex 本地模式（vectorless 树索引），`docs/` 敏感文件默认排除；邮件按通道抽象接入。
- 参考项目档案（含为什么不抄什么）见 2026-10-08/09 会话调研与 registry 条目；2026-10-09 知乎榜单五项目（openhuman/agentmemory/CloakBrowser/mattpocock-skills/AiToEarn）评估见 `research/2026-10-09-知乎榜单五项目-评估.md`。

## 七、给新会话的第一分钟

1. 读 AGENTS.md（自动加载）+ 本文件。
2. `git log --oneline` 看最近提交；`ls assistant/reports/ | tail` 看最近报告产出。
3. 想知道"现在有哪些集成" → `assistant/integrations/registry.json`；"在等什么" → 本文第四节 + `integrations/proposals/`。
4. 别碰 `assistant/docs/`（敏感文件库，用户明确要求才能读）；别恢复 srdcloud 的 git 重写规则（历史遗留，用户烦它）。
