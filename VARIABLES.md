# 变量参考表 — Variable Reference

## 词库插件 (wordlib) — `[变量名]` 格式

### 通用变量（所有回复可用）

| 变量 | 说明 | 示例值 |
|------|------|--------|
| `[qq]` | 发送者的QQ号 | `1234567890` |
| `[name]` | 发送者的群昵称 | `小明` |
| `[nick]` | 发送者的自定义昵称（如有设置） | `大佬` |
| `[card]` | 发送者的群名片 | `管理员-小明` |
| `[group_id]` | 当前群号 | `957918829` |
| `[favor]` | 发送者当前好感度 | `25` |
| `[time]` | 当前时间(HH:MM:SS) | `14:30:00` |
| `[date]` | 当前日期(YYYY-MM-DD) | `2026-05-12` |
| `[datetime]` | 当前日期时间 | `2026-05-12 14:30:00` |
| `[bot_qq]` | 机器人自己的QQ号 | `2551736206` |
| `[message_id]` | 当前消息的ID | `12345` |
| `[raw_message]` | 当前消息的原始文本 | `签到` |
| `[r1-100]` | 1~100随机整数 | `42` |
| `[r1-1000]` | 1~1000随机整数 | `742` |
| `[rX-Y]` | X~Y随机整数（X和Y可自定义） | `[r50-200]` → `127` |
| `[img:URL]` | 嵌入图片（URL指向的图片） | `[img:https://example.com/pic.jpg]` |
| `[@qq]` | @发送者 | `@小明` |
| `[@QQ]` | @发送者（同上） | `@小明` |
| `[avatar]` | 发送者的QQ头像 | 图片消息段 |
| `[next]` | 将回复拆分成多条消息发送 | — |

### 模板专用变量

| 变量 | 所属回复模板 | 说明 |
|------|-------------|------|
| `[add]` | `sign_success` | 本次签到增加的好感度 |
| `[minus]` | `sign_already` | 重复签到扣除的好感度 |
| `[need]` | `nickname_fail` | 设置昵称还差的好感度 |
| `[count]` | `praise_success`, `add_success_*`, `delete_reply_success`, `query_*` | 点赞次数 / 回复条数 |
| `[keyword]` | `add_success_*`, `delete_*`, `query_*` | 词条关键词 |
| `[idx]` | `rank_item`, `query_*`, `delete_reply_success` | 序号 |
| `[content]` | `delete_reply_success`, `query_detail_item` | 回复内容摘要 |
| `[cmd]` | `add_format_error`, `delete_format_error` | 命令关键词 |
| `[top]` | `rank_title`, `query_list_title` | 排行榜/列表显示数量 |
| `[uid]` | `rank_item` | 用户QQ号 |
| `[total]` | `rank_item` | 签到总次数 |
| `[code]` | `encode_result` | 转码后的CQ码 |

---

## 结婚插件 (marry) — `{变量名}` 格式 (Python str.format)

| 变量 | 所属回复模板 | 说明 |
|------|-------------|------|
| `{rate}` | `prob_set` | 设置的结婚成功率 |
| `{hours}` | `cd_set`, `divorce_cooldown` | 设置的CD小时数 / 剩余冷却小时 |
| `{minutes}` | `divorce_cooldown` | 剩余冷却分钟（不足1小时时显示） |

---

## 伪人插件 (pseudo_persona) — `{变量名}` 格式 (Python str.format)

| 变量 | 所属回复模板 | 说明 |
|------|-------------|------|
| `{model}` | `current_model` | 当前使用的AI模型名称 |

---

## 插件提示词 (persona) — `[占位符]` 格式

| 占位符 | 说明 |
|--------|------|
| `[nick]` | 对方的自定义昵称（自动替换） |
