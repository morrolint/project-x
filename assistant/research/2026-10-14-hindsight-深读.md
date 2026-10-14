# 深读档案 · vectorize-io/hindsight（Agent Memory That Learns）

> 调研日期：2026-10-14。月榜 #2（月增 +25.9k，49k★），Python，可自托管（docker/嵌入式/MCP 三形态）。
> 我们的关系：**设计吸收方**——第二批记忆升级的活教材；不安装其服务（自托管栈重：docker+向量库+reranker），
> 只把纯 stdlib 能承载的设计搬进 `agent/memory.py`。

## 七个设计点与我们的取舍

| hindsight 设计 | 是什么 | 我们的处置 |
|---|---|---|
| 四类记忆 | world facts（世界事实）/ experiences（亲历）/ observations（证据固化信念）/ mental models（常备理解） | ✅ 吸收前两类（facts.md + 月度日志），observations 需调度器放第二批后段 |
| retain 三步 | LLM 抽取事实/实体/时间 → 归一化 → 多表示索引 | ✂️ 我们由 daemon 的 LLM 在 memory_save 前自行组织一句话（现有做法已够轻场景） |
| recall 四路并行 | 语义向量 + **BM25** + 图谱 + 时间过滤 → RRF 融合 + rerank | ✅ 吸收 BM25 路（86% 实测得分的来源，agentmemory 基准背书）；其余三路上向量库时再说 |
| observations | 后台把相关事实固化为"信念"：带证据引文+证明计数，**求精不覆盖**（新证据强化/弱化旧信念而非静默替换） | 📌 第二批后段（需定时调度）；这是"记忆不再是流水账"的关键设计 |
| mental model / knowledge page | 对固定问题（"用户偏好是什么"）的常备答案页，读它是纯 DB 读零检索，**agent 开机即带着沉淀知识** | ✅ 立即吸收极简版：`memory/profile.md`，daemon 每轮注入系统提示（与 kwp 双层记忆的热缓存殊途同归） |
| banks | 严格隔离的记忆库 + **disposition traits**（怀疑度/字面度/共情度）影响 reflect 风格 | 📌 单用户暂不需要多 bank；disposition 与 personas/ 正交——将来 reflect 落地时打通 |
| Memory Defense | retain 时扫 45 种密钥/PII 模式，打码或拦截 | ✅ 立即吸收基础版：retain 前正则打码（token=xx / sk- / ghp_ 等），默认开 |

另两个顺带确认：多语言原生（张伟不转 Zhang Wei——我们的中文 bigram 分词天然满足）；benchmark 被 VT Sanghani Center 与华盛顿邮报独立复现（可信度高于自报）。

## 落地映射（memory.py v0.2，纯 stdlib）

1. 双层文件：`facts.md`（稳定事实/偏好）+ `YYYY-MM.md`（时序日志）——retain 按 kind 路由
2. BM25 评分召回（k1=1.5, b=0.75，中文 bigram + 拉丁词元）替代 v0.1 的词元重合
3. `profile.md` 常备页：daemon 每轮注入（零检索成本的世界观底座）
4. retain 前密钥打码（Memory Defense 基础版）

## 溯源

README Core Concepts 全节 + repo tree（5124 文件）抓取于 2026-10-14；benchmark 数据见其 README "Memory Performance & Accuracy"（VT 复现）。关联：`research/2026-10-09-知乎榜单五项目-评估.md`（agentmemory 的 BM25 实测背书）、kwp 抄作业清单（双层记忆）。
