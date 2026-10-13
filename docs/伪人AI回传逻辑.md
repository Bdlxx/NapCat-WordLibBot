# 伪人插件 · AI 回传信息逻辑

> 插件文件：`instances/<QQ>/plugins/pseudo_persona.py`
> 目标：讲清「一条消息进来 → 组织哪些信息发给 AI → 回复如何发出」的完整链路。

---

## 1. 数据流总览

```
QQ 消息事件
   │
   ▼
extract_text() / extract_images()     ← 从消息段提取文本 + 图片 URL
   │
   ▼
触发判定（私聊直接 / 群聊 @或提机器人名）
   │ 触发
   ▼
handle() 组装 payload（文本、图片、clean_text）
   │ 立即返回（不阻塞主循环）
   ▼
会话级后台队列（每群/私聊一个 FIFO worker 线程）
   │
   ├─ get_context_for_ai()   ← 历史上下文（当前消息之前）
   ├─ add_to_history(user)   ← 记录本条用户消息
   ├─ call_ai()              ← 系统提示 + 历史 + 本条 + 图片 → AI
   ├─ add_to_history(assistant)
   └─ split_msg() → 分段发送
```

---

## 2. 输入提取

| 内容 | 来源 | 说明 |
|---|---|---|
| `text` | 消息段中所有 `type=text` 拼接 | `extract_text(event)` |
| `images` | 消息段中所有 `type=image` 的 `data.url` | `extract_images(event)`，仅取 URL 字段 |
| `user_id` | `event.user_id` | 说话者 QQ |
| `self_id` | `event.self_id` | 用于过滤机器人自己的消息（不响应自消息） |

---

## 3. 触发条件（决定哪些消息会"回传"给 AI）

1. **自消息过滤**：机器人自己发的消息 → 直接忽略。
2. **主人开关指令**（开启/关闭伪人、切模型、清历史等）→ 注册表直接处理，不进 AI。
3. **屏蔽词放行**：文本含其他插件指令（如 `B站登录`、`开启视频解析`）→ 交给对应插件，不进伪人。
4. **触发判定**：
   - **私聊**：默认直接对话（必触发候选）。
   - **群聊**：消息包含机器人名 或 @ 机器人 才算触发候选。
5. **概率**：`random.random() > reply_probability`（默认 1.0 = 必回）则不触发；不触发仍记录进历史（群聊默认只记录与 bot 相关消息，`record_group_unrelated=False` 时无关闲聊不记录，避免污染上下文）。

---

## 4. 系统提示（system prompt）构建 —— `build_system_prompt()`

按顺序拼接：

1. **默认人设**（动态取 bot 名）：
   ```
   你是{依星/羽笙}，一个温柔可爱的女孩子。
   性格：温柔体贴、善解人意、偶尔撒娇卖萌
   风格：用简短句子、语气词（呀呢嘛啦）、颜文字 (◕‿◕)
   像朋友聊天，不要像客服。
   看到图片时要自然地评论图片内容，像朋友一样聊天。
   ```
2. **用户补充人设** `user_persona`（若有）。
3. **插件人设** `persona`（web 面板配置的完整人设模板，含群聊说话规范、`|#|#|` 分段语法、`[@QQ]` 艾特语法、`![图片](url)` 图片语法等）——自动识别并跳过旧版残留的默认人设避免重复。
4. **消息分段规则**：说明用 `|#|#|` 分隔多句。
5. **长期记忆**：注入与该用户相关的记忆条目（`build_memory_context`）。
6. 将人设中的 `[nick]` 替换为当前用户昵称（群名片 → 昵称 → "对方"）。

---

## 5. 历史上下文构建 —— `get_context_for_ai()`

- 会话 key：群聊 = `group_{群号}`；私聊 = `private_{QQ}`。
- 历史记录结构（`add_to_history` 写入）：
  ```python
  {role: "user"/"assistant", content, user_id, sender_name,
   triggered, has_image, timestamp}
  ```
- **摘要压缩**：历史超过 `context_window` 最近 10 轮（`raw_limit`）时，更早的旧记录（最多 12 条）压缩为一行摘要：
  ```
  [历史摘要]
  {昵称}(QQ): 内容前50字
  机器人: 内容前50字
  ```
  摘要以一条 `role=user` 消息发给 AI。
