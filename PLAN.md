# 邮件处理 Agent — 实现计划

**目标**：构建一个能收取邮件、理解意图、安全执行动作（回复/归档/删除）的 LangGraph Agent。

---

## 技术栈

**核心**
- Runtime: Python 3.11+
- Agent: LangGraph
- LLM: GPT-4o（决策）+ GPT-4o-mini（分类）+ 语义缓存（GPTCache）

**邮件层**
- 收取: IMAP（QQ 邮箱，imap.qq.com:993，SSL/TLS，支持 IMAP IDLE 实时推送）
- 发送: SMTP（QQ 邮箱，smtp.qq.com:587，STARTTLS；授权码认证）
- 解析: `email` + `beautifulsoup4`
- 附件: `pdfplumber`、`python-docx`、`pytesseract`
- 安全扫描: ClamAV 或 VirusTotal API

**存储层**
- 关系数据库: PostgreSQL + SQLAlchemy
- 向量数据库: ChromaDB
- 任务队列: Celery + Redis

**工程**
- 配置: `pydantic-settings` + `.env`
- 容器: Docker + Docker Compose
- 观测: LangSmith + Prometheus + Grafana
- 测试/评估: `promptfoo` 或 LangSmith Evaluation

---

## 项目目录结构

```
email_agent/
├── ingestion/            # Phase 1：邮件接入与预处理
│   ├── imap_client.py    # IMAP IDLE 监听 + SMTP 发送（QQ 邮箱）
│   ├── parser.py         # 邮件解析（正文/附件/PII脱敏）
│   ├── scanner.py        # ClamAV/VirusTotal 附件扫描
│   └── dedup.py          # 去重与状态机
├── graph/                # Phase 2：LangGraph 状态机
│   ├── nodes/            # 各节点实现（injection, classify, risk, confirm, execute）
│   ├── state.py          # GraphState 定义
│   └── builder.py        # 图构建与编译
├── tools/                # Phase 3：Tool 定义
│   ├── email_tools.py    # reply / forward / label / delete
│   └── calendar_tools.py # create_calendar_event / create_task
├── memory/               # Phase 4：记忆模块
│   ├── short_term.py     # 线程上下文管理
│   ├── long_term.py      # ChromaDB 向量存储
│   └── preferences.py    # 用户偏好管理
├── models/               # 数据库 Schema
│   ├── email.py          # emails 表
│   ├── audit.py          # audit_log 表
│   └── preference.py     # user_preferences 表
├── api/                  # 人工确认 Webhook 接口
│   └── confirm.py
├── config.py             # pydantic-settings 配置
└── tests/                # Phase 5：测试与 Golden Dataset
    ├── golden_dataset/
    ├── mocks/
    └── e2e/
```

---

## 数据库 Schema

### `emails` 表
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | — |
| `message_id` | VARCHAR UNIQUE | 邮件 Message-ID（RFC 2822），用于去重 |
| `thread_id` | VARCHAR | 邮件线程 ID（`In-Reply-To` / `References` 头推导）|
| `sender` | VARCHAR | 发件人（存储前 PII 脱敏） |
| `subject` | VARCHAR | 主题 |
| `received_at` | TIMESTAMP | 接收时间 |
| `status` | ENUM | `pending / in_progress / done / failed` |
| `idempotency_key` | VARCHAR | 操作幂等键 |
| `updated_at` | TIMESTAMP | 最后更新时间 |

### `audit_log` 表（不可覆盖，仅 INSERT）
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | — |
| `email_id` | UUID FK | 关联邮件 |
| `action` | VARCHAR | 执行的动作（`move_to_trash` / `permanently_delete` 等）|
| `reason` | TEXT | LLM 输出的原因 |
| `llm_trace` | JSONB | 完整 LLM 推理链 |
| `operator` | VARCHAR | `agent` 或人工操作者 ID |
| `confirmed_by` | VARCHAR | 人工确认者（高风险操作必填）|
| `created_at` | TIMESTAMP | 不可修改 |

### `user_preferences` 表
| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID PK | — |
| `rule_type` | VARCHAR | 偏好类型（如 `auto_label`、`block_sender`）|
| `rule_value` | JSONB | 规则内容 |
| `source` | ENUM | `manual_override` / `explicit_config` |
| `created_at` | TIMESTAMP | — |

---

## QQ 邮箱接入架构

QQ 邮箱使用 IMAP IDLE 实现近实时收信，完整链路如下：

```
QQ 邮箱（imap.qq.com:993）
    ↓ IMAP IDLE 长连接，服务端推送新邮件通知
IMAPClient（aioimaplib）
    ↓ 收到 EXISTS 通知后 FETCH 邮件
Celery Task Queue（Redis）
    ↓
LangGraph Agent 处理
```

