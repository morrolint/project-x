# v1 常驻 Agent（Telegram 入站）

ZCode 之后的自建 agent 运行时：一个 launchd 托管的常驻 Python 进程，Telegram
长轮询收消息 → tool-use 循环 → 回复。纯标准库，兼容系统 Python 3.9，
全部 HTTP 走 curl 子进程（LibreSSL 与本地代理的 TLS 兼容问题，见 AGENTS.md）。

```
daemon.py        入口：轮询主循环、通道插件发现、确认门（分级）、任务线进度、内置调度器（08:00/21:00 班次接管）、--check / --once / --shift
tasks.py         任务线：五态状态机（RUNNING/WAITING_USER/DONE/FAILED/CANCELED），tasks/<id>.json 唯一事实源，重启恢复（治挂起丢失/重复投递）
channels/        入站通道插件（telegram.py；飞书=新增插件+registry 行+AGENT_CHANNEL 切换）
personas/        人设库（pm.md 产品经理；AGENT_PERSONA=pm 强制切换，或模型按任务自选）
llm.py           OpenAI 兼容 /chat/completions（GLM/DeepSeek/Claude 环境变量切换）
tools.py         工具集 ×10：收件箱 ×3 / 报告 / Trending 榜 / 读写列目录 / 记忆 ×2（写文件需确认）
memory.py        markdown 记忆（按月归档 + 词元召回；第二批换 BM25）
_http.py         curl 子进程 HTTP（auto/on/off 三种代理模式）
```

## 配置（assistant/.secrets.env）

| 键 | 必填 | 说明 |
|---|---|---|
| TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID | ✅（已有） | telegram 通道插件读取；只响应 CHAT_ID 本人 |
| AGENT_CHANNEL | 缺省 `telegram` | 选择 channels/ 下的入站通道插件 |
| LLM_API_KEY | ✅ | OpenAI 兼容接口的 key |
| LLM_BASE_URL | 缺省智谱 `https://open.bigmodel.cn/api/paas/v4` | |
| LLM_MODEL | 缺省 `glm-5.3-flash` | |
| LLM_WEB_SEARCH | 缺省 auto（智谱端点自动开官方 web_search 工具） | |
| LLM_PROXY | 缺省关；走 Claude 等需代理的端点设 `on` | |
| ASSISTANT_PROXY | 已有 | 设 `off` 全局禁代理（Telegram 会不可用） |

## 跑起来

```bash
python3 assistant/agent/daemon.py --check          # 自检（无网络请求）
python3 assistant/agent/daemon.py                  # 前台调试
python3 assistant/agent/daemon.py --once "在吗"    # 单条消息调试
# 常驻：见 com.project-x.agent.plist 头部注释（sed 替换 __REPO_ROOT__ 后 launchctl load）
```

## 安全边界

- 只处理 `TELEGRAM_CHAT_ID` 的消息，其他人给 bot 发消息只记日志不响应。
- 一切文件读写限 `assistant/` 内；`docs/`（敏感文件库）与 `.secrets.env`/`*.pem` 永拒。
- `write_file` 是确认门工具：LLM 发起后 daemon 把预览发给你，回复「确认」才执行，
  回复其他内容则取消并按新指令处理（NeedsConfirmation，HANDOFF §六）。
- 确认门分级：`reports/` 等机器产物区写操作免确认；班次轮次宽口径（skills/proposals/registry）；`docs/` 与密钥**任何口径都拦**。用户对话历史在内存；确认挂起经任务线落盘，重启可恢复。

## 与既有资产的关系

- 收件箱协议与 `scripts/report.py#read_inbox` 一致：ZCode 两班倒自动化照常处理
  TASKS.md，daemon 与它是**并存的两个入口**；daemon 稳定后再讨论是否接管 8/21 定时任务。
- 集成纪律不变：新工具加进 `tools.py` 属于架构内扩展；接第三方工具/服务仍走
  `integrations/proposals/` 提案。
- 日志 `logs/YYYY-MM-DD.jsonl` 已记录 LLM usage 与思考过程（reasoning 单列事件，不回传 API），第二批做成本记账与回放（HANDOFF §六）。

## 第二批（按 HANDOFF §六，未做）

多轮长记忆压缩、BM25/隐私过滤的记忆升级、日志回放 + 成本记账、邮件入站、飞书通道。
