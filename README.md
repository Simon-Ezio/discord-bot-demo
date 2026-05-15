# Hermes-lite Discord Relationship Bot

一个极简的 Discord 陪伴机器人。启动时对自身和主人一无所知，通过自然对话逐步形成身份、记忆和关系，并将一切持久化到本地文件中。

```
"Would you actually want this bot?" — PRD
```

## 交付清单

| # | 交付项 | 说明 | 状态 |
|---|--------|------|------|
| 1 | **GitHub Repo** | 本仓库，已分享至 pikarecruit | ✅ |
| 2 | **Discord Bot** | 在线运行，邀请链接单独提供 | ✅ |
| 3 | **State Files** | `state/` 目录下所有记忆文件，交互后发送 | ✅ |
| 4 | **Loom (≈5min)** | 架构讲解 + 记忆机制 + Proactive + 改进方向 | ⏳ |

**Bot 配置：** Owner 设为 `cm6550`，在指定频道对话即可测试。

---

## 技术栈

| 层 | 技术 |
|---|------|
| 语言 | Python 3.11+ |
| Discord | discord.py 2.4+ |
| HTTP | httpx (异步) |
| LLM | MiniMax API (ChatCompletion v2) |
| 存储 | 本地 Markdown + JSON 文件 |
| 包管理 | uv + pyproject.toml |
| 测试 | pytest |

**刻意不做：** 没有数据库、没有向量存储、没有插件系统、没有完整对话记录存储。

---

## 架构总览

```
                        ┌──────────────────────────┐
                        │       Discord Server       │
                        │  ┌────────┐  ┌─────────┐  │
                        │  │ Chat   │  │  Log    │  │
                        │  │Channel │  │ Channel │  │
                        │  └───┬────┘  └────┬────┘  │
                        └──────┼─────────────┼───────┘
                               │ msg         │ log
                               ▼             ▼
┌──────────────────────────────────────────────────────────────┐
│                     DiscordAdapter                            │
│  - 过滤：只响应 OWNER_USER_ID + CHAT_CHANNEL_ID               │
│  - 下载图片附件 → local path                                  │
│  - 消息分片（1900 字符/Discord 限制）                         │
│  - @everyone/@here 净化                                       │
└──────────────────────────┬───────────────────────────────────┘
                           │ MessageEvent
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                       BotRuntime                              │
│  编排层：加载快照 → 调用 Agent → 发送回复 → 保存记忆 → 记录事件│
└───────┬──────────────────────────────────┬───────────────────┘
        │                                  │
        ▼                                  ▼
┌───────────────┐                 ┌──────────────────┐
│ Relationship  │                 │  MemoryStore     │
│    Agent      │                 │  + MemoryCurator │
│               │                 │                  │
│ chat (回复)   │◄── MemorySnapshot│ markdown/json   │
│ reflect (记忆)│                 │ 读写 + 压缩      │
│ plan_proactive│                 │ events.jsonl     │
└───────┬───────┘                 └──────────────────┘
        │
        ▼
┌───────────────┐
│ MiniMaxClient │
│  LLM API 调用  │
└───────────────┘
```

---

## 数据流

### 消息处理流程

```
Owner 发消息
    │
    ▼
DiscordAdapter.on_message()
    │ 过滤 owner + channel
    ▼
BotRuntime.handle_message()
    │
    ├─► MemoryStore.load_snapshot()
    │   读取 bot_identity.md, owner_profile.md,
    │   relationship_journal.md, avatar_prompt.md,
    │   runtime_state.json, conversation_history.json
    │
    ├─► RelationshipAgent.respond()
    │   ┌──────────────────────────────────────┐
    │   │ Step 1: Chat                         │
    │   │ PromptBuilder.build_chat_messages()   │
    │   │ → MiniMaxClient.complete()            │
    │   │ → 解析 JSON → reply_text              │
    │   └──────────────┬───────────────────────┘
    │                  │ reply_text
    │   ┌──────────────▼───────────────────────┐
    │   │ Step 2: Reflection                   │
    │   │ PromptBuilder.build_reflection_messages()│
    │   │ → MiniMaxClient.complete()            │
    │   │ → 解析 JSON → memory_updates          │
    │   └──────────────────────────────────────┘
    │
    ├─► DiscordAdapter.send_chat(reply_text)
    │   发送回复到 Discord
    │
    ├─► MemoryStore.save_conversation_history()
    │   保存 owner + bot 消息到最近 10 条历史
    │
    ├─► MemoryCurator.apply_updates()
    │   应用 add/replace/remove 操作到 md 文件
    │   必要时触发 memory compaction
    │
    ├─► MemoryStore.save_runtime_state()
    │   更新 last_owner_message_at, unanswered_proactive_count
    │
    └─► MemoryStore.append_event()
       记录 owner_message + memory_update 到 events.jsonl
```

