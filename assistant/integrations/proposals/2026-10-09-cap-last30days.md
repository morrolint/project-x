# 提案：cap-last30days — 跨平台"近 30 天"调研引擎

- 提案日期：2026-10-09
- 仓库：[mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill)（MIT；GitHub Trending 单日 #1）
- 状态：proposed（README 级调研完成；**未安装任何代码**）
- 来源：用户 2026-10-09 推荐阅读其 README.zh-CN.md

## 是什么

面向 agent 宿主的调研技能 + 引擎：给定主题（人物/公司/产品/技术/"X vs Y"），
并行搜索约 18 个平台（Reddit、X、YouTube、HN、Polymarket、GitHub、arXiv、Techmeme……），
按**真实互动**（赞同票/点赞/Polymarket 成交量概率）而非编辑或 SEO 排序，
跨平台聚类同一事件，产出带引用的简报。亮点：

- discovery 模式：不指定主题也能发现"正在爆发的话题"，按增长排序，附可追问的后续命令；
- `--emit=json` 版本化数据契约（agent 可编程消费）；watchlist/briefing 定时脚本；
- `--store` SQLite 跨运行积累、资料库全文检索（离线确定性行为，与本项目 BM25 起步思路同调）；
- 2700+ 测试、52 位社区贡献者、15 个版本持续维护——抓取源易碎但上游修得快。

## 对本项目的价值

1. **早报"科技动态"的升级候选**：现在靠 ZCode 早班 WebSearch 补几条；last30days 的
   互动评分 + 发现模式回答的是"真实用户此刻在讨论什么"，且 briefing 脚本与两班倒报告天然同构。
2. **v1 daemon 的深度调研工具**：JSON 契约现成，可挂成 `research(topic)` 工具（走 127.0.0.1:7892）。
3. **纯方法层可零成本先行**：多源并行 → 互动评分 → 故事聚类的编排方法论，可提炼为
   本项目 skill 指导早班增强——不装任何东西。

## 接入路径（批准后执行）

- **第一步（零安装）**：抓取其 `skills/last30days/SKILL.md`，提炼方法论为
  `assistant/skills/cross-platform-fresh-research/SKILL.md`，registry 加 skill 条目。
- **第二步（装引擎，可选）**：uv 配 Python 3.12（**系统 3.9 不满足，全项目唯一的运行时偏离**）
  → 克隆或 `npx skills add` → `--preflight` 预检 → 三个主题试研。
  验收标准：简报质量 ≥ 早班 WebSearch 产出，且全程仅用免费档来源。
- registry：按实际走的深度转 active（装引擎）或补 skill 条目（只走方法层）。

## 风险与回滚

- **重**：带 Node 依赖与浏览器 cookie 方案的引擎，偏离"纯标准库 + 系统 Python"的轻量底线。
- **易碎**：平台抓取源频繁失效（其更新日志一半在修源）；上游活跃是缓冲，但断网更新会衰减。
- **与 cap-agent-reach 定位重叠**：同为"早报新源"候选，建议评估期二选一先试。
- 回滚：删安装目录 + PATH 清理，无系统级改动；第一步的方法层 skill 独立存在、不受回滚影响。

## 凭据需求

- **v0 只用免费档（零密钥）**：Reddit（含评论）、HN、Polymarket、GitHub、StockTwits、arXiv、Techmeme。
- 可选不加：YouTube 走 yt-dlp（免费）；X 用浏览器 cookie 或付费密钥；
  TikTok/Instagram/LinkedIn 等 9 个源要 ScrapeCreators 密钥（前 1 万次免费）。
- 若批准安装，任何密钥存 `assistant/.secrets.env`（git 忽略），不入仓库。

## 批准方式

在 `assistant/TASKS.md` 待办写一行：`批准 cap-last30days`（全量）或
`批准 cap-last30days 第一步`（只做零安装的方法层提炼）。下次收件箱巡检执行。
