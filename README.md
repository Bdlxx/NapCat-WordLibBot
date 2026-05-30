# NapCat WordLib Bot — QQ 词库机器人框架

基于 **NapCat** 的 QQ 机器人框架，采用插件化架构，内置功能完整的词库插件。

---

## 快速开始

```bash
# 1. 安装依赖
pip install websocket-client requests flask

# 2. 修改配置
#    编辑 config.json，填入你的 NapCat 连接信息

# 3. 启动机器人
python main.py --bot-name "你的机器人名" --bot-qq 123456789
```

或者启动 Web 管理面板：
```bash
python web/api.py
```

### 配置文件 `config.json`
```json
{
  "_note": "机器人主配置",
  "BOT_NAME": "羽笙",
  "MASTER_QQ": [123456789],
  "BOT_QQ": 2551736206,
  "NAPCAT_HTTP": "http://127.0.0.1:3000",
  "ACCESS_TOKEN": "your-token-here",
  "WS_URL": "ws://127.0.0.1:3001/?access_token=your-token-here"
}
```

| 配置项 | 说明 |
|--------|------|
| `BOT_NAME` | 机器人昵称，用于回复和命令前缀 |
| `MASTER_QQ` | 主人 QQ 号（数组，可多个） |
| `BOT_QQ` | 机器人自己的 QQ 号 |
| `NAPCAT_HTTP` | NapCat HTTP 接口地址 |
| `ACCESS_TOKEN` | NapCat 访问令牌 |
| `WS_URL` | NapCat WebSocket 连接地址 |

---

## 框架结构

```
├── main.py              # 入口：WebSocket 连接 + 插件调度器（SDK）
├── config.json          # 机器人配置（已 .gitignore）
├── plugins/             # 插件目录（热加载）
│   ├── wordlib.py       # 词库插件（内置）
│   └── your_plugin.py   # ← 你的插件放这里
├── utils/               # SDK 工具库
│   ├── api.py           # 发送消息、HTTP 调用 NapCat API
│   ├── config.py        # 读取 config.json 配置
│   ├── ws.py            # WebSocket 连接全局引用
│   ├── plugin_toggle.py # 分群插件开关
│   └── command_table.py # 命令表生成
├── data/                # 数据存储（已 .gitignore）
└── web/                 # Web 管理面板（Flask）
```

### 核心模块说明

| 模块 | 功能 |
|------|------|
| `main.py` | WebSocket 连接 NapCat，自动重连，插件事件分发 |
| `utils/api.py` | `send_message()` 发送消息，`http_get()` 调用 NapCat REST API |
| `utils/config.py` | 读取 `config.json`，支持命令行 `--bot-name` / `--bot-qq` 参数覆盖 |
| `utils/ws.py` | 存储全局 WebSocket 连接引用 |
| `utils/plugin_toggle.py` | 分群开关，所有插件默认关闭，需群内手动开启 |

---

## 插件开发指南（SDK）

### 插件规范

每个插件是一个独立的 `.py` 文件，放在 `plugins/` 目录下，无需注册，自动加载。

**必要条件：** 文件必须导出一个 `handle(event: dict) -> bool` 函数。

### 最小插件示例

```python
# plugins/echo.py
from utils.api import send_message

def handle(event: dict) -> bool:
    """收到 'ping' 回复 'pong'"""
    if event.get("raw_message", "").strip() == "ping":
        send_message(event, "pong")
        return True
    return False
```

### 事件结构

`event` 是 OneBot 标准的消息事件字典，关键字段：

| 字段 | 说明 | 示例值 |
|------|------|--------|
| `post_type` | 事件类型 | `"message"` |
| `message_type` | 消息类型 | `"group"` / `"private"` |
| `raw_message` | 原始文本 | `"签到"` |
| `user_id` | 发送者 QQ | `123456789` |
| `group_id` | 群号（仅群消息） | `957918829` |
| `message` | 消息段数组 | `[{"type":"text","data":{"text":"hello"}}]` |
| `sender.nickname` | 发送者昵称 | `"小明"` |
| `sender.card` | 群名片 | `"管理员"` |

### 常用 API

```python
from utils.api import send_message, http_get

# 回复消息（字符串）
send_message(event, "你好！")  # 自动判断群/私聊

# 回复消息段（如图文混排）
send_message(event, [
    {"type": "text", "data": {"text": "看这张图："}},
    {"type": "image", "data": {"file": "http://..."}}
])

# HTTP 调用 NapCat API（获取群成员列表等）
result = http_get("get_group_member_list", {"group_id": 123456})
```