### Proactive 流程

```
run_proactive_loop() (后台 asyncio Task)
    │ 每 PROACTIVE_CHECK_SECONDS 秒醒来
    ▼
run_proactive_tick()
    │
    ├─► ProactivePlanner.maybe_plan()
    │   ┌────────────────────────────────────┐
    │   │ ProactivePolicy.precheck()          │
    │   │ - 检查 idle 窗口 (min/max)          │
    │   │ - early stage 用更短的 min_idle     │
    │   │ - 未回复 backlog 指数退避 + cap      │
    │   │ - 通过 → 调用 Agent                 │
    │   └────────────┬───────────────────────┘
    │                │
    │   ┌────────────▼───────────────────────┐
    │   │ RelationshipAgent.plan_proactive()  │
    │   │ - 是否有合理动机（follow-up/命名等） │
    │   │ - 生成自然、非机械的主动消息         │
    │   └────────────┬───────────────────────┘
    │                │ ProactiveDecision
    ▼
    ├─► DiscordAdapter.send_chat(message)
    ├─► MemoryStore.save_conversation_history()
    ├─► MemoryStore.save_runtime_state()
    └─► MemoryStore.append_event()
       proactive_sent / proactive_failed
```

---

## 目录结构

```
discord-bot-demo/
├── run.py                          # 入口 (uv run python run.py)
├── CLAUDE.md                       # Claude Code 项目指令
├── README.md                       # 本文档
├── pyproject.toml                  # 依赖和构建配置
├── .env.example                    # 环境变量模板
│
├── src/bot/
│   ├── config.py                   # BotConfig — 从环境变量加载配置
│   ├── main.py                     # build_runtime, amain, proactive loop
│   ├── runtime.py                  # BotRuntime — 编排层
│   ├── models.py                   # 所有数据模型 (dataclasses)
│   ├── safety.py                   # 输出净化 + 记忆内容过滤
│   │
│   ├── agent/
│   │   ├── prompt_builder.py       # 三层 Prompt 构建器
│   │   ├── relationship_agent.py   # Chat + Reflection + Proactive Agent
│   │   └── minimax_client.py       # MiniMax LLM 适配器
│   │
│   ├── memory/
│   │   ├── store.py                # 文件读写、快照、历史、事件
│   │   └── curator.py              # add/replace/remove 记忆操作 + 压缩
│   │
│   ├── platforms/
│   │   └── discord_adapter.py      # Discord I/O、附件下载
│   │
│   ├── scheduler/
│   │   └── proactive.py            # 主动策略 + 规划器
│   │
│   └── observability/
│       └── bot_logger.py           # 控制台 + Discord 日志频道
│
├── scripts/
│   ├── dry_run_turn.py             # 离线单轮测试（默认不调 LLM）
│   └── show_state.py               # 查看状态文件
│
├── tests/                          # pytest 测试套件 (102 tests)
│
├── state/                          # 运行时生成，不提交
│   ├── bot_identity.md             # 机器人的身份记忆
│   ├── owner_profile.md            # 主人的画像
│   ├── relationship_journal.md     # 关系日志
│   ├── avatar_prompt.md            # 头像描述
│   ├── runtime_state.json          # 运行时计数器
│   ├── conversation_history.json   # 最近 10 条对话
│   ├── events.jsonl                # 追加式事件日志
│   └── attachments/                # 下载的图片附件
│
└── docs/
    └── ARCHITECTURE.md             # 详细架构文档
```

