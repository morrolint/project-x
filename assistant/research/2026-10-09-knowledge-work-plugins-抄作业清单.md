# 抄作业清单 · anthropics/knowledge-work-plugins

> 调研日期：2026-10-09（用户批准"两个动作都做"之②）。仓库：anthropics/knowledge-work-plugins（1037 文件，MIT），
> 结构：按职业分类的插件集（bio-research / customer-support / data / design / engineering / finance / legal / marketing /
> operations / productivity / sales …），每插件 = skills/（SKILL.md 方法）+ commands/ + 可选 dashboard.html。
> 与本项目相关的是 **productivity** 与 **operations** 两类，其余职业类明确不抄。
> 阅读顺序建议：本清单 → 想深抄某条时再抓对应 SKILL.md 原文（路径在每条末尾）。

## 一、已决定抄的（对应到我们项目）

### 1. 双层记忆（productivity/skills/memory-management）→ v1 记忆层第二批的升级蓝图 ⭐ 最有价值

- **架构**：热缓存（~100 行，Top 30 人物 / 30 缩写 / 活跃项目 / 偏好，覆盖 90% 日常解码）+ 冷库（`memory/` 全量：glossary.md 解码环、people/ 人档、projects/ 项目档、context/ 环境）。
- **核心机制**：查_lookup 三级（热缓存 → 冷库 → 问用户"这是什么，我记下来"）；**晋升/降级**（高频条目升入热缓存，过时条目降回冷库，热缓存常新）；昵称/代号必须收录（"todd/PSR/oracle" 这类 shorthand 能被解码才算懂用户）。
- **映射到我们**：我们的 `assistant/memory/` 目前只有按月流水 + 词元召回（last30days 思路）；AGENTS.md 事实上充当热缓存（自动加载）。第二批记忆升级照此改造：加 `memory/glossary.md`（用户的缩写/习惯用语解码环）+ 偏好区 + 晋升降级规则；daemon 的 `_new_conversation` 已有召回注入，补"查不到就问用户并 memory_save"闭环。
- 深抄路径：`productivity/skills/memory-management/SKILL.md`

### 2. 收件箱四区制（productivity/skills/task-management）→ TASKS.md 演进方向

- **模板**：Active / Waiting On / Someday / Done 四区；任务行 `- [ ] **标题** - 背景, for 谁, due 日期`；完成用 `[x] ~~删除线~~ (日期)`；Waiting On 记 `since [日期]`（等了多久一目了然）；Done 保留约一周后清理。
- **映射到我们**：我们的收件箱是 待办/已完成 两区，**最缺 Waiting On**——三条待批提案正是"等用户"状态，散在 HANDOFF/registry 里；Someday 对应"想法但不到排期"。第二批收件箱升级：加两区，registry 的 proposed 条目在 Waiting On 放一行指针。
- 深抄路径：`productivity/skills/task-management/SKILL.md`

### 3. 状态报告模板（operations/skills/status-report）→ 早报/晚间简报的呈现参考

- **骨架**：执行摘要（3-4 句）→ 总体 🟢🟡🔴 → KPI 表（目标/实际/趋势/状态）→ 本期成果 → 风险表（影响/缓解/负责人）→ **决策需表**（背景/期限/建议动作）→ 下期优先级。
- **映射到我们**：早报已有"数据源与备注"（≈诚实度披露），可抄的是**"等你拍板"小节**——把待批提案/待确认事项做成"背景+期限+我的建议"表，把"汇报"升级成"催办"；执行摘要三句话原则契合"结论先行"。
- 深抄路径：`operations/skills/status-report/SKILL.md`

### 4. 首启引导（productivity/skills/start）→ daemon 首次对话流程

- **方法**：从用户现有任务列表里**学语言**——逐条识别昵称/缩写/代号，交互式问清再入库（"真实任务 = 真实 shorthand"）；数据源按置信度分组呈现（可直接入库 / 需澄清 / 低频存疑）。
- **映射到我们**：daemon 上线后首次对话可走此流程建立 glossary；开源时先读 TASKS.md 与近期报告提候选，问用户确认。
- 深抄路径：`productivity/skills/start/SKILL.md`

## 二、记一笔但暂不动

- **dashboard.html**：TASKS.md 的本地可视化看板（读写同一文件、拖拽排序）。要写代码，属于 capability 级提案——若以后觉得收件箱该有 UI，先想起它已有参考实现。
- **插件分发格式**（.claude-plugin/marketplace.json + commands/ + hooks/）：Agent Skills 生态的标准打包。我们 skills/ 走"纯方法 markdown"契约，暂不兼容该格式；若将来要跨宿主分发再对齐。
- **cowork-plugin-management / enterprise-search 等**：面向多用户组织场景，个人助手用不上。

## 三、为什么不抄什么

- 职业垂直类（bio-research/sales/legal/finance…）：领域不对口，且其技能依赖 MCP 连接器（Slack/邮件/日历），我们 v1 尚无这些入站通道。
- 它的记忆/task 体系依赖 `${CLAUDE_PLUGIN_ROOT}` 与 dashboard：我们只抄**结构与机制**（分层/晋升/四区/模板），不抄宿主绑定。

## 溯源

根 README.md、productivity 全部 4 个 SKILL.md、operations/status-report SKILL.md 抓取于 2026-10-09（raw.githubusercontent.com 直连）。
