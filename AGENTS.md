# Project X — 个人助手（自建轻量版）

自建个人 AI 助手：飞书通道 + agent 循环（tool-use）+ 记忆层 + 定时汇报。Python，先跑在 Mac 本地。

## 已定决策（2026-10-07 与用户敲定，勿轻易推翻）

- **通道**：飞书（个人免费版自建应用，国内直连，支持 webhook 与长连接）
- **技术栈**：Python
- **部署**：先 Mac 本地（launchd 常驻），后续可平移 VPS/NAS
- **LLM**：做成可切换——OpenAI 兼容接口 + 环境变量（候选：GLM 智谱 / DeepSeek / Claude）
- **源起**：用户嫌 OpenClaw 重 → 先用 ZCode 充当助手探索验证（2026-10-07）→ 决定固化为正式项目

## 蓝图

- **v0（当前待做）**：确定性脚本——早报/晚间简报（抓取 → 渲染 markdown → 写 `assistant/reports/`），launchd/cron 驱动，接管下述自动化
- **v1**：飞书 bot + agent 循环（读写文件 / 联网搜索 / 处理收件箱）+ markdown 记忆层
- **v2**：文档库检索、邮件入站、敏感文件留本地 + Tailscale 拓扑。参考项目：tinyhumansai/openhuman（118 个 OAuth 同步个人上下文）、rohitg00/agentmemory（agent 持久记忆）

## 目录约定

```
assistant/
├── TASKS.md    任务收件箱（一行一条；完成后移入"已完成"区）
├── reports/    早报 YYYY-MM-DD-早报.md；晚间简报 YYYY-MM-DD-晚间简报.md
└── docs/       个人文件库（含证件等敏感文件：仅在用户明确要求时读取，日常流程不扫描）
```

## 早报数据源（已验证可用）

- 中文要闻：blog.intelexe.cn 的"每天60秒读懂世界"——先抓索引页找当日 `/archives/xxxx` 链接（**按标题里的日期匹配**，站内最新可能不是当日 60s），再抓正文取 ~15 条
- GitHub Trending：https://github.com/trending（直连超时，脚本会自动走代理并重试）
- 热搜：微博官方接口 `weibo.com/ajax/side/hotSearch`（tophub 的微博榜节点已返回"无效的快照ID"，仅作备用）；科技动态：WebSearch（由自动化层补充）
- **规则**：任一源失败就跳过并在报告"数据源与备注"节注明，绝不中断

## 报告格式（现成样例见 assistant/reports/2026-10-07-早报.md）

- 早报五节：🗞️ 要闻速览（国内/国际/科技AI）/ 🐙 GitHub Trending（表格+点评）/ 🤖 AI 一句话 / 📥 收件箱 / 数据源与备注
- 晚间简报三节：🌙 白天动态 / 🐙 Trending 复盘（与早报对比，↑↓ 标注）/ 📥 收件箱巡检

## 环境注意

- git 全局代理 = 127.0.0.1:7892（SpeedCat VPN）；GitHub 直连会卡，VPN 客户端没开时 git 拉取会失败
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