**前置配置步骤（Phase 1 实现前必须完成）**：
1. 登录 QQ 邮箱 → 设置 → 账户，开启 **IMAP/SMTP 服务**
2. 生成**授权码**（非 QQ 密码），作为 IMAP/SMTP 认证凭据，存入 `.env`（本地）或 Secret Manager（生产）
3. 确认 IMAP 服务器：`imap.qq.com:993`（SSL），SMTP：`smtp.qq.com:587`（STARTTLS）
4. 本地开发：IMAP IDLE 可直接对真实邮箱测试，或使用 `imaplib` 录制/回放模式

**注意**：QQ 邮箱对单 IP 每日收发有频率限制，大批量操作需增加退避策略。

---

## Phase 1 — 邮件接入与预处理

**目标**：能稳定收取、解析、去重邮件，为 Agent 提供干净的输入。

| # | 任务 | 关键点 |
|---|------|--------|
| 1.1 | QQ 邮箱 IMAP IDLE 连接管理 | `aioimaplib` 建立 SSL 长连接，监听 `EXISTS` 事件；连接断开自动重连（指数退避）；SMTP 发送用 `aiosmtplib` |
| 1.2 | 邮件解析器 | 提取 `From/To/Subject/Body`，HTML → 纯文本 |
| 1.3 | 附件处理 | PDF/Word 提取文本，图片 OCR；**单附件大小上限 10MB，超限拒绝处理**；**所有附件先经 ClamAV 扫描，命中则隔离** |
| 1.4 | 去重 & 状态机 | 数据库记录 `Message-ID` + 状态字段（`pending / in_progress / done / failed`） |
| 1.5 | Prompt Injection 预处理 | 邮件正文统一用 `<email_content>` XML 标签包裹，与指令角色隔离 |

**验收**：读取真实 QQ 邮件解析正确；恶意附件被拦截；重启后不重复消费；IMAP 连接断开后自动重连。

---

## Phase 2 — LangGraph 状态机

**目标**：构建核心决策图，覆盖所有意图分类和风险控制。

**节点设计**（顺序执行，有分支）：

```
[解析节点]
    ↓
[Prompt Injection 检测节点]  →  命中 → [告警/拒绝，记录日志]
    ↓ 通过
[意图分类节点]  (GPT-4o-mini)
    ↓ 输出意图列表（支持多意图）
[LLM 输出校验节点]  →  校验失败重试（最多3次）→ 仍失败 → [转人工处理队列]
    ↓ 通过
[多意图拆分节点]  →  拆分为有序意图列表，串行执行
    ↓
[风险分级节点]  →  取列表中最高风险等级作为整体等级
    ├── 低风险（打标签、归档）      → [直接执行节点]
    ├── 中风险（回复、转发）        → [预览节点] → 5秒可撤销 → [执行节点]
    └── 高风险（删除、批量操作）    → [人工确认节点] → 确认→[执行节点]
                                                     拒绝→[终止，记录日志]
                                                     超时→[默认拒绝，记录日志]
[LLM 不可用降级节点]  →  指数退避重试3次 → 失败放回队列 → 降级 GPT-4o-mini 重试
```

| # | 任务 | 关键点 |
|---|------|--------|
| 2.1 | Prompt Injection 检测节点 | 正文关键词匹配（`ignore previous`、`forward all` 等），命中即拒绝，不进入意图节点 |
| 2.2 | 意图分类节点 | GPT-4o-mini；输出结构化 JSON，包含 `intents[]`、`entities`、`reason` |
| 2.3 | LLM 输出校验节点 | Pydantic 模型强校验 LLM 输出；校验失败最多重试 3 次，用 `with_structured_output`；仍失败转人工处理队列 |
| 2.4 | 多意图拆分节点 | 将 `intents[]` 拆分为有序执行列表；任一意图为高风险则整体升为高风险 |
| 2.5 | 风险分级节点 | 按上表映射；删除/批量操作强制归为高风险 |
| 2.6 | 人工确认节点 | Webhook/UI 暴露审核接口；**超时未响应默认拒绝** |
| 2.7 | 执行节点（幂等）| 操作前写 `in_progress`，成功后写 `done`，异常回滚 `pending` |
| 2.8 | LLM 降级策略 | GPT-4o 调用失败时指数退避重试 3 次（1s/2s/4s）；仍失败降级至 GPT-4o-mini 重试一次；最终失败放回 Celery 队列 |

**验收**：Injection 样本被拦截；多意图邮件正确拆分串行执行；LLM 输出格式非法时触发重试而非崩溃；删除意图必须经人工确认；崩溃重启不重复发送。

---

## Phase 3 — Tools 定义

**目标**：每个可执行动作封装为独立 Tool，含安全约束。

| Tool | 风险等级 | 说明 |
|------|----------|------|
| `reply_email(to, subject, body, idempotency_key)` | 中 | 幂等键防重发；SMTP via QQ 邮箱授权码 |
| `forward_email(to, email_id, idempotency_key)` | 中 | 同上 |
| `label_email(email_id, label)` | 低 | 直接执行 |
| `create_calendar_event(title, time, participants)` | 低 | — |
| `create_task(title, description, due_date)` | 低 | — |
| `move_to_trash(email_id, reason)` | **高** | 软删除，30天可恢复；`reason` 字段必填 |
| `permanently_delete(email_id, confirmed: bool)` | **高** | `confirmed=False` 时返回确认请求，**不执行删除** |

