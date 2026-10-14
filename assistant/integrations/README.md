# 集成子系统 · 契约与接入规范

> 目的：外部项目/工具接入本助手，**只走标准管线**——注册表声明、类型化契约、生命周期管理。
> 禁止"来一个加一个"式地在脚本里打补丁。本文件是接入的唯一规范。

## 四条铁律

1. **注册表是唯一事实来源**：任何集成本（无论多小）必须在 `registry.json` 有条目（id / type / status / provenance / added）。没有条目的集成视为不存在。
2. **report.py 不认识任何具体数据源与推送通道**：它只知道"插件契约"。新增数据源 = 在 `sources/` 放一个插件文件 + registry 加一行；新增推送通道 = 在 `channels/` 放一个插件文件 + registry 加一行；report.py **零改动**。
3. **自动化不得私自安装代码**：从榜单/调研中发现的项目，纯方法/知识类可直接固化为 `../skills/` 下的 markdown 技能（不含可执行代码）；需要 pip/npm 安装、跑服务、配凭据的，一律写 `proposals/` 提案等用户批准。
4. **失效要退役，不留死代码**：源长期失效 → 插件标 `retired`（registry 备注），插件文件移除；不满足于"跳过并备注"的僵尸集成。

## 集成类型（type）与契约

| type | 载体 | 契约 | 现状 |
|---|---|---|---|
| `report-source` | `sources/*.py` 插件 | 见下节 | ✅ 已运行（3 个源） |
| `push-channel` | `channels/*.py` 插件 | `ID` + `NAME` + `push(text) -> (ok, err)`，失败不阻断；凭据走环境变量 | ✅ Telegram |
| `skill` | `../skills/<name>/SKILL.md` | 纯方法文档：frontmatter(name/description) + 步骤；**不含可执行代码** | ✅ 3 个技能已上线 |
| `capability` | 外部工具/服务（如 Agent-Reach、PageIndex） | 必须经提案批准后安装，安装方式与回滚步骤写进提案 | 📋 若干提案中 |
| `channel-inbound` | `../agent/channels/*.py` 插件，daemon 按 `AGENT_CHANNEL` 选择 | 见下节 | 🚧 Telegram 开发中 |
| `ui-kit` | `../web/kit/`（设计令牌+HUD 组件+动效脚本+SVG 资产，零依赖无构建） | 页面引用；改主色只动 `:root` 令牌 | ✅ 巨构套件 |
| `persona` | `../agent/personas/*.md` | frontmatter(name/vibe) + 身份/铁律/交付标准；daemon 按任务匹配注入或 `AGENT_PERSONA` 强制 | ✅ PM 首个人设 |
| `memory` | `../agent/memory.py` | `retain / recall` 已实现（reflect 属第二批）；markdown 按月归档 + 词元召回 | ✅ v0.1（随 v1 daemon 上线） |

## report-source 插件契约

文件放在 `sources/`，不以 `_` 开头即被自动发现。必须暴露：

```python
ID = "github-trending"        # 与 registry 条目 id 一致
NAME = "GitHub Trending"      # 人读名（日志/报告用）
KINDS = ("morning", "evening")  # 该源服务哪些报告；不在 KINDS 的班次不调用

def fetch(target_date):
    """返回 (数据|None, 备注文本)。约定：
    - 任何网络/解析失败都返回 (None, "失败原因")，绝不抛异常、绝不中断报告；
    - 直连失败自动走代理并重试（用 _common.http_get）；
    - 数据结构自由，但必须可被 JSON 序列化（会进 reports/*.trending.json sidecar）。"""
```

`_common.py` 提供共享设施：`http_get`（curl 子进程，直连→代理→重试）、UA、代理配置（环境变量 `ASSISTANT_PROXY=off` 可禁用）。

**已知边界**：新数据源若要进报告的"新内容槽位"，需同步扩展 report.py 渲染函数——属架构变更，先立 ADR（见 docs/adr/ 与 assistant/ARCHITECTURE.md 的增长触发器）。

## push-channel 插件契约

文件放 `channels/`，不以 `_` 开头即被 report.py 动态发现。必须暴露：

```python
ID = "push-telegram"     # 与 registry 条目 id 一致
NAME = "Telegram"        # 人读名（日志/报告备注用）

def push(text):
    """推一段文本。返回 (ok, err)；任何失败返回 (False, 原因)，
    绝不抛异常、绝不中断报告。凭据从环境变量读（report.py 已加载 .secrets.env）。"""
```

## channel-inbound 插件契约（agent 侧）

文件放 `../agent/channels/`，daemon 按 `AGENT_CHANNEL`（默认 telegram）加载。必须暴露：

```python
ID = "telegram"

def create():
    """从环境变量构建通道实例。返回 (client|None, err)。
    client 需实现：poll() -> (updates, err) / send(text, reply_to=None) / chat_id 属性。"""
```

新增通道（如飞书）= 放插件 + registry 加一行 + 设 `AGENT_CHANNEL`，daemon 零改动。
daemon 对 updates 的消费约定：只处理 `message.text`，非白名单 chat 记日志不响应。

## registry 校验器（四铁律的机制化）

改过 registry.json 或增删插件文件后必跑：`python3 assistant/integrations/check_registry.py`
（自动化收件箱巡检动 registry 前后各跑一次）。检查：id 唯一、type/status 枚举、
impl 文件存在且 source/channel 插件的 ID 常量与 registry id 双向对账、active 必有 impl、
skill 契约抽查。退出码 0/1，可接自动化。

## skill 契约

`../skills/<name>/SKILL.md`：

```markdown
---
name: <kebab-case 名>
description: 一句话说明何时用
---
## 方法
（步骤化、可复述；自动化会话按此执行）
## 来源
（若提炼自某个外部项目：仓库名 + 抓取日期）
```

技能只写方法，不写代码。需要代码的 → `capability` 提案。

## 生命周期

```
proposed（提案/发现） → evaluating（调研中，提案附调研结论）
  → active（已接入，registry 有实现指针）
  → retired（失效/替代；registry 保留一行备注，实现移除）
```

- 提案文件：`proposals/YYYY-MM-DD-<id>.md`，必须包含：是什么 / 对本项目的价值 / 接入路径（装什么、改什么）/ 风险与回滚 / 凭据需求。
- 用户批准方式：在 TASKS.md 待办写一行 `批准 <id>`；自动化收件箱巡检时执行安装并在 registry 转 active。
- 拒绝方式：删提案文件，registry 条目标 `rejected`（留档，避免同一项目反复被提）。
