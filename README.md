# NapCat WordLib Bot

📦 基于 NapCat 的 QQ 机器人框架 + 一键部署脚本 | [v1.0.0 发布说明](https://github.com/Bdlxx/NapCat-WordLibBot/releases/tag/v1.0.0)

```bash
# 一键部署（Ubuntu/Debian/CentOS）
bash <(curl -s https://raw.githubusercontent.com/Bdlxx/NapCat-WordLibBot/master/install.sh)
```

---

## 📋 目录

- [一键安装脚本](#-一键安装脚本-installsh)
  - [部署新实例](#1-部署新实例)
  - [实例管理](#2-实例管理)
  - [后续设置](#3-后续设置)
- [手动部署](#-手动部署)
- [Web 管理面板](#-web-管理面板)
- [插件开发 (SDK)](#-插件开发-sdk)
- [内置插件：词库](#-内置插件词库-wordlib)
- [项目结构](#-项目结构)

---

## 📦 一键安装脚本 (`install.sh`)

交互式 TUI 菜单（基于 whiptail），支持多实例独立部署。

### 主菜单

```
1. 📦 部署新实例
2. 🗂  实例管理
3. 🔗 后续设置
Q. 🚪 退出
```

### 1. 部署新实例

为每个 QQ 号创建完全独立的运行环境：

1. **输入 QQ 号** → 作为实例标识
2. **环境检测** → Docker/Python3/screen/git 自动检测
3. **部署 NapCat** → Docker 拉镜像 → 创建独立容器 `napcat_{QQ}`
   - 支持 `host` 或 `bridge` 网络模式
   - 自动生成端口和 Token 配置
   - 自动写入 `onebot11_{QQ}.json`
4. **部署项目** → 从 GitHub 克隆或使用本地目录
5. **配置向导** → 填写机器人昵称、主人QQ、连接信息
6. **自动生成** `config.json` + `wordlib_config.json`

### 2. 实例管理

自动扫描所有已部署实例，显示列表：

```
📊 完整状态查看
▶️  / ⏹  / 🔄  NapCat 容器启停
📱 二维码获取（扫码登录QQ）
🤖 Bot 管理（启停/重启/日志）
📋 日志查看（NapCat日志 + runtime.log）
❌ 卸载实例
```

### 3. 后续设置

- 安装 `napbot` 全局命令
- Web 面板 systemd 服务（含公网访问开关）

---

## 🔧 手动部署

### 环境要求

- Python 3.10+
- NapCat 服务（WebSocket + HTTP）
- `screen` 进程管理

### 安装

```bash
pip install websocket-client requests flask
```

### 配置

编辑 `config.json`：

```json
{
  "_note": "机器人主配置",
  "BOT_NAME": "机器人昵称",
  "MASTER_QQ": [123456789],
  "BOT_QQ": 2551736206,
  "NAPCAT_HTTP": "http://127.0.0.1:3000",
  "ACCESS_TOKEN": "your-http-token",
  "WS_URL": "ws://127.0.0.1:3001/?access_token=your-ws-token"
}
```

| 配置项 | 说明 |
|--------|------|
| `BOT_NAME` | 机器人昵称，用于回复和命令前缀 |
| `MASTER_QQ` | 主人 QQ 号（数组，可多个） |
| `BOT_QQ` | 机器人自己的 QQ 号 |
| `NAPCAT_HTTP` | NapCat HTTP 接口地址（调 API 用） |
| `ACCESS_TOKEN` | NapCat HTTP Token |
| `WS_URL` | NapCat WebSocket 连接地址（接收事件） |

### 启动

```bash
# 启动机器人
python main.py --bot-name "昵称" --bot-qq 123456789

# 或通过 screen 管理
screen -dmS bot python3 main.py --bot-name "昵称" --bot-qq 123456789
```

---

## 🌐 Web 管理面板

浏览器管理词库配置，支持单实例和双 bot 模式。

```bash
# 启动（默认 http://127.0.0.1:8080）
python web/api.py

# 公网访问
python web/api.py --host 0.0.0.0 --port 8080

# 单实例模式（指定项目目录）
python web/api.py --bot-dir /root/mybot_123456 --bot-name "我的Bot" --bot-qq 123456789
```

### Web 面板参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--host` | `127.0.0.1` | 监听地址，`0.0.0.0` 开放公网 |
| `--port` | `8080` | 监听端口 |
| `--bot-dir` | `None` | 单实例模式：机器人项目目录 |
| `--bot-name` | `None` | 单实例模式：机器人名称 |
| `--bot-qq` | `None` | 单实例模式：机器人 QQ |
| `--bot-screen` | `bot` | 单实例模式：screen 会话名 |

---

## 🔌 插件开发 (SDK)

框架支持热加载插件，放在 `plugins/` 目录即可。

### 插件规范

```python
# plugins/echo.py
from utils.api import send_message

def handle(event: dict) -> bool:
    """收到 'ping' 回复 'pong'，返回 True 表示已处理"""
    if event.get("raw_message", "").strip() == "ping":
        send_message(event, "pong")
        return True
    return False
```

- 文件须导出 `handle(event: dict) -> bool` 函数
- 返回 `True` 终止事件传递，`False` 交给下一个插件
- 插件按文件名排序执行

### 事件结构

| 字段 | 说明 | 示例 |
|------|------|------|
| `post_type` | 事件类型 | `"message"` |
| `message_type` | 消息类型 | `"group"` / `"private"` |
| `raw_message` | 原始文本 | `"签到"` |
| `user_id` | 发送者 QQ | `123456789` |
| `group_id` | 群号 | `957918829` |
| `message` | 消息段数组 | `[{"type":"text","data":{...}}]` |

### API 工具

```python
from utils.api import send_message, http_get

# 回复消息（自动判断群/私聊）
send_message(event, "你好！")

# 回复消息段（图文混排）
send_message(event, [
    {"type": "text", "data": {"text": "看："}},
    {"type": "image", "data": {"file": "http://..."}}
])

# 调用 NapCat REST API
members = http_get("get_group_member_list", {"group_id": 123456})
```

### 分群开关

```python
from utils.plugin_toggle import is_enabled, set_enabled

def handle(event):
    gid = event.get("group_id")
    # 检查本群是否开启
    if event.get("message_type") == "group" and not is_enabled(gid, "my_plugin"):
        return False
    # 开关命令
    if raw == "开启我的插件":
        set_enabled(gid, "my_plugin", True)
        send_message(event, "已开启")
        return True
```

需在 `utils/plugin_toggle.py` 的 `PLUGINS` 列表中注册插件名。

---

## 📖 内置插件：词库 (wordlib)

完整的词库系统：关键词回复、签到好感度、自定义昵称、点赞、转码。

### 管理员命令

| 命令 | 说明 |
|------|------|
| `{bot}跟我学` | 两步式添加词条（关键词→回复→模式） |
| `{bot}跟我学 关键词 答 回复` | 一步式精准匹配词条 |
| `添加模糊词条 关键词 答 回复` | 模糊匹配词条 |
| `{bot}忘掉 关键词` | 删除关键词及所有回复 |
| `{bot}忘掉 关键词 序号` | 删除指定回复 |
| `{bot}回忆一下` | 查看关键词列表 |
| `{bot}回忆一下 关键词` | 查看回复详情 |

> `{bot}` 替换为机器人昵称，所有命令可在 `wordlib_config.json` 的 `commands` 字段自定义。

### 用户功能

| 命令 | 说明 |
|------|------|
| `签到` / `{bot}签到` | 每日签到，增加好感度 |
| `{bot}以后叫我 XXX` | 设置自定义昵称（需 10 好感度） |
| `签到排行` | 签到次数排行榜 |
| `{bot}赞我` | 给自己点赞 |
| `转码` | 获取消息的 CQ 码原生格式 |

### 回复变量

词条回复支持变量替换，详见 [VARIABLES.md](VARIABLES.md)。

`[qq]` `[name]` `[nick]` `[card]` `[group_id]` `[favor]` `[time]` `[date]` `[datetime]`
`[bot_qq]` `[message_id]` `[raw_message]` `[r1-100]` `[r1-1000]` `[rX-Y]`
`[img:URL]` `[@qq]` `[avatar]` `[next]`

### 自定义配置

`data/wordlib_config.json`（通过 Web 面板或直接编辑）：

| 配置块 | 说明 |
|--------|------|
| `commands` | 所有触发命令文本 |
| `settings` | 参数：好感度范围、排行人数、超时时间等 |
| `messages` | 所有回复模板文本 |
| `admins` | 管理员 QQ 列表 |

---

## 📁 项目结构

```
├── install.sh              # 一键安装管理脚本
├── main.py                 # 机器人入口 / SDK 框架
├── config.json             # 机器人配置（gitignored）
├── plugins/                # 插件目录（热加载）
│   └── wordlib.py          # 词库插件
├── utils/                  # SDK 工具库
│   ├── api.py              # 消息发送 / HTTP API
│   ├── config.py           # 配置读取
│   ├── ws.py               # WebSocket 全局引用
│   ├── plugin_toggle.py    # 分群插件开关
│   └── command_table.py    # 命令表生成
├── templates/              # NapCat 配置模板
│   ├── napcat-onebot.json
│   └── napcat.json
├── web/                    # Web 管理面板（Flask）
│   ├── api.py              # 面板 API
│   └── index.html          # 登录页
├── data/                   # 运行数据（gitignored）
│   ├── wordlib_data.json
│   ├── wordlib_config.json
│   ├── user_data.json
│   ├── sign_data.json
│   ├── praise_data.json
│   └── plugin_toggle.json
├── README.md
├── VARIABLES.md            # 变量参考
└── CLAUDE.md               # 开发指引
```

---

## 术语

| 术语 | 说明 |
|------|------|
| NapCat | 基于 OneBot 协议的 QQ 机器人服务端（Docker） |
| OneBot | QQ 机器人通用协议标准 |
| CQ 码 | QQ 消息原生格式，如 `[pic=xxx.jpg]` |
| SDK | 插件开发框架 |
| 好感度 | 用户签到积累的分数 |
