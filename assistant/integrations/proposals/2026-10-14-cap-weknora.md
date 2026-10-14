# 提案：cap-weknora — 腾讯开源知识库平台（v2 文档检索候选）

- 提案日期：2026-10-14（来源：GitHub 月榜 #10 探索扫描，用户授权"能用的就用"后调研）
- 仓库：[Tencent/WeKnora](https://github.com/Tencent/WeKnora)（33.9k★，月增 +11.2k）
- 状态：proposed（README 级调研完成；**未安装**）
- 与 `cap-pageindex` 的关系：**并案二选一**，见对比节

## 是什么

腾讯开源（微信团队）的本地知识库平台，三合一能力：

1. **RAG**：混合检索（向量+关键词）、多模态文档解析、**带引用的可验证答案**
2. **Agent**：知识+工具执行任务（多步推理/技能/沙箱/本地浏览器/MCP/记忆）
3. **Wiki**：文档自动组织成 wiki + 知识图谱 + 回滚

部署形态：Docker Compose 一键起（Web UI + 后端 8080 + 可选 Langfuse 追踪），**LLM/向量库/存储全部可插拔**，支持本地 Ollama 模型，数据完全留在自己环境——官方定位就是"local or private cloud"。

## 对本项目的价值

命中 v2 蓝图的核心诉求"文档库检索"：
- **国内直连**：腾讯系，拉镜像/文档无墙（PageIndex 的最大顾虑直接消解）
- **中文原生**：微信团队出品，中文解析/检索质量有基本盘
- 带引用答案 + 知识图谱，与我们诚实度规则同构

## 与 cap-pageindex 对比（批准前请先拍这一条）

| 维度 | WeKnora | PageIndex |
|---|---|---|
| 网络 | 腾讯系，国内直连 | 境外仓库，需代理 |
| 架构 | Docker 全家桶（平台级：UI+API+追踪） | 轻库（vectorless 树索引，嵌入应用） |
| 与我们的契合 | 平台旁路：daemon 经 API 调用其 RAG | 库内嵌：直接进 daemon 工具链 |
| 重量 | 重（compose 多容器，2C4G 服务器可跑但挤） | 轻 |
| 隐私红线 | 自托管数据不出域 ✓；**docs/ 默认排除必须写进接入配置** | 同样要求 |

**建议**：若 v2 走"2C4G 服务器 + 独立知识服务"形态 → WeKnora；若想保持 daemon 单进程极简 → PageIndex。可先批 WeKnora 在服务器试装（它本身就是服务形态），daemon 侧只需一个 query 工具对接其 API。

## 接入路径（批准后执行，在服务器或本机）

Docker Compose 起 WeKnora → 接 Ollama 或智谱 API 作 LLM → 建 `assistant-docs` 库（**排除 docs/ 敏感文件**，只进 reports/research/skills）→ daemon 加 `knowledge_query` 工具调其 8080 API。

## 风险与回滚

- Docker 多容器占用资源（2C4G 上与其他服务并存需评估；本机 mini 16GB 无压力）
- 回滚：`docker compose down` + 删镜像，零残留

## 凭据需求

无外部凭据（本地部署）；若接智谱 API 则复用现有 LLM_API_KEY。

## 批准方式

TASKS.md 写 `批准 cap-weknora 试装`（服务器/本机二选一注明）。
