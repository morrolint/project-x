# Project X · 巨构个人助手

自建轻量 AI 助手：**Telegram 随时可达 + 桌面控制台 + 常驻 daemon**。
纯 Python 标准库（零框架零第三方依赖），跑在一台 Mac mini 上，所有数据不出本机。

> 状态：**v1 在役**。调度器接管早晚班、任务线五态、确认门分级、记忆 v0.2（BM25）、
> 经验固化引擎（自进化闭环 v1）、桌面控制台——全部过 30/30 测试与 registry 校验器。

## 它能做什么

- **随时对话**：Telegram（@m0rro_bot，白名单单用户）或桌面控制台 `http://127.0.0.1:8787`，两个入口共用同一个记忆与确认门
- **早晚班自治**：08:00 早报 / 21:00 晚间简报由内置调度器自动生成（抓取 → 逐项目深读 → 增强 → 推送 Telegram）
- **任务与提醒**："30 分钟后提醒我"“以后帮我 X"——任务线五态跟踪（RUNNING/WAITING_USER/DONE/FAILED/CANCELED）
- **Trending 观测**：日/周/月榜实时抓取，高热新面孔主动推送（每 3 小时扫描）
- **出图**：编辑级图表（SVG→PNG），榜单与对比数据可视化
- **知识库**：检索自己的架构宪法、决策记录、方法技能与调研档案（BM25）
- **自进化**：非平凡任务自动沉淀为技能（经验固化 → registry 登记 → 校验过门），每次变更留审计日志
- **安全边界**：`docs/` 敏感文件与一切密钥任何口径不进上下文；危险写操作走确认门（Telegram 按钮 / 控制台预览）

## 架构一图

```
入口    Telegram（channels/ 插件）  +  控制台 127.0.0.1:8787（agent/console.py）
  ↓          agent/daemon.py —— 轮询 · LLM 循环 · 任务线 · 确认门 · 调度器
执行        agent/tools.py ×14（收件箱/报告/榜单/图表/文件/提醒/活动/记忆/知识库）
  ↓
数据    memory/（BM25 双层）· reports/ · logs/ · tasks/ · state.json
知识    skills/ · personas/ · integrations/（registry 管线）· research/ · web/kit/
```

分层、不变量、隐含假设与增长触发器详见 [assistant/ARCHITECTURE.md](assistant/ARCHITECTURE.md)；
重大决策见 [docs/adr/](docs/adr/)；自进化审计线见 [docs/evolution.md](docs/evolution.md)。

## 快速开始（部署到一台新 Mac mini）

```bash
git clone git@github.com:morrolint/project-x.git && cd project-x
# 1. 凭据：assistant/.secrets.env 填 TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID /
#    LLM_API_KEY（智谱 coding 端点）与 ASSISTANT_PROXY（本机实测端口）
# 2. 自检
python3 assistant/agent/daemon.py --check
# 3. 常驻（launchd + caffeinate + KeepAlive，模板在 assistant/agent/com.project-x.agent.plist）
launchctl load ~/Library/LaunchAgents/com.project-x.agent.plist
```

## 仓库导航

| 路径 | 内容 |
|---|---|
| [assistant/README.md](assistant/README.md) | 助手使用手册（给日常使用） |
| [assistant/ARCHITECTURE.md](assistant/ARCHITECTURE.md) | 架构宪法（分层/不变量/假设/触发器） |
| [assistant/agent/](assistant/agent/) | daemon 本体（含 [README](assistant/agent/README.md)） |
| [assistant/integrations/](assistant/integrations/) | 集成管线：registry + 校验器 + 插件契约 |
| [assistant/research/](assistant/research/) | 调研档案（RSI/知识库/竞品对比） |
| [docs/adr/](docs/adr/) | 决策记录（为什么这样设计） |
| [docs/evolution.md](docs/evolution.md) | 自进化审计日志 |
| [HANDOFF.md](HANDOFF.md) | 交接快照（新会话第一分钟读它） |

## 参照系（产物质量的约束）

测试套件 `assistant/tests/run.py`（30/30）· registry 校验器 `check_registry.py` ·
oil-ui 独立视觉评审（基线 7/10，见 web/kit/review-2026-10-14/）· 产品经理验收标准（personas/pm.md）。

## 演进

v0 确定性脚本（✅）→ **v1 常驻自建 agent（当前）** → v2 文档库检索/邮件入站/Tailscale（提案与调研就绪）。
演进策略：prompt 层跑稳再固化成代码；每次进化留决策记录与审计日志。
