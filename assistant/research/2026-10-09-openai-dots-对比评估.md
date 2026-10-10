# OpenAI Dots 对比评估（2026-10-09）

> 背景：用户问"codex 出了个 dot，跟我们新做的助手有啥区别"。Dots 是 OpenAI 2026-09-29 DevDay 发布、
> 10-07 详述的常驻主动 agent（ChatGPT 内，GPT-6 Astra 驱动，每 dot 一台云 VM）。
> 官方页：openai.com/index/introducing-dots。

## 一句话定位

Dots = **住进 OpenAI 生态的常驻分身**（云 VM + 4000 插件 + frontier 模型）；我们的 agent = **住进自己 Mac 的常驻分身**
（本机数据 + 自选通道 + 可切换 LLM + 840 行全透明）。能力天花板他们高；数据主权、通道自主、成本、可定制是我们赢——
这四点正是本项目的立项理由。

## 维度对比

| 维度 | OpenAI Dots | 我们（v1 daemon） |
|---|---|---|
| 运行位置 | OpenAI 云 VM + 云浏览器 | 自己的 Mac mini（launchd） |
| 数据主权 | 内容在 OpenAI（可控制是否训练，但数据在他们那） | 全部本地（registry/skills/记忆/日志），docs/ 物理隔离 |
| 入站通道 | ChatGPT/Slack/Teams（texting 即将），**不可自接** | Telegram（自选）+ channels/ 插件化可扩展 |
| LLM | GPT-6 Astra（frontier，代差承认） | GLM-5.3-flash 起步，环境变量随时换（含未来的更强模型） |
| 工具生态 | 4000+ 官方插件 + 云浏览器 | 自建 8 工具；MCP 第二批 |
| 主动性 | **proactive research**（后台只读扫描、主动汇报） | 响应式 + 外部 cron 两班倒（daemon 未接管定时） |
| 治理 | auto-review + Custom Rules（允许/需批准/禁止）+ 敏感操作必须人工 | 确认门 + 路径守卫 + chat 白名单（**设计哲学撞车，方向互证**） |
| 成本 | Pro / Business Premium 订阅（首个 dot 含在内，深度工作有额度） | coding plan，今日实测 11 万 tokens ≈ 0 |
| 可定制 | 黑盒：规则是他们的 Custom Rules，prompt/记忆不可见 | 840 行全读过，想改哪行改哪行 |

## 值得抄的三点（记入第二批候选）

1. **proactive research**：无任务时用只读工具在后台找有用的事、主动汇报——给 daemon 加"闲时只读扫描"模式
   （约束：只读工具白名单，与他们的做法一致）。
2. **Activity View**：后台工作进度可视化——我们的 JSONL 日志已是数据层，缺一个 `activity` 视图命令/报告。
3. **Custom Rules 分级**：确认门从"工具级二元（确认/不确认）"升级为"规则级（允许/需批准/禁止）"，
   例如 read_file 默认放行、write_file 限 reports/ 内免确认。

## 什么时候该用 dots 而不是我们

如果你长期活在境外 SaaS 生态、不介意数据上云、要 4000 插件的开箱即用——dots 大概率更省心。
但本项目的核心诉求（本机敏感文件、Telegram 自选通道、国内直连 GLM、极度定制、零订阅成本）
恰好全落在 dots 不覆盖的象限里。两者不是替代关系：dots 教设计，我们做自己。