- **最近窗口**：取最近 `min(context_window=20, raw_limit=10)` 条原始记录逐条转 messages：
  - **用户消息**：`content = "{昵称}({QQ}): {内容}"`（`role: user`）→ AI 能区分群里不同说话者。
  - **机器人消息**：`content = 原始内容`（`role: assistant`）——**不加任何前缀**（曾加过"依星: "前缀导致 AI 模仿输出，已修复）。
- **要点**：当前正在处理的消息**尚未写入历史**（worker 内先取上下文、后 add），避免 AI 收到重复的"本条消息"。

---

## 6. 当前消息组装 —— `call_ai()` 内

发送者标识（嵌入文本，不用 name 字段）：

- 有昵称：`{昵称}({QQ}): `；无昵称：`u{QQ}: `；均无：不带前缀。

**有图片时**（OpenAI 兼容多模态格式）：

```json
{
  "role": "user",
  "content": [
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<图片base64>"}},
    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<图2base64>"}},
    {"type": "text", "text": "昵称(QQ): <本条文字，若无文字则固定文案>"}
  ]
}
```

- 每张图片经 `download_image_as_base64(url)` 下载 → base64（下载失败自动跳过该图）。
- **无文字但有图**：文本用文案模板：`msg("check_image")` = "看看你发了什么图~"（实际发的是"发了一张图片"占位文本）。
- 支持模型：`glm-4v-flash`（主）、`gemini-2.5-flash`（备）——均为多模态视觉模型，通过统一 OpenAI 兼容网关（`/v1/chat/completions`）调用。

**纯文本时**：

```json
{"role": "user", "content": "昵称(QQ): 本条文字"}
```

---

## 7. 模型调用与容错

1. 主模型 `current_model`（默认 glm-4v-flash）；失败自动切换备用 `gemini-2.5-flash`（带冷却，主模型恢复后切回）。
2. 请求体：`model / messages(system+context+当前) / temperature(0.8) / max_tokens(500)`，超时 `api_timeout(90s)`。
3. 双模型都失败 → 返回文案 `msg("no_reply")` = "唔...我好像有点累了，待会再聊吧~"。

---

## 8. 回复后处理与发送

1. 去掉 AI 开头的 meta 确认句（`好的，我明白了。` / `我知道了。` 等，仅整句为确认时删除）。
2. 去除完全重复的整行。
3. 压缩多余空白。
4. 记录 `assistant` 进历史。
5. `split_msg()` 分段：
   - 清理零宽/控制字符；
   - 含 `|#|#|` 时按分隔符切分，超过 `split_count`(3) 丢弃末尾多余段；
   - 每段之间 `sleep(1~3s)`；
   - 段内含 `[@QQ]` 语法 → 转成真实 QQ @ 消息段（`_build_at_segments`）。
6. 逐段 `send_message` 发送，日志打印 `[伪人] 发送: {part}`。

---

## 9. 并发与连续消息（重要）

- **主消息循环不被阻塞**：AI 调用（同步 requests，5~90 秒）全部放在**会话级后台 worker 线程**里执行；`handle()` 只做轻量判定 + 入队后立即返回。
- **每会话一个 FIFO worker**：同一群/私聊的消息按到达顺序排队处理。
- **连续发两条消息**：第二条的 worker 处理时，第一条的（user + assistant）已写入历史 → AI 能看到完整来龙去脉，回复自然衔接。
- 不同会话（不同群/私聊）之间互不排队，可并行。

---

## 10. 关键配置速查（data/persona_config.json）

| 键 | 默认 | 作用 |
|---|---|---|
| `current_model` | `glm` | 主模型 |
| `glm.model` | `glm-4v-flash` | 视觉模型 |
| `gemini.model` | `gemini-2.5-flash` | 备用视觉模型 |
| `reply_probability` | 1.0 | 触发后必回复的概率 |
| `record_group_unrelated` | false | 群聊是否记录无关消息入上下文 |
| `max_history` | 50 | 每会话历史上限（超出丢最旧） |
| `context_window` | 20 | 发给 AI 的最近消息条数 |
| `split_count` / `split_delay_min/max` | 3 / 1 / 3 | 回复分段数与间隔 |
| `temperature` / `max_tokens` / `api_timeout` | 0.8 / 500 / 90 | 生成参数 |

---

*文档依据 pseudo_persona.py 当前代码整理（2026-09 版本）。*