---

## 模块职责

| 模块 | 一句话职责 | 关键方法 |
|------|-----------|----------|
| `BotConfig` | 从环境变量加载并校验全部配置 | `from_env()` |
| `DiscordAdapter` | Discord 消息收发、附件下载、过滤 | `on_message()`, `send_chat()`, `send_log()` |
| `BotRuntime` | 编排消息处理全流程 | `handle_message()` |
| `PromptBuilder` | 构建 Chat/Reflection/Proactive 三层 Prompt | `build_chat_messages()`, `build_reflection_messages()` |
| `RelationshipAgent` | 调用 LLM 生成回复 + 记忆更新 + 主动决策 | `respond()`, `plan_proactive()` |
| `MiniMaxClient` | MiniMax API 的异步 HTTP 客户端 | `complete()` |
| `MemoryStore` | 状态文件的原子读写、快照加载 | `load_snapshot()`, `save_runtime_state()`, `append_event()` |
| `MemoryCurator` | 记忆更新的 add/replace/remove + 去重压缩 | `apply_updates()`, `compact_if_needed()` |
| `ProactivePolicy` | 主动消息的时序规则 | `precheck()` |
| `ProactivePlanner` | 策略 + Agent 组合，完整主动决策 | `maybe_plan()` |
| `BotLogger` | 控制台 + Discord 双通道日志，自动脱敏 | `info()`, `error()` |

---

## 状态文件设计

### `bot_identity.md`
机器人的自我认知。随对话逐步填充姓名、性格、语调。

```markdown
# Bot Identity
- The bot's personality is not yet formed...
- Name: 小美
- Personality: 温柔、好奇、有分寸感
- Voice: 自然口语化中文，偶尔加一点俏皮
```

### `owner_profile.md`
主人的画像 — 爱好、习惯、偏好、项目。

```markdown
# Owner Profile
- Owner likes climbing and late-night coding
- Owner is building a Discord bot for an evaluation
- Owner prefers concise, direct communication
```

### `relationship_journal.md`
关系里程碑和互动调性记录。

```markdown
# Relationship Journal
- First conversation was warm and curious
- Owner shared their project goals on day one
```

### `avatar_prompt.md`
用于图片生成的视觉描述。

```markdown
# Avatar Prompt
- A soft, warm-toned companion with a subtle glow
- Wears a green scarf, reminiscent of tea and quiet evenings
```

### `runtime_state.json`
对话和主动行为计数器。

```json
{
  "last_owner_message_at": "2026-05-16T01:30:00+00:00",
  "last_proactive_sent_at": null,
  "unanswered_proactive_count": 0,
  "last_proactive_reason": "",
  "last_proactive_message": ""
}
```

### `conversation_history.json`
保留最近 10 条消息（5 轮来回），用于 Prompt 中的对话上下文。

```json
[
  {"role": "owner", "content": "你好", "timestamp": "..."},
  {"role": "bot", "content": "嘿，你好！", "timestamp": "..."}
]
```

### `events.jsonl`
追加式事件日志，用于调试和审计。每行一条 JSON：

```jsonl
{"type":"owner_message","at":"...","summary":"Owner asked about bot name"}
{"type":"memory_update","at":"...","target":"bot_identity.md","summary":"2 update(s) applied"}
{"type":"proactive_sent","at":"...","summary":"Followed up on naming","reason":"bot still unnamed"}
{"type":"proactive_failed","at":"...","summary":"Followed up on naming"}
```

---

## Prompt 设计

系统采用**双层 LLM 调用**（Chat → Reflection），将「生成回复」和「记录记忆」分离，防止 LLM 自我强化幻觉。

### Layer 1：Chat Prompt（生成回复）

