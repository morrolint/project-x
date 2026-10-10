# Project X — 个人助手（自建轻量版）

自建个人 AI 助手：Telegram 通道（常驻 agent）+ agent 循环（tool-use）+ 记忆层 + 定时汇报。Python，先跑在 Mac 本地。

## 已定决策（2026-10-07 与用户敲定，勿轻易推翻）

- **通道**：Telegram 先行（**2026-10-09 用户确认，推翻 10-07 的飞书优先**：推送链路已验证、用户日常在用；代价是收发全程依赖本机代理 127.0.0.1:7892。飞书预留——通道抽象留位，要国内直连时再接）
- **技术栈**：Python
- **部署**：Mac 本地（launchd 常驻）。**2026-10-10 用户定盘：载体 = 本机（Mac mini，M6/16GB），另一台 Mac mini 退役不再运行**（单机拓扑：无跨机同步，仓库即生产副本，origin 推送从可选升级为备份刚需）
- **LLM**：做成可切换——OpenAI 兼容接口 + 环境变量（候选：GLM 智谱 / DeepSeek / Claude）
- **源起**：用户嫌 OpenClaw 重 → 先用 ZCode 充当助手探索验证（2026-10-07）→ 决定固化为正式项目

## 蓝图

- **v0（✅ 已完成 2026-10-07）**：确定性脚本——早报/晚间简报（抓取 → 渲染 markdown → 写 `assistant/reports/`），launchd/cron 驱动，接管下述自动化
- **v1（🚧 2026-10-09 动工）**：常驻 agent daemon（`assistant/agent/`，launchd 托管）+ Telegram 长轮询入站 + agent 循环（读写文件 / 联网搜索 / 处理收件箱 / 记忆）+ markdown 记忆层。最小闭环已写完（待运行机实测）；动因：用户嫌 ZCode 不够定制，要常驻+随时可达。Octop 不再试装，降级为源码级设计参考
- **v2**：文档库检索、邮件入站、敏感文件留本地 + Tailscale 拓扑。参考项目：tinyhumansai/openhuman（118 个 OAuth 同步个人上下文）、rohitg00/agentmemory（agent 持久记忆）

## 目录约定

```
assistant/
├── TASKS.md        任务收件箱（一行一条；完成后移入"已完成"区）
├── reports/        早报 YYYY-MM-DD-早报.md；晚间简报 YYYY-MM-DD-晚间简报.md；trending.json sidecar
├── scripts/        report.py（报告生成；推送通道 = integrations/channels/ 插件，动态发现）
├── agent/          v1 常驻 agent（入站通道插件化 agent/channels/ + tool-use 循环 + 确认门；见其 README）
├── memory/         agent 长期记忆（markdown 按月归档，agent 运行时生成）
├── integrations/   集成子系统：README.md（契约铁律）/ registry.json（唯一事实来源）/ check_registry.py（校验器）/ sources/（数据源插件）/ channels/（推送插件）/ proposals/（接入提案）
├── skills/         agent 技能库（纯方法 markdown，不含可执行代码）
├── research/       调研档案（外部项目"抄作业清单"、吸收笔记；供后续会话与自动化查阅，不是集成）
└── docs/           个人文件库（含证件等敏感文件：仅在用户明确要求时读取，日常流程不扫描）
```

## 集成与扩展（2026-10-09 起）

- **一切接入走标准管线**：registry.json 声明（唯一事实来源）→ 类型化契约（report-source / push-channel / skill / capability / channel-inbound / memory）→ 生命周期（proposed→evaluating→active→rejected/retired）。细则见 `assistant/integrations/README.md` 四铁律。
- report.py 不认识任何具体数据源/推送通道：新增源 = sources/ 放插件、新增推送 = channels/ 放插件，各 + registry 加一行，脚本零改动。registry 改动后跑 `python3 assistant/integrations/check_registry.py` 校验。
- 自动化发现的有价值项目：纯方法类可直接固化为 skill（markdown）；需要装代码/服务/凭据的一律写 proposals/ 提案，用户在 TASKS.md 写"批准 <id>"后才执行。**禁止私自 pip/npm 安装。**

