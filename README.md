# NapCat WordLib Bot

📦 基于 NapCat 的 QQ 机器人框架 + 一键部署脚本 | [v1.1.0 发布说明](https://github.com/Bdlxx/NapCat-WordLibBot/releases/tag/v1.1.0)

```bash
# 一键部署（Ubuntu/Debian/CentOS）
bash <(curl -s https://raw.githubusercontent.com/Bdlxx/NapCat-WordLibBot/master/install.sh)
```

---

## 🚀 快速开始：创建一个新实例（教程）

下面是从零开始部署一个机器人实例的完整流程。每一步做什么、为什么要做，都写清楚了。

### 第 0 步：准备环境（一次性）

在一台 Linux 服务器（Ubuntu/Debian/CentOS 均可）上安装：

| 依赖 | 用途 | 检查命令 |
|---|---|---|
| **Docker** | 运行 NapCat（QQ 客户端）容器 | `docker --version` |
| **Python 3.10+** | 运行机器人主程序 | `python3 --version` |
| **Git** | 拉取项目与插件 | `git --version` |

> 首次使用安装脚本时会自动检查这些依赖。

### 第 1 步：运行安装脚本

```bash
bash <(curl -s https://raw.githubusercontent.com/Bdlxx/NapCat-WordLibBot/master/install.sh)
```

脚本会显示交互式菜单，**并自动把自身保存到 `~/napbot/install.sh`**——之后在任意目录执行 `napbot` 即可进入同样的管理菜单。

### 第 2 步：部署新实例（主菜单选 1「📦 部署新实例」）

输入机器人 QQ 号（如 `123456789`）作为实例标识。脚本会自动完成 4 件事：

1. **克隆项目** → 创建实例目录 `<脚本目录>/instances/<QQ>/`（以 QQ 号命名，多实例互不干扰）
2. **拉取插件** → 从 [插件仓库](https://github.com/Bdlxx/NapCat-WordLibBot-Plugins) 自动安装全部插件到 `plugins/`
3. **配置向导** → 询问以下信息并自动写入 `config.json`：
   - **机器人昵称**（如：小助手）
   - **主人 QQ**（必填，拥有全部管理权限，多个用逗号分隔：`10001,10002`）
4. **创建容器** → 生成 NapCat 配置（端口/Token 自动分配）并启动 `napcat_<QQ>` 容器（网络模式可选：Host 直通 / Bridge 端口映射）

### 第 3 步：扫码登录 QQ

1. 主菜单选 2「🗂 实例管理」→ 选择你的实例
2. 选「📱 查看二维码」→ 用**手机 QQ** 扫码（二维码约 2-3 分钟有效，过期重新获取）
3. 等待容器日志出现登录成功提示

> 这一步让 NapCat 容器以你的机器人 QQ 登录，之后才能收发消息。

### 第 4 步：检查机器人配置（一般无需修改）

实例目录下的 `instances/<QQ>/config.json` 是机器人主配置：

```json
{
  "BOT_NAME": "我的机器人",          // 机器人昵称（显示用）
  "BOT_QQ": 123456789,               // 机器人 QQ（部署时已填）
  "MASTER_QQ": [10001],              // 主人 QQ（可多个，拥有全部管理权限）
  "NAPCAT_HTTP": "http://127.0.0.1:3000",  // NapCat HTTP 地址（脚本已自动写入）
  "WS_URL": "ws://127.0.0.1:3001/?access_token=xxx",  // WebSocket 地址（脚本已自动写入）
  "ACCESS_TOKEN": "xxx"              // NapCat 访问令牌（脚本已自动写入）
}
```

> 端口、Token、WS 地址、机器人昵称、主人 QQ 都在部署时由脚本自动写入 `config.json` 了，
> **一般无需手动修改**；如需增删主人 QQ，直接编辑此文件后重启 Bot 即可。

### 第 5 步：启动 Bot

回到实例管理菜单 → 「🤖 Bot 管理」→ 启动。观察日志出现：

```
WebSocket 连接成功，等待事件...
✓ 词库插件 v1.0.0 — ...
```

即表示机器人已正常运行（断线会自动重连）。

### 第 6 步：把机器人拉进群，开启插件

1. 用 QQ 把机器人拉进你的群
2. 在群里发送**开启命令**启用插件（仅主人 QQ 有效）：

| 插件 | 开启命令 | 说明 |
|---|---|---|
| 词库 | `开启词库` | 关键词回复、签到、自定义昵称 |
| 结婚 | `开启结婚` | 群内结婚/离婚系统 |
| 视频解析 | `开启视频解析` | 视频链接去水印 |
| JM下载 | `开启jm下载` | 禁漫本子下载转 PDF |

> 所有插件在每个群默认关闭，需主人发送对应命令开启（私聊发送 = 全局开关）。

### 第 7 步：Web 管理面板（可选）

主菜单选 3「🔗 后续设置」可配置 Web 面板：

- 设置访问密码：`bash set_password.sh 面板名 密码`
- 启动面板：`python web/api.py` → 访问 `http://<服务器IP>:8080`
- 面板功能：仪表盘、Bot 启停、扫码、插件配置、群组开关矩阵、日志

### 日常维护

| 操作 | 方法 |
|---|---|
| **更新插件** | 实例管理 → 「🔌 更新插件」（从插件仓库拉取最新） |
| **更新项目** | 实例管理 → 重新部署（自动 `git pull`） |
| **重启 Bot** | 群内发「重启」（主人），或实例管理 → Bot 管理 |
| **新增实例** | 重复第 2~5 步，每个 QQ 号一个独立实例 |

---

## 📋 目录

- [🚀 快速开始：创建新实例教程](#-快速开始创建一个新实例教程)
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

为每个 QQ 号创建完全独立的运行环境。输入 QQ 号作为标识，自动创建独立容器 `napcat_{QQ}` 和项目目录 `instances/{QQ}`（位于脚本目录下，以 QQ 号命名）。

### 实例管理

扫描所有已部署实例，支持启停容器、扫码登录、Bot 管理、日志查看、**更新插件**（从插件仓库拉取最新插件）、卸载。

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
python web/api.py --bot-dir instances/123456 --bot-name Bot --bot-qq 123456789
```

### 安全

- MD5 密码存储，登录限流（5 次失败冻结 15 分钟）
- CSRF 防护，会话 24 小时过期
- 密码管理：`bash set_password.sh <名称> <密码>`

---

## 🔌 插件开发 (SDK)

框架采用**动态加载**插件架构：主程序启动时扫描 `plugins/` 目录，凡导出 `handle()` 函数的
`.py` 文件都会自动加载（无需手动注册，Web 面板同样自动识别）。

> 插件已拆分到独立仓库 [NapCat-WordLibBot-Plugins](https://github.com/Bdlxx/NapCat-WordLibBot-Plugins)，
> `install.sh` 部署/更新实例时自动从该仓库拉取插件到 `plugins/` 目录。本仓库仅内置核心词库插件。

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

## 📖 插件

### 内置插件：词库 (wordlib)

关键词匹配回复、签到好感度、自定义昵称、点赞、转码。（随主仓库发布）

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

### 插件仓库插件（install.sh 自动安装）

以下插件由 [NapCat-WordLibBot-Plugins](https://github.com/Bdlxx/NapCat-WordLibBot-Plugins) 提供，
部署实例时 `install.sh` 自动拉取；更新用「实例管理 → 更新插件」：

| 插件 | 功能 |
|------|------|
| **结婚插件** (marry) | 群内每日结婚/离婚系统，支持成功率和冷却配置 |
| **JM下载** (jm_downloader) | `jm <车号>` 下载禁漫本子并合并为 PDF 分享；`jm详情 <车号>` 查看元信息；自动更新 jmcomic 库（配合 `jm_worker.py` 子进程） |
| **伪人插件** (pseudo_persona) | AI 对话回复，支持 GLM 和 Gemini 双模型切换 |
| **视频解析** (video_parser) | 自动检测群内视频链接并解析去水印，支持抖音、哔哩哔哩、快手、小红书、TikTok |

> 新插件开发完成后 push 到插件仓库，即可通过「更新插件」分发到所有实例。

---

## 📁 项目结构

```
├── install.sh              # 一键安装管理脚本（含插件仓库拉取）
├── set_password.sh         # Web面板密码管理工具
├── watchdog.py             # 看门狗进程（监听「重启」命令）
├── main.py                 # SDK 框架入口
├── config.json             # 机器人配置（gitignored）
├── plugins/                # 插件目录（动态加载）
│   ├── wordlib.py          # 词库插件（内置）
│   └── README.md           # 插件说明（其余插件由 install.sh 从插件仓库拉取）
├── utils/                  # SDK 工具库
│   ├── api.py              # 消息发送 / 合并转发 / HTTP API
│   ├── config.py           # 配置读取
│   ├── ws.py               # WebSocket 全局引用
│   ├── http_client.py      # HTTP 客户端封装
│   ├── plugin_toggle.py    # 分群开关 + 插件元数据（自动扫描插件目录）
│   └── command_table.py    # 命令表生成
├── templates/              # NapCat 配置模板
├── web/                    # Web 管理面板（Flask, 8080）
├── data/                   # 运行数据（gitignored）
├── README.md
├── VARIABLES.md            # 变量参考
└── CLAUDE.md               # 开发指引
```