```
┌─ System ─────────────────────────────────────┐
│ ## Identity                                  │
│ Who you are, how to use identity memory      │
│                                              │
│ ## Behavior rules                            │
│ Conversation style, question limits,          │
│ anti-hallucination guardrails                │
│                                              │
│ ## Stage guidance                            │
│ Dynamic: first meeting → identity forming    │
│ → deepening → established                    │
│                                              │
│ ## Output format                             │
│ Raw JSON: {"reply_text": "..."}              │
└──────────────────────────────────────────────┘
┌─ User ───────────────────────────────────────┐
│ Memory snapshot (4 md files as data)          │
│ Recent conversation (last 10 messages)        │
│ Current message + timestamp + attachments     │
└──────────────────────────────────────────────┘
```

### Layer 2：Reflection Prompt（生成记忆更新）

```
┌─ System ─────────────────────────────────────┐
│ ## Your role                                 │
│ Analyze what happened, NOT what you imagined  │
│ Verify against owner's actual words           │
│                                              │
│ ## Onboarding progress checks                │
│ Name status, avatar status, stage-specific   │
│                                              │
│ ## Output format                             │
│ JSON with add/replace/remove memory ops       │
└──────────────────────────────────────────────┘
┌─ User ───────────────────────────────────────┐
│ Memory snapshot + conversation history        │
│ "Owner just said: <content>"                 │
│ "You just replied: <reply_text>"             │
└──────────────────────────────────────────────┘
```

### Layer 3：Proactive Prompt（主动决策）

```
┌─ System ─────────────────────────────────────┐
│ Should you reach out? Must have a reason.     │
│ Memory-as-data, be conservative if ignored.   │
│ "Would a real friend text this right now?"    │
└──────────────────────────────────────────────┘
┌─ User ───────────────────────────────────────┐
│ All 4 memory files + runtime_state            │
└──────────────────────────────────────────────┘
```

### 记忆操作类型

| 操作 | 含义 | JSON |
|------|------|------|
| `add` | 追加一条新记忆（默认） | `{"op":"add","value":"Owner likes climbing"}` |
| `replace` | 查找并替换整行 | `{"op":"replace","find":"likes climbing","value":"Owner loves bouldering"}` |
| `remove` | 查找并删除整行 | `{"op":"remove","find":"likes climbing"}` |

兼容旧格式：字符串 `"Owner likes climbing"` 自动视为 `{"op":"add","value":"Owner likes climbing"}`。

---

## Proactive 主动行为

### 策略规则表

| 条件 | 行为 |
|------|------|
| `unanswered_proactive_count >= 2` | 停止，直到 owner 再次说话 |
| `stage == "early"` (无身份/无画像) | min_idle = `PROACTIVE_EARLY_IDLE_SECONDS` (默认 150s)，每天最多 2 次 |
| `stage == "established"` | min_idle = `PROACTIVE_MIN_IDLE_SECONDS` (默认 300s)，每天最多 1 次 |
| 有未回复的主动消息 | 指数退避: `min_idle * 2^count`，cap = `PROACTIVE_BACKOFF_CAP_SECONDS` (7200s) |
| 超出 `PROACTIVE_MAX_IDLE_SECONDS` (86400s) | 不再主动 — 太久了不合适 |
| 无合理动机 | 不发送 |

### 合理动机 vs 无效消息

| ✅ 合理 | ❌ 无效 |
|---------|---------|
| 还没名字，想请主人起名 | "Hi" |
| Follow-up 主人提过的项目 | "Are you there?" |
| 头像方向建议 | "Please talk to me" |
| owner_profile 里有保存的 follow-up item | 重复泛泛的 check-in |

---

## 对话阶段

| 阶段 | 触发条件 | 行为特征 |
|------|---------|---------|
| **First meeting** | 0-2 轮对话 | 温暖、好奇、了解基本信息 |
| **Identity forming (无名)** | 还没名字 | 优先请主人起名 |
| **Identity forming (有名)** | ≤5 轮 | 让个性在回应中自然展现 |
| **Deepening** | 6-10 轮 | 自然引用过去对话，让主人感觉被记住 |
| **Established** | >10 轮 | 丰富的共享历史，很少需要提问 |

---

## 故障处理

