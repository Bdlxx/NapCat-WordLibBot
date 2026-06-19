# NapCat WordLib Bot

📦 基于 NapCat 的 QQ 机器人框架 + 一键部署脚本 | [v1.0.1 发布说明](https://github.com/Bdlxx/NapCat-WordLibBot/releases/tag/v1.0.1)

```bash
# 一键部署（Ubuntu/Debian/CentOS）
bash <(curl -s https://raw.githubusercontent.com/Bdlxx/NapCat-WordLibBot/master/install.sh)
```

---

## 📋 目录

- [一键安装脚本](#-一键安装脚本-installsh)
- [Web 管理面板](#-web-管理面板)
- [插件开发 (SDK)](#-插件开发-sdk)
- [内置插件](#-内置插件)
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

### 部署新实例

为每个 QQ 号创建完全独立的运行环境。输入 QQ 号作为标识，自动创建独立容器 `napcat_{QQ}` 和项目目录 `/root/mybot_{QQ}`。

### 实例管理

扫描所有已部署实例，支持启停容器、扫码登录、Bot 管理、日志查看、卸载。

### 后续设置

- `napbot` 全局命令安装
- Web 面板 systemd 服务（公网访问开关、端口自定义）

---

## 🌐 Web 管理面板

基于 Flask，仿 Guoba-Plugin 风格，浅色/深色双主题。

| 页面 | 功能 |
|------|------|
| 📊 **仪表盘** | Bot / NapCat 状态指标卡，快捷操作，系统信息 |
| 🛠️ **运行管理** | Bot 启停，NapCat 二维码查看 |
| ⚙️ **插件配置** | 显示所有已安装插件列表，中英文名显示，表单配置 |
| 👥 **群组开关** | 表格化开关矩阵（行=群号×列=插件名），全选批量操作 |
| 📋 **运行日志** | 彩色日志查看器 |

### 启动

```bash
# 默认 http://127.0.0.1:8080
python web/api.py

# 公网访问
python web/api.py --host 0.0.0.0 --port 8080

# 单实例模式
python web/api.py --bot-dir /root/mybot_123456 --bot-name Bot --bot-qq 123456789
```

### 安全

- MD5 密码存储，登录限流（5 次失败冻结 15 分钟）
- CSRF 防护，会话 24 小时过期
- 密码管理：`bash set_password.sh <名称> <密码>`

---

## 🔌 插件开发 (SDK)

框架采用热加载插件架构，放在 `plugins/` 目录即可自动加载。

### SDK 规范

```python
# plugins/my_plugin.py

# ========== 插件元数据 ==========
__plugin_name_cn__ = "我的插件"      # 中文名称（WebUI 显示用）
__plugin_name_en__ = "my_plugin"     # 英文标识（需与文件名一致）
__plugin_version__ = "1.0.0"
__plugin_desc__  = "功能描述"
__plugin_author__ = "作者名"
# ===============================

from utils.api import send_message

def handle(event: dict) -> bool:
    if event.get("raw_message", "").strip() == "ping":
        send_message(event, "pong")
        return True
    return False
```

### 事件结构

| 字段 | 说明 | 示例 |
|------|------|------|
| `post_type` | 事件类型 | `"message"` |
| `message_type` | 消息类型 | `"group"` / `"private"` |
| `raw_message` | 原始文本 | `"签到"` |
| `user_id` | 发送者 QQ | `123456789` |
| `group_id` | 群号 | `957918829` |
| `message` | 消息段数组 | `[{"type":"text","data":{...}}]` |

### 常用 API

```python
from utils.api import send_message, http_get

send_message(event, "你好！")  # 回复消息
send_message(event, [          # 图文混排
    {"type": "text", "data": {"text": "看："}},
    {"type": "image", "data": {"file": "http://..."}},
])
members = http_get("get_group_member_list", {"group_id": 123456})  # HTTP API
```

### 分群开关

```python
from utils.plugin_toggle import is_enabled, set_enabled

if event.get("message_type") == "group" and not is_enabled(gid, "my_plugin"):
    return False
set_enabled(gid, "my_plugin", True)  # 开关命令
```

### 配置模式

使用独立 JSON 配置文件，WebUI 自动读取并生成表单：

```python
CFG_FILE = os.path.join("data", "my_plugin_config.json")

def cmd(k, default=None):
    return _load().get("commands", {}).get(k, default)

def setting(k, default=None):
    v = _load().get("settings", {}).get(k)
    return v if v is not None else default
```

WebUI 自动识别 `commands`（文本）、`settings`（开关/数字）、`messages`（文本域）。

---

## 📖 内置插件

### 词库插件 (wordlib)

关键词匹配回复、签到好感度、自定义昵称、点赞、转码。

| 命令 | 说明 |
|------|------|
| `{bot}跟我学` | 添加词条 |
| `{bot}忘掉` | 删除词条 |
| `{bot}回忆一下` | 查询词条 |
| `签到` | 每日签到 |
| `签到排行` | 排行榜 |
| `开启/关闭词库` | 分群开关 |

> 命令和回复模板可在 `data/wordlib_config.json` 自定义。
> 变量参考详见 [VARIABLES.md](VARIABLES.md)。

### 结婚插件 (marry)

群内每日结婚/离婚系统，支持成功率和冷却配置。

### 伪人插件 (pseudo_persona)

AI 对话回复，支持 GLM 和 Gemini 双模型切换。

### 视频解析 (video_parser)

自动检测群内视频链接并解析去水印。支持抖音、哔哩哔哩、快手、小红书、TikTok。

---

## 📁 项目结构

```
├── install.sh              # 一键安装管理脚本
├── set_password.sh         # Web面板密码管理工具
├── main.py                 # SDK 框架入口
├── config.json             # 机器人配置（gitignored）
├── plugins/                # 插件目录（热加载）
│   ├── wordlib.py          # 词库插件
│   ├── marry.py            # 结婚插件
│   ├── pseudo_persona.py   # 伪人插件
│   └── video_parser.py     # 视频解析插件
├── utils/                  # SDK 工具库
│   ├── api.py              # 消息发送 / HTTP API
│   ├── config.py           # 配置读取
│   ├── ws.py               # WebSocket 全局引用
│   ├── plugin_toggle.py    # 分群开关 + 插件元数据
│   └── command_table.py    # 命令表生成
├── templates/              # NapCat 配置模板
├── web/                    # Web 管理面板（Flask, 8080）
├── data/                   # 运行数据（gitignored）
├── README.md
├── VARIABLES.md            # 变量参考
└── CLAUDE.md               # 开发指引
```