## 早报数据源（已验证可用）

- 中文要闻：blog.intelexe.cn 的"每天60秒读懂世界"——先抓索引页找当日 `/archives/xxxx` 链接（**按标题里的日期匹配**，站内最新可能不是当日 60s），再抓正文取 ~15 条
- GitHub Trending：https://github.com/trending（直连超时，脚本会自动走代理并重试）
- 热搜：微博官方接口 `weibo.com/ajax/side/hotSearch`（tophub 的微博榜节点已返回"无效的快照ID"，仅作备用）；科技动态：WebSearch（由自动化层补充）
- **规则**：任一源失败就跳过并在报告"数据源与备注"节注明，绝不中断

## 报告格式（现成样例见 assistant/reports/2026-10-09-早报.md）

- 早报五节：🗞️ 要闻速览（国内/国际/科技AI）/ 🐙 GitHub Trending（**逐项目解读**：中文讲清"是什么/有什么用"，相关项目标 ⭐ 并注明对个人助手的提升，样例见 2026-10-09 早报）/ 🤖 AI 一句话 / 📥 收件箱 / 数据源与备注
- 晚间简报三节：🌙 白天动态 / 🐙 Trending 复盘（与早报对比，↑↓ 标注；保留表格即可，深读在早报做）/ 📥 收件箱巡检
- 报告生成后自动推送 Telegram 摘要（凭据在 `assistant/.secrets.env`，git 忽略）

## 环境注意

- git 全局代理（已退役的那台 mini）曾是 127.0.0.1:7892（SpeedCat VPN）；**本机（2026-10-10 起唯一载体）实测 7890**（.secrets.env 已设）。代理端口因机而异——换机部署先 `scutil --proxy` 实测，用 `ASSISTANT_PROXY` 覆盖即可，代码零改动。台式机睡眠管理一步到位：`sudo pmset -c sleep 0`（空闲不睡）+ `sudo pmset -c autorestart 1`（断电恢复自动开机）
- 工作风格：用户中文交流，偏轻量方案、选型审慎；明确授权后放手自主推进，但**缺信息时直接问用户，不要扫描他的个人目录**

## 迁移状态（2026-10-07）

- 资产已从旧工作区（`~/.zcode/workspace/default/assistant/`）复制而来，本文件为交接文档
- **v0 已完成**：早报/晚间简报固化为 `assistant/scripts/report.py`（纯标准库 + 系统 curl）。要点：
  - 用法 `python3 assistant/scripts/report.py morning|evening [--date] [--output-dir] [--force]`；同名报告已存在则跳过（幂等）
  - 直连失败自动走代理 127.0.0.1:7892 并重试；单源失败跳过并在"数据源与备注"注明，绝不中断
  - 60s 源按标题日期匹配 archives 链接（站内最新文章可能是其他栏目）；GitHub Trending 按今日星数降序；热搜主源为微博官方接口 `ajax/side/hotSearch`（tophub 节点已失效，仅备用）
  - macOS 系统 Python 3.9 的 LibreSSL 与本地代理有 TLS 兼容问题，故用 curl 子进程而非 urllib
- 本项目已重建两班倒自动化（每天 08:00 早报 / 21:00 晚间简报）：脚本生成骨架，自动化做增强（WebSearch 补科技动态、写点评、处理收件箱）
- **待办**：确认新自动化稳定跑通后（约 1-2 天），去旧会话删除旧工作区的两班倒自动化（id `automation-5a22a4f5-4b36-4e76-af60-71c030626fda`），避免重复报告；旧会话的记忆层已盘点迁移（2026-10-07），其余资产与本项目重复，旧工作区可随自动化一并清理