| 故障 | 处理 | 影响 |
|------|------|------|
| LLM API 异常 | 发 fallback 回复，**不更新记忆**，记录 error log | 单条消息丢失对话质量，状态不损坏 |
| LLM 返回非 JSON | 尝试提取 plain text 当做回复，跳过记忆更新 | 同上 |
| JSON 无 reply_text | 发 fallback 回复 | 同上 |
| 文件写入失败 (OSError) | 捕获异常，记录 error log，**不崩溃** | 本轮记忆丢失，下次对话正常 |
| Discord send 失败 | 记录 error log，不做 tight retry loop | 消息未送达但不影响系统 |
| 被主人 ignore | 指数退避 + cap，连续 2 次未回复停止 | 不骚扰 |
| events.jsonl 写入失败 | 静默忽略 — best-effort | 事件日志缺失但不影响主流程 |
| 客户端启动失败 | `SystemExit(1)` + `client.close()` | 优雅退出 |

---

## 环境变量

```dotenv
# ── 必填 ──
DISCORD_BOT_TOKEN=          # Discord Bot Token
MINIMAX_API_KEY=            # MiniMax API Key
OWNER_USER_ID=              # 主人的 Discord 用户 ID
CHAT_CHANNEL_ID=            # 对话频道 ID
LOG_CHANNEL_ID=             # 日志频道 ID

# ── 可选 ──
OWNER_USERNAME=cm6550       # 仅用于显示/日志，不做鉴权
MINIMAX_BASE_URL=https://api.minimax.chat/v1/text/chatcompletion_v2
MINIMAX_MODEL=MiniMax-Text-01
STATE_DIR=state

# ── Proactive 调参 ──
PROACTIVE_CHECK_SECONDS=60           # 后台 loop 的检查间隔
PROACTIVE_MIN_IDLE_SECONDS=300       # 正常最小空闲（主人不说话多久后可主动）
PROACTIVE_MAX_IDLE_SECONDS=86400     # 最大空闲（超过则放弃主动）
PROACTIVE_EARLY_IDLE_SECONDS=150     # Early stage 的 min_idle（更积极）
PROACTIVE_BACKOFF_CAP_SECONDS=7200   # 未回复指数退避的上限

# ── 代理 ──
PROXY=                      # HTTP 代理
PROXY_SSL_VERIFY=true       # 代理 SSL 验证
```

---

## Setup & Run

```bash
# 1. 安装依赖
uv sync --extra dev

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 DISCORD_BOT_TOKEN、MINIMAX_API_KEY 等

# 3. 运行
uv run python run.py

# 4. 查看状态（不打印 secrets）
uv run python scripts/show_state.py --state-dir state

# 5. 离线单轮测试（不调 LLM，用确定性 DryRunAgent）
uv run python scripts/dry_run_turn.py --message "Hello" --state-dir state

# 6. 离线测试 + 调 MiniMax API
uv run python scripts/dry_run_turn.py --message "Hello" --state-dir state --use-minimax

# 7. 运行测试
uv run pytest
```

### Discord Developer Portal 配置

1. 开启 **Developer Mode** → 复制 User ID 和 Channel ID
2. Bot 需开启 **Message Content Intent**
3. Bot 加入 Server 时权限至少需 `Send Messages` + `Attach Files`

### Proactive 快速调试

开发时用短间隔快速看到主动行为：

```dotenv
PROACTIVE_CHECK_SECONDS=10
PROACTIVE_MIN_IDLE_SECONDS=30
PROACTIVE_EARLY_IDLE_SECONDS=15
PROACTIVE_BACKOFF_CAP_SECONDS=60
```

---

## 评估标准对照

| PRD 标准 | 实现 |
|----------|------|
| Product Taste — 像人还是像问卷？ | 分层 Prompt + 阶段指导 + 只问一个问题 |
| Conversational Judgment | Chat/Reflection 分离，Reflection 验证 owner 原话 |
| Proactive Logic — 真实动机 | 策略引擎：stage-aware + 动机枚举 + 指数退避 |
| Memory Design — 自然回忆 | Markdown bullet + add/replace/remove + Jaccard 去重压缩 |
| Failure Handling — 优雅降级 | fallback 回复 + 不损坏记忆 + 静默忽略非关键错误 |
| Code Quality — 简洁可读 | 无框架、无数据库、全文件存储、102 tests |