### 插件配置模式

推荐插件使用独立的 JSON 配置文件（放在 `data/` 目录，已 gitignore）：

```python
import json, os

CFG_FILE = os.path.join("data", "my_plugin_config.json")

def _load():
    if os.path.exists(CFG_FILE):
        with open(CFG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def cmd(k, default=None):
    return _load().get("commands", {}).get(k, default)

def setting(k, default=None):
    v = _load().get("settings", {}).get(k)
    return v if v is not None else default
```

### 分群开关

通过 `utils.plugin_toggle` 实现每个群独立控制：

```python
from utils.plugin_toggle import is_enabled, set_enabled

# 检查本群是否开启
if event.get("message_type") == "group":
    if not is_enabled(event.get("group_id"), "my_plugin"):
        return False

# 开关命令
def handle(event):
    raw = event.get("raw_message", "").strip()
    if raw == "开启我的插件":
        set_enabled(event.get("group_id"), "my_plugin", True)
        send_message(event, "已开启")
        return True
```

插件需要在 `utils/plugin_toggle.py` 的 `PLUGINS` 列表中注册名称。

---

## 内置插件：词库 (wordlib)

功能完整的词库插件，支持关键词匹配回复、签到好感度、自定义昵称、点赞、转码等。

### 管理员命令

| 命令 | 说明 |
|------|------|
| `{bot}跟我学` | 两步式添加词条（关键词→回复→模式） |
| `{bot}跟我学 关键词 答 回复` | 一步式添加精准匹配词条 |
| `添加模糊词条 关键词 答 回复` | 添加模糊匹配词条 |
| `{bot}忘掉 关键词` | 删除关键词及所有回复 |
| `{bot}忘掉 关键词 序号` | 删除指定序号回复 |
| `{bot}忘掉 序号` | 按全局序号删除 |
| `{bot}回忆一下` | 查看所有关键词列表 |
| `{bot}回忆一下 关键词` | 查看关键词的回复详情 |

（`{bot}` 替换为机器人昵称，所有命令可在 `data/wordlib_config.json` 自定义）

### 用户功能

| 命令 | 说明 |
|------|------|
| `签到` / `{bot}签到` | 每日签到，增加好感度 |
| `{bot}以后叫我 XXX` | 设置自定义昵称（需 10 好感度） |
| `签到排行` | 签到次数排行榜 |
| `{bot}赞我` | 给自己点赞（NapCat 点赞） |
| `转码` | 获取消息的 CQ 码原生格式 |

### 回复变量

词条回复支持丰富的变量替换，详见 [VARIABLES.md](VARIABLES.md)。

### 配置

见 `data/wordlib_config.json`，可通过 Web 面板或直接编辑：

| 配置块 | 说明 |
|--------|------|
| `commands` | 所有触发命令文本 |
| `settings` | 参数：好感度范围、排行人数、超时时间等 |
| `messages` | 所有回复模板文本 |
| `admins` | 管理员 QQ 列表 |

---

## 术语对照

| 术语 | 说明 |
|------|------|
| NapCat | 基于 OneBot 协议的 QQ 机器人服务端 |
| OneBot | QQ 机器人通用协议标准 |
| CQ 码 | 原生 QQ 消息格式，如 `[pic=xxx.jpg]` |
| SDK | 插件开发框架，提供 API 和工具函数 |
| 好感度 | 用户通过签到积累的分数，用于设置昵称等 |

---

## 目录说明

```
/root/mybot2/
├── .gitignore
├── CLAUDE.md              # Claude Code 项目指引
├── VARIABLES.md           # 词库回复变量完整参考
├── README.md              # ← 本文档
├── main.py                # 机器人入口 / SDK
├── config.json            # 配置（gitignored）
├── plugins/
│   └── wordlib.py         # 词库插件
├── utils/
│   ├── __init__.py
│   ├── api.py             # 消息发送 / HTTP API
│   ├── config.py          # 配置读取
│   ├── ws.py              # WebSocket 引用
│   ├── plugin_toggle.py   # 分群开关
│   └── command_table.py   # 命令表
├── templates/             # 占位
├── web/
│   ├── api.py             # Flask Web 面板
│   ├── index.html         # 登录页
│   ├── yusheng/           # 羽笙面板
│   └── yixing/            # 依星面板
└── data/                  # 数据（gitignored）
    ├── wordlib_config.json
    ├── wordlib_data.json
    ├── user_data.json
    ├── sign_data.json
    ├── praise_data.json
    └── plugin_toggle.json
```