**验收**：`permanently_delete(confirmed=False)` 不执行；所有高风险 Tool 调用均有审计日志。

---

## Phase 4 — 记忆与上下文

**目标**：支持跨邮件线程的上下文理解和历史检索。

| # | 任务 | 关键点 |
|---|------|--------|
| 4.1 | 短期记忆 | Thread-ID 关联同线程历史；单邮件上下文 ≤ 8K tokens，线程历史 ≤ 16K tokens；超出时先用 GPT-4o-mini 摘要再传入 LLM |
| 4.2 | 长期记忆 | 邮件摘要 **PII 脱敏**（姓名/电话/银行卡）后向量化存入 ChromaDB |
| 4.3 | 数据留存 | 向量索引 90 天自动过期；实现"被遗忘权"接口（按联系人清除所有向量记录） |
| 4.4 | 用户偏好 | 记录手动覆盖操作（含拒绝删除的记录），写回 System Prompt |

**验收**：语义检索正确召回历史邮件；被遗忘权接口清除指定联系人记录。

---

## Phase 5 — 测试与评估

**目标**：保证意图分类准确率可持续，防止 prompt 改动后静默劣化。

| # | 任务 | 关键点 |
|---|------|--------|
| 5.1 | 构建 Golden Dataset | 覆盖：回复、转发、软删除、永久删除、创建日程、边界 case、Prompt Injection 样本、批量删除样本 |
| 5.2 | 自动评估流水线 | 集成 `promptfoo` / LangSmith Evaluation；**准确率 < 95% 阻断部署** |
| 5.3 | 沙箱集成测试 | 使用独立测试邮箱做端到端测试，不污染真实邮箱 |
| 5.4 | 本地开发 Mock 策略 | IMAP：录制/回放真实邮件（`unittest.mock` + `aioimaplib` mock）；SMTP：`aiosmtplib` mock 拦截发送；LLM：`pytest` 固定返回值或 LangSmith dataset replay；Celery：内存 broker 模式（`task_always_eager=True`）|

**验收**：Golden Dataset 准确率 ≥ 95%；CI 中 prompt 变更自动触发评估。

---

## Phase 6 — 部署与观测

**目标**：可运行、可观测、可告警。

| # | 任务 | 关键点 |
|---|------|--------|
| 6.1 | 容器化 | Dockerfile + Compose（Agent + Redis + PostgreSQL + ChromaDB） |
| 6.2 | 日志脱敏 | 所有日志屏蔽邮件正文、收件人、PII 字段 |
| 6.3 | 审计日志 | 独立审计表（删除操作）：触发原因 + LLM 推理链 + 操作来源 + 时间戳，**不可覆盖** |
| 6.4 | Trace | LangSmith 追踪每次完整决策链路 |
| 6.5 | 监控告警 | Prometheus + Grafana；告警项：处理延迟、Token 成本、失败率、**删除频率异常**、**Injection 命中率** |
| 6.6 | CI/CD 流水线 | GitHub Actions；触发条件：PR 合并到 main；阶段：`lint → unit test → Golden Dataset 评估（≥95% 通过）→ 构建镜像 → 部署` |

**验收**：LangSmith 可追溯完整 trace；Grafana 删除频率和 Injection 告警正常触发。

---

## 各 Phase 依赖关系

```
Phase 1 → Phase 2 → Phase 3  （串行，基础层依次构建）
                 ↘ Phase 4    （Phase 2 完成后可并行开始）
Phase 3 + Phase 4 → Phase 5  （需要 Tools 和记忆就绪后才能评估）
Phase 5 → Phase 6            （评估通过后才部署）
```

---

## 决策记录

| 决策 | 原因 |
|------|------|
| 使用 QQ 邮箱 IMAP/SMTP 替代 Gmail API | 无需 GCP 项目和 OAuth2 应用审核，授权码认证更简单；IMAP IDLE 可实现近实时推送，满足响应需求 |
| 删除 Tool 拆分为 `move_to_trash`（软删除）和 `permanently_delete`（硬删除） | 降低误删风险，`confirmed` 标志位作为最后一道防护 |
| 删除意图归为高风险，强制人工确认 | 不可逆操作，LLM 幻觉风险不可接受 |
| 邮件正文用 XML 标签角色隔离，Prompt Injection 检测为独立首节点 | 邮件正文是最高危的外部输入 |
| 附件先扫描后处理，恶意文件不进入 LLM 上下文 | 防止恶意附件触发 LLM 漏洞 |
| 分模型路由：分类用 GPT-4o-mini，决策用 GPT-4o | 控制 Token 成本 |
| PII 脱敏 + 90 天留存 + 被遗忘权接口 | GDPR 合规 |
| 超时未响应默认拒绝 | 人工确认节点的安全兜底 |
