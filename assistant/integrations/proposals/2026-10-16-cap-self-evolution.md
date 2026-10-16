# 提案：cap-self-evolution — 自进化闭环 v1（经验固化 / 变更过门 / 进化日志）

- 提案日期：2026-10-16（RSI 调研产出，见 research/2026-10-16-RSI-自进化调研.md；本文件兼 PM 立卡）
- 状态：proposed（设计已过 PM 交付标准，等用户批准后实施）
- 来源：用户 2026-10-16 授权自进化线 + 三参照项目（GenericAgent / Raven / evolver）方法吸收，零外部安装

## 问题

助手的能力只从"外部发现"生长（早班 Trending → skills），不从"自身经验"生长：同类任务每次都重新摸索，10 月来做过三次 Trending 深读、多次报告增强，无一沉淀为可复用技能。同时，若开放自修改而无门禁，风险不可控（用户明确要求多参照系约束）。

## 目标与指标

- 主指标：非平凡任务完成后，可复用模式的固化率（每周 ≥2 条新 skill 来自经验，而非仅外部发现）
- 安全指标：自进化产生的任何变更 100% 过 tests + check_registry；高风险类（gate_rules/系统提示/工具）100% 用户确认后才生效
- 审计指标：每次自进化有 git commit + registry provenance 可追溯

## 取舍（明确不做）

- 不装 GenericAgent/Raven/evolver/CowAgent（对照与思想吸收；四铁律下零安装）
- 不做权重级 RSI（不碰模型本身，只进化提示/技能/策略/工具层）
- 首版不做自动 A/B 评估（Raven 式 propose→evaluate 的 evaluate 首版 = 测试套件 + PM 对照验收，不做并行对照实验）

## 方案

1. **经验固化**：任务线 DONE 后，daemon 增加一步轻量反思（同轮或夜间批处理）：读本次任务 trace，判断"可复用模式？"——是则按 agent-discipline + PM 标准写 skill 并登记 registry；判断标准：同类任务第二次出现、或单次 >5 轮工具的探索路径
2. **变更过门**：新增 gate_rules 策略类 `self-evolve`——写 skills/ 自动放行（宽口径已有），改系统提示/gate_rules/工具代码一律走确认门（永拦区不变）
3. **进化日志**：`docs/evolution.md` 一行一条（时间/触发任务/产物/参照系验证结果），git commit 随行
4. **对照基准**：CowAgent 能力清单存 research/，季度对照一次差距

## 风险与回滚

- 风险：反思步增加 token 成本（估 +15%/非平凡任务）；skill 质量漂移（以 PM 验收 + 周固化 review 兜底）
- 回滚：经验固化挂在调度器可独立关闭（state.json 开关）；产物全是 markdown/registry 行，revert 即回滚

## 时间窗

批准后 1 个班次日（约 4-6 小时）：固化反思 + 门禁分类 + 进化日志 + 测试 + 文档。

## 批准方式

TASKS.md 写 `批准 cap-self-evolution`，或直接说"冲"。
