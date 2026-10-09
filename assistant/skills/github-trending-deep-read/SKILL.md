---
name: github-trending-deep-read
description: 早报生成后，把 GitHub Trending 节从"项目名列表"升级为逐项目解读（是什么/有什么用/与我们是否相关）
---

## 方法

1. **以脚本生成的表格为准**（数据已抓好，勿重抓榜单；星数以表格当日值为准）。
2. 对每个项目抓 README：`curl -sSL -x http://127.0.0.1:7892 https://raw.githubusercontent.com/<owner>/<repo>/HEAD/README.md`。前 5 名逐个通读；6-10 名读首屏（前 60 行）即可。
3. 每个项目写一段（Markdown，格式对齐 assistant/reports/2026-10-09-早报.md）：
   `**N. [项目名](链接) [⭐] — 一句话定位（+星数/日，总星★）**` + 两三句中文讲清"这是什么、有什么用"。
4. **相关性判断标准**（满足其一即标 ⭐ 并加一行 `**与我们**：……`）：
   - 能直接挂载到助手（MCP 工具、agent 技能包、可复用的自动化模式）；
   - 与 v1 蓝图（飞书 bot / agent 循环 / 记忆层）或 v2（文档检索/通道）直接相关；
   - 能改进现有流程（报告生成、收件箱处理、推送）。
5. 全部写完后用 Edit **整体替换**脚本的表格与"点评（脚本版）"段；节标题改为"GitHub Trending 今日 Top 10（逐项目解读）"，开头保留一行抓取时点说明。
6. **接入流程（必做）**：对每个 ⭐ 项目查 `assistant/integrations/registry.json`：
   - 未收录 → 评估接入方式：纯方法/知识类 → 直接写成 `assistant/skills/<name>/SKILL.md` 并在 registry 加 `skill` 条目（status: active，provenance 注明来源仓库与日期）；需要装代码/服务/凭据 → 写 `assistant/integrations/proposals/YYYY-MM-DD-<id>.md` 提案（registry 状态 proposed），**不得私自安装**；
   - 已收录 → 视情况更新条目备注。
7. 有价值的项目结论同时反哺早报"与我们"一行——提案路径告知用户（报告收件箱节或汇报里提一句）。

## 注意

- README 抓不到（404/空）时凭仓库描述写一句话定位，不编造细节。
- 与我们无关的项目也保留条目（一两句即可），保证榜单完整性。
- 时间敏感：标注"榜单抓取于今日 HH:MM"。

## 来源

用户 2026-10-09 要求："把项目名列出来有什么用？我想要的是：里面到底是干嘛的？有什么作用？对个人助手有什么提升？"据此把点评方法固化为技能。
