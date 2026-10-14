# ARCHITECTURE · Project X 架构宪法

> 改架构前必读。本文声明**分层、不变量、隐含假设、增长触发器**四件事；
> 重大决策的"为什么"在 `docs/adr/`（编号决策记录）。本文与代码冲突时，以代码为准并立即修订本文。

## 分层

```
L0 建造者层   ZCode 会话（工程侧）—— 开发、迭代、人肉补班（历史）
              资产：~/.zcode/skills（工程个人件，不属于本项目）
L1 服务层     agent/：daemon（轮询+LLM 循环+任务线+调度器）+ channels/（入站插件）
              + tools.py（工具与守卫）+ memory.py + scheduler.py + llm.py/_http.py
L2 确定性层   scripts/：report.py（报告骨架，无 LLM）+ notify.py（通知）
L3 知识层     skills/（方法）+ personas/（人设）+ integrations/（registry+插件管线）
              + research/（调研档案）+ web/kit/（UI 套件）
L4 数据层     memory/ + reports/ + TASKS.md + logs/ + tasks/ + state.json
              —— 文件即接口：每类数据有唯一属主模块与格式，见下表
```

## 不变量（违反即 bug，修代码不改文档）

1. **用户数据不出域**：`docs/` 与一切密钥（.secrets.env/*.pem）任何口径不进 LLM 上下文、不进仓库、不进日志正文；记忆写入经 Memory Defense 打码。
2. **失败不阻断**：单数据源/单工具/单插件/单班次失败只降级并留痕（日志或报告备注），绝不中断整班或 daemon。
3. **易失状态必有磁盘事实源**：任务态 `tasks/<id>.json`、游标与调度账 `state.json`、集成 `registry.json`、对比基线 `trending.json`、稳定事实 `facts.md`——重启可恢复，不靠进程内存。
4. **危险写必过确认门**：分级策略数据化在 `agent/gate_rules.json`；`docs/` 与密钥**任何口径永拦**（策略文件不可豁免）。
5. **插件一律走管线**：新集成 = 目录 + registry 条目 + check_registry 通过；没有条目的集成视为不存在。
6. **本体优先**：本体能消费的方法/皮肤/决策进仓库（L1-L4）；工程侧个人件进 `~/.zcode`（L0），不得反向依赖。

## 隐含假设（当前为优点的约束，改动前必读）

- **单用户**：chat 白名单单值、无鉴权（webui 计划含 Tailscale 私网）。
- **单实例**：同一 Telegram bot 只允许一个 getUpdates 消费者；无文件锁，并发写靠此约定。
- **单机**：全部状态在本地文件系统；跨机 = 新架构，需先立 ADR。
- **零依赖**：Python 3.9 标准库 + curl 子进程；HTTP 经 `_http.py`/`notify.py`/channels 插件，不引入 requests。
- **LLM 可替换**：OpenAI 兼容接口 + 环境变量；模型能力差异不得写死进代码。

## 日志事件枚举（logs/YYYY-MM-DD.jsonl 的 dir 字段）

`boot` / `in` / `out` / `tool` / `llm` / `llm_err` / `err` / `send_err` / `poll_err` /
`confirm` / `progress` / `reasoning` / `recover` / `shift` / `task` / `deny`
（新增枚举须在本表登记；usage 结构见 llm.py，reasoning 文本截断 4000 字符且不回传 API。）

## 增长触发器（碰到即先还债/立 ADR）

- `daemon.py` 超 800 行 → 必拆（调度器已独立，下一个候选是确认门与班次执行）
- 第 7 种插件类型 → 必先立 ADR
- 新目录进确认门免确认清单 → 只改 `gate_rules.json`，不改代码
- 测试丢失或长期不跑 → 立即还债（tests/ 是可安全重构的前提）
- 引入任何第三方依赖 → 必先立 ADR（现状：零依赖是特性）

## 决策记录索引

见 `docs/adr/`（ADR-001 通道定盘 Telegram / ADR-002 插件管线 / ADR-003 确认门分级 /
ADR-004 自动化层退役与调度器内置 / ADR-005 单体不拆 / ADR-006 记忆自建不装服务）。
