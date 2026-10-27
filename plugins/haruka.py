# -*- coding: utf-8 -*-
"""
B站推送插件（HarukaBot 移植版）
=================================
把 [HarukaBot](https://github.com/SK-415/HarukaBot)（NoneBot2 插件，B站动态/直播推送）
的核心能力移植到本框架：**不引 nonebot / tortoise / playwright**，只依赖 `requests`，
数据落 JSON（与其它插件一致），配置项由 `__config_schema__` 自声明给 Web 面板。

功能
----
- 关注 / 取关 / 关注列表（群与私聊各自独立）
- 直播开播推送（标题、分区、封面、链接，可 @全体）与下播提醒（含时长）
- 动态推送（正文、封面、链接），可单独开启/关闭
- 已开播列表、本群权限开关（默认仅管理员可用）、机器人退群自动清理订阅
- 后台轮询线程（单线程循环，间隔可配）；配置改完即时生效（无需重启）

与 HarukaBot 的差异（都是本框架/部署环境的约束，不是偷懒）
--------------------------------------------------------
1. **不走 playwright 截图**：HarukaBot 把动态渲染成图片再发，依赖 Chromium；
   这里改为「文字摘要 + 封面图 + 链接」，部署轻、失败面小。
2. **数据源自动降级**：完整动态接口 `web-dynamic/v1/feed/space` 需要 wbi 签名且对
   机房/海外 IP 极容易 412；被风控时自动改用 `web-dynamic/v1/opus/feed/space`
   （图文动态，无需签名）。降级状态见「B站推送状态」。
3. **没有频道/QQ 频道（guild）**：本框架只有群聊与私聊。
4. **订阅数据存 JSON**，没有 tortoise/SQLite。

数据文件（都在实例的 `data/` 下）
--------------------------------
- `haruka_config.json`：可配置项（面板表单由 `__config_schema__` 生成）
- `haruka_data.json`：订阅关系 / UP 名称 / 群权限 / 推送状态（插件自己维护）

指令（触发词都可以在面板里改；==改完即生效，无需重启==）
--------------------------------------------------------
    关注 <UID|空间链接|UP名>   取关 <UID>            关注列表
    开启动态/关闭动态 <UID>     开启直播/关闭直播 <UID>
    开启全体/关闭全体 <UID>     已开播
    开启权限 / 关闭权限          B站帮助 / B站推送状态 / B站推送测试
"""

import copy
import hashlib
import json
import os
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.api import http_get, send_message
from utils.command_registry import CommandRegistry
from utils.config import get_bot_name, get_bot_qq, get_master_qq
from utils.plugin_toggle import is_enabled as _pt_enabled, set_enabled as _pt_set

# ============================================================================
# SDK 元数据
# ============================================================================
__plugin_name_cn__ = "B站推送"
__plugin_name_en__ = "haruka"
__plugin_version__ = "1.0.0"
__plugin_desc__ = "B站 UP 主动态/开播/下播推送到群，支持关注管理、@全体、权限开关"
__plugin_author__ = "NapCat-WordLibBot（移植自 HarukaBot）"

# ============================================================================
# 可配置项声明（面板据此**自动生成表单**，见 web/config_schema.py）
#
#   · 字段名 → 控件类型；path 是值在配置文件里的位置（push.live / poll.live_interval）
#   · label/help/group 是面板上直接显示的中文；advanced 折叠进「高级选项」
#   · default 必须与本文件 `_DEFAULTS` 一致（有单测盯着，改一处就得改两处）
# ============================================================================
__config_schema__ = {
    # ---------------- 开关 ----------------
    "enabled": {
        "type": "bool", "label": "启用推送", "group": "开关",
        "path": "enabled", "default": True,
        "help": "总开关；关闭后既不轮询也不推送，指令仍可用",
    },
    "push_live": {
        "type": "bool", "label": "开播推送", "group": "开关",
        "path": "push.live", "default": True, "help": "UP 开播时推送到订阅位置",
    },
    "push_live_off": {
        "type": "bool", "label": "下播提醒", "group": "开关",
        "path": "push.live_off", "default": True, "help": "下播时推送，并给出本次直播时长",
    },
    "push_dynamic": {
        "type": "bool", "label": "动态推送", "group": "开关",
        "path": "push.dynamic", "default": True, "help": "UP 发动态时推送正文+封面+链接",
    },
    "push_cover": {
        "type": "bool", "label": "附带封面图", "group": "开关",
        "path": "push.cover", "default": True, "help": "把封面/配图以图片消息一起发出（失败不影响文字）",
    },
    "push_live_at": {
        "type": "bool", "label": "开播可 @全体", "group": "开关",
        "path": "push.live_at", "default": False,
        "help": "为某个 UP 单独开启全体后，开播时才会真的 @全体；关=永远不 @",
    },
    "push_dynamic_at": {
        "type": "bool", "label": "动态也 @全体", "group": "开关",
        "path": "push.dynamic_at", "default": False,
        "help": "默认只有开播会 @全体；打开后动态推送也 @（同样要单独开启全体）",
    },

    "require_at": {
        "type": "bool", "label": "群内指令需要 @机器人", "group": "开关",
        "path": "require_at", "default": False,
        "help": "默认关：管理员直接发「关注 123」即可。打开后必须 @机器人（或消息以机器人名开头），"
                "非管理员不 @ 的消息原样交给其它插件，不会被本插件吃掉",
    },

    # ---------------- 轮询 ----------------
    "live_interval": {
        "type": "number", "label": "直播轮询间隔", "group": "轮询", "unit": "秒",
        "path": "poll.live_interval", "default": 60, "min": 30, "max": 600, "step": 10,
        "help": "所有直播订阅合并成一次请求（批量接口），间隔太小容易被限流",
    },
    "dynamic_interval": {
        "type": "number", "label": "动态轮询间隔", "group": "轮询", "unit": "秒",
        "path": "poll.dynamic_interval", "default": 180, "min": 60, "max": 3600, "step": 30,
        "help": "每个 UP 一次请求；订阅多时建议调大，避免 412 风控",
    },
    "max_new_per_poll": {
        "type": "number", "label": "单次最多推几条动态", "group": "轮询", "unit": "条",
        "path": "poll.max_new_per_poll", "default": 3, "min": 1, "max": 10,
        "help": "积压（如机器人停机）时避免一次刷屏，剩下的下轮继续推",
    },
    "text_max_len": {
        "type": "number", "label": "动态正文截断", "group": "轮询", "unit": "字",
        "path": "poll.text_max_len", "default": 200, "min": 0, "max": 1000, "step": 50,
        "help": "0=不截断；太长会被 QQ 折叠",
    },

    # ---------------- 网络 ----------------
    "cookie": {
        "type": "password", "label": "B站 Cookie", "group": "网络",
        "path": "net.cookie", "default": "",
        "help": "可选。填 SESSDATA=...; bili_jct=... 这类浏览器 Cookie 可显著降低风控概率",
    },
    "proxy": {
        "type": "text", "label": "代理地址", "group": "网络",
        "path": "net.proxy", "default": "",
        "placeholder": "http://127.0.0.1:7890",
        "help": "可选。海外/机房 IP 拿不到完整动态时，填一个国内代理；留空=直连",
    },
    "timeout": {
        "type": "number", "label": "请求超时", "group": "网络", "unit": "秒",
        "path": "net.timeout", "default": 15, "min": 5, "max": 60, "step": 5,
    },

    # ---------------- 推送模板 ----------------
    "tpl_live_on": {
        "type": "textarea", "label": "开播文案", "group": "推送模板", "rows": 3,
        "path": "templates.live_on",
        "default": "{name} 开播啦！\n分区：{area}\n标题：{title}\n{url}",
        "help": "占位符：{name} UP名 · {uid} UID · {area} 分区 · {title} 直播间标题 · {url} 直播间地址",
    },
    "tpl_live_off": {
        "type": "textarea", "label": "下播文案", "group": "推送模板", "rows": 2,
        "path": "templates.live_off",
        "default": "{name} 下播了。{duration}",
        "help": "占位符：{name} · {uid} · {duration} 本次直播时长（可能是空串） · {url}",
    },
    "tpl_dynamic": {
        "type": "textarea", "label": "动态文案", "group": "推送模板", "rows": 4,
        "path": "templates.dynamic",
        "default": "{name} {kind}：\n{text}\n{url}",
        "help": "占位符：{name} · {uid} · {kind} 动态类型（如「发布了新图文动态」） · {text} 正文 · {url} 动态地址",
    },

    # ---------------- 指令触发词 ----------------
    "cmd_sub": {"type": "text", "label": "关注", "group": "指令", "path": "commands.sub", "default": "关注",
                "help": "前缀匹配，后面跟 UID/空间链接/UP名"},
    "cmd_unsub": {"type": "text", "label": "取关", "group": "指令", "path": "commands.unsub", "default": "取关",
                  "help": "前缀匹配，后面跟 UID"},
    "cmd_list": {"type": "text", "label": "关注列表", "group": "指令", "path": "commands.list", "default": "关注列表"},
    "cmd_dyn_on": {"type": "text", "label": "开启动态", "group": "指令", "path": "commands.dyn_on", "default": "开启动态"},
    "cmd_dyn_off": {"type": "text", "label": "关闭动态", "group": "指令", "path": "commands.dyn_off", "default": "关闭动态"},
    "cmd_live_on": {"type": "text", "label": "开启直播", "group": "指令", "path": "commands.live_on", "default": "开启直播"},
    "cmd_live_off": {"type": "text", "label": "关闭直播", "group": "指令", "path": "commands.live_off", "default": "关闭直播"},
    "cmd_at_on": {"type": "text", "label": "开启全体", "group": "指令", "path": "commands.at_on", "default": "开启全体"},
    "cmd_at_off": {"type": "text", "label": "关闭全体", "group": "指令", "path": "commands.at_off", "default": "关闭全体"},
    "cmd_live_now": {"type": "text", "label": "已开播", "group": "指令", "path": "commands.live_now", "default": "已开播"},
    "cmd_perm_on": {"type": "text", "label": "开启权限", "group": "指令", "path": "commands.perm_on", "default": "开启权限"},
    "cmd_perm_off": {"type": "text", "label": "关闭权限", "group": "指令", "path": "commands.perm_off", "default": "关闭权限"},
    "cmd_help": {"type": "text", "label": "帮助", "group": "指令", "path": "commands.help", "default": "B站帮助"},
    "cmd_status": {"type": "text", "label": "运行状态", "group": "指令", "path": "commands.status", "default": "B站推送状态"},
    "cmd_test": {"type": "text", "label": "测试推送", "group": "指令", "path": "commands.test", "default": "B站推送测试"},
    "cmd_enable": {"type": "text", "label": "开启推送", "group": "指令", "path": "commands.enable", "default": "开启B站推送",
                   "help": "群内=开本群（仅主人），私聊=开全局（仅主人）"},
    "cmd_disable": {"type": "text", "label": "关闭推送", "group": "指令", "path": "commands.disable", "default": "关闭B站推送",
                    "help": "群内=关本群（仅主人），私聊=关全局（仅主人）"},

    # ---------------- 回复文案 ----------------
    "reply_usage": {"type": "text", "label": "用法提示", "group": "回复文案", "path": "replies.usage",
                    "default": "用法：{cmd} UID（也可以换成空间链接或 UP 名）", "help": "占位符：{cmd} 触发词"},
    "reply_sub_ok": {"type": "text", "label": "关注成功", "group": "回复文案", "path": "replies.sub_ok",
                     "default": "已关注 {name}（{uid}），当前共关注 {count} 个 UP",
                     "help": "占位符：{name} {uid} {count}"},
    "reply_already": {"type": "text", "label": "已关注过", "group": "回复文案", "path": "replies.already",
                      "default": "已经关注过 {name}（{uid}）了", "help": "占位符：{name} {uid}"},
    "reply_unsub_ok": {"type": "text", "label": "取关成功", "group": "回复文案", "path": "replies.unsub_ok",
                       "default": "已取关 {name}（{uid}）", "help": "占位符：{name} {uid}"},
    "reply_not_sub": {"type": "text", "label": "未关注", "group": "回复文案", "path": "replies.not_sub",
                      "default": "没有关注 {uid}，先发「{cmd} {uid}」", "help": "占位符：{uid} {cmd}"},
    "reply_not_found": {"type": "text", "label": "找不到 UP", "group": "回复文案", "path": "replies.not_found",
                        "default": "没有找到这个 UP：{arg}", "help": "占位符：{arg} 用户输入"},
    "reply_no_perm": {"type": "text", "label": "权限不足", "group": "回复文案", "path": "replies.no_perm",
                      "default": "权限不足：只有管理员和主人才能操作（群主可发「关闭权限」让所有人可用）"},
    "reply_group_only": {"type": "text", "label": "仅限群聊", "group": "回复文案", "path": "replies.group_only",
                         "default": "这个指令只能在群里用"},
    "reply_list_empty": {"type": "text", "label": "关注列表为空", "group": "回复文案", "path": "replies.list_empty",
                         "default": "还没有关注任何 UP。发送「关注 UID」即可添加"},
    "reply_list_title": {"type": "text", "label": "关注列表标题", "group": "回复文案", "path": "replies.list_title",
                         "default": "【关注列表】共 {count} 个（群与私聊各自独立）", "help": "占位符：{count}"},

    # ---------------- 元数据（只读） ----------------
    "command_labels": {
        "type": "json", "label": "指令标签映射", "group": "其它", "advanced": True,
        "readonly": True, "rows": 6, "path": "command_labels", "default": {},
        "help": "插件启动时自动写入的「触发词 → 指令中文名」映射，供面板显示可读名称；只读",
    },
}

# ============================================================================
# 路径与默认配置
# ============================================================================
PLUGIN = "B站推送"

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 数据目录可注入（单测/排障时指到临时目录，别碰线上实例的 data/）
_DATA_DIR = os.environ.get("HARUKA_DATA_DIR") or os.path.join(_ROOT, "data")
_CFG_FILE = os.path.join(_DATA_DIR, "haruka_config.json")
_DATA_FILE = os.path.join(_DATA_DIR, "haruka_data.json")

_DEFAULTS = {
    "enabled": True,
    "require_at": False,
    "push": {
        "live": True,
        "live_off": True,
        "dynamic": True,
        "cover": True,
        "live_at": False,
        "dynamic_at": False,
    },
    "poll": {
        "live_interval": 60,
        "dynamic_interval": 180,
        "max_new_per_poll": 3,
        "text_max_len": 200,
    },
    "net": {
        "cookie": "",
        "proxy": "",
        "timeout": 15,
    },
    "templates": {
        "live_on": "{name} 开播啦！\n分区：{area}\n标题：{title}\n{url}",
        "live_off": "{name} 下播了。{duration}",
        "dynamic": "{name} {kind}：\n{text}\n{url}",
    },
    "commands": {
        "sub": "关注", "unsub": "取关", "list": "关注列表",
        "dyn_on": "开启动态", "dyn_off": "关闭动态",
        "live_on": "开启直播", "live_off": "关闭直播",
        "at_on": "开启全体", "at_off": "关闭全体",
        "live_now": "已开播",
        "perm_on": "开启权限", "perm_off": "关闭权限",
        "help": "B站帮助", "status": "B站推送状态", "test": "B站推送测试",
        "enable": "开启B站推送", "disable": "关闭B站推送",
    },
    "replies": {
        "usage": "用法：{cmd} UID（也可以换成空间链接或 UP 名）",
        "sub_ok": "已关注 {name}（{uid}），当前共关注 {count} 个 UP",
        "already": "已经关注过 {name}（{uid}）了",
        "unsub_ok": "已取关 {name}（{uid}）",
        "not_sub": "没有关注 {uid}，先发「{cmd} {uid}」",
        "not_found": "没有找到这个 UP：{arg}",
        "no_perm": "权限不足：只有管理员和主人才能操作（群主可发「关闭权限」让所有人可用）",
        "group_only": "这个指令只能在群里用",
        "list_empty": "还没有关注任何 UP。发送「关注 UID」即可添加",
        "list_title": "【关注列表】共 {count} 个（群与私聊各自独立）",
    },
    "command_labels": {},
}

# ============================================================================
# 通用小工具
# ============================================================================


def _plog(level, msg):
    """分级日志（plugin_log 失败时兜底 print；别递归调自己）"""
    try:
        from utils.log import plugin_log
        plugin_log(PLUGIN, level, msg)
    except Exception:
        print(f"[{PLUGIN}] {msg}")


def _deep_merge(base, over):
    """递归合并：over 覆盖 base，缺失的键保留 base（配置项将来新增也有值）

    注意 base 必须**深拷贝**：浅拷贝会让 `_CFG` 与 `_DEFAULTS` 共享嵌套字典，
    运行期改一个配置项就把默认值也改了（广播给下一次重载）。
    """
    out = copy.deepcopy(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def cfgv(path, default=None):
    """读配置（点号路径），如 cfgv("poll.live_interval", 60)"""
    node = _CFG
    for key in str(path).split("."):
        if not isinstance(node, dict) or key not in node:
            return default
        node = node[key]
    return default if node is None else node


def _cfg_int(path, default, lo=None, hi=None):
    try:
        value = int(float(cfgv(path, default)))
    except (TypeError, ValueError):
        value = int(default)
    if lo is not None and value < lo:
        value = lo
    if hi is not None and value > hi:
        value = hi
    return value


def _is_master(user_id):
    try:
        masters = get_master_qq() or []
    except Exception:
        masters = []
    if not isinstance(masters, (list, tuple, set)):
        masters = [masters]
    return str(user_id) in {str(m) for m in masters}


# ============================================================================
# 配置加载 / 保存
# ============================================================================
_CFG = {}
_CFG_LOCK = threading.RLock()


def _load_cfg():
    """读磁盘配置并与默认值合并（磁盘上缺的项用默认值，不写回）"""
    global _CFG
    disk = {}
    try:
        if os.path.exists(_CFG_FILE):
            with open(_CFG_FILE, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                disk = loaded
    except Exception as exc:  # 配置文件坏了不该让插件起不来
        _plog("warn", f"读取配置失败，使用默认值：{exc}")
    with _CFG_LOCK:
        _CFG = _deep_merge(_DEFAULTS, disk)
    return _CFG


def _save_cfg():
    """原子写回配置（tmp + os.replace，避免面板/插件同时写坏文件）"""
    with _CFG_LOCK:
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            tmp = _CFG_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(_CFG, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, _CFG_FILE)
        except Exception as exc:
            _plog("error", f"保存配置失败：{exc}")


# ============================================================================
# 订阅 / 状态存储（JSON，原子写）
# ============================================================================
def _target_key(target):
    return f"{target[0]}:{target[1]}"


def _parse_target_key(key):
    kind, _, ident = str(key).partition(":")
    return kind or "group", ident


class _Store:
    """订阅与推送状态。

    结构（haruka_data.json）::

        {
          "version": 1,
          "subs": {"group:123": {"546195": {"name": "...", "live": true,
                                            "dynamic": true, "at": false, "since": 0}}},
          "users": {"546195": "老番茄"},
          "groups": {"123": {"admin": true}},
          "state": {"dynamic_last": {"546195": "1232..."},
                    "live": {"546195": {"status": 1, "since": 0, "title": "", "ts": 0}}}
        }
    """

    def __init__(self, path):
        self._path = path
        self._lock = threading.RLock()
        self._data = self._blank()

    @staticmethod
    def _blank():
        return {
            "version": 1,
            "subs": {},
            "users": {},
            "groups": {},
            "state": {"dynamic_last": {}, "live": {}},
        }

    # ---------- 读写 ----------
    def load(self):
        with self._lock:
            try:
                with open(self._path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                if isinstance(raw, dict):
                    self._data = self._normalize(raw)
            except FileNotFoundError:
                pass
            except Exception as exc:
                _plog("warn", f"读取订阅数据失败（按空数据处理）：{exc}")
            return self._data

    def _normalize(self, raw):
        data = self._blank()
        for key in ("version", "subs", "users", "groups", "state"):
            if isinstance(raw.get(key), type(data[key])):
                data[key] = raw[key]
        data["state"].setdefault("dynamic_last", {})
        data["state"].setdefault("live", {})
        for key in list(data["subs"]):
            if not isinstance(data["subs"][key], dict):
                data["subs"][key] = {}
        return data

    def save(self):
        with self._lock:
            try:
                os.makedirs(os.path.dirname(self._path), exist_ok=True)
                tmp = self._path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(self._data, fh, ensure_ascii=False, indent=2)
                os.replace(tmp, self._path)
            except Exception as exc:
                _plog("error", f"保存订阅数据失败：{exc}")

    # ---------- 订阅 ----------
    def subs_of(self, target, create=False):
        key = _target_key(target)
        with self._lock:
            if create:
                return self._data["subs"].setdefault(key, {})
            return self._data["subs"].get(key, {})

    def all_targets(self):
        with self._lock:
            return {_parse_target_key(k): v for k, v in self._data["subs"].items() if v}

    def count_uids(self):
        with self._lock:
            return len({uid for subs in self._data["subs"].values() for uid in subs})

    def has_sub(self, target, uid):
        return str(uid) in self.subs_of(target)

    def add_sub(self, target, uid, name, live=True, dynamic=True, at=False):
        uid = str(uid)
        with self._lock:
            subs = self.subs_of(target, create=True)
            subs[uid] = {
                "name": name or uid,
                "live": bool(live),
                "dynamic": bool(dynamic),
                "at": bool(at),
                "since": int(time.time()),
            }
            if name:
                self._data["users"][uid] = name
            self.save()
            return True

    def remove_sub(self, target, uid):
        uid = str(uid)
        with self._lock:
            subs = self.subs_of(target)
            if uid not in subs:
                return False
            subs.pop(uid, None)
            self.save()
            return True

    def set_flag(self, target, uid, flag, value):
        uid = str(uid)
        with self._lock:
            subs = self.subs_of(target)
            if uid not in subs:
                return False
            subs[uid][flag] = bool(value)
            self.save()
            return True

    def name(self, uid):
        with self._lock:
            return str(self._data["users"].get(str(uid)) or "")

    def set_name(self, uid, name):
        with self._lock:
            if name and self._data["users"].get(str(uid)) != name:
                self._data["users"][str(uid)] = name
                return True
            return False

    def uids_for(self, kind):
        """需要某种推送的 UID 列表（去重、稳定顺序）"""
        kind = "live" if kind == "live" else "dynamic"
        with self._lock:
            uids = {uid for subs in self._data["subs"].values()
                    for uid, sub in subs.items() if sub.get(kind)}
        return sorted(uids, key=lambda x: int(x) if str(x).isdigit() else 0)

    def targets_for(self, uid, kind):
        """返回 [(target, sub), ...]：哪些位置要收这个 UP 的这类推送"""
        uid = str(uid)
        result = []
        with self._lock:
            for key, subs in self._data["subs"].items():
                sub = subs.get(uid)
                if isinstance(sub, dict) and sub.get(kind):
                    result.append((_parse_target_key(key), sub))
        return result

    def drop_group(self, gid):
        """机器人退群/被踢：清掉该群订阅，返回清理条数"""
        key = f"group:{gid}"
        with self._lock:
            subs = self._data["subs"].pop(key, None)
            self._data["groups"].pop(str(gid), None)
            if subs:
                self.save()
                return len(subs)
            return 0

    # ---------- 群权限 ----------
    def group_perm(self, gid):
        """该群是否启用「仅管理员」（默认开启，与 HarukaBot 一致）"""
        with self._lock:
            info = self._data["groups"].get(str(gid)) or {}
            return bool(info.get("admin", True))

    def set_group_perm(self, gid, enabled):
        with self._lock:
            self._data["groups"].setdefault(str(gid), {})["admin"] = bool(enabled)
            self.save()

    # ---------- 推送状态 ----------
    def dynamic_last(self, uid):
        """上次推到的动态 id；None=还没建立基线（下次轮询只记基线不推送）"""
        with self._lock:
            value = self._data["state"]["dynamic_last"].get(str(uid))
        if value in (None, ""):
            return None
        return str(value)

    def set_dynamic_last(self, uid, value):
        with self._lock:
            self._data["state"]["dynamic_last"][str(uid)] = str(value)
            self.save()

    def live_state(self, uid):
        with self._lock:
            state = self._data["state"]["live"].get(str(uid))
        return dict(state) if isinstance(state, dict) else None

    def set_live_state(self, uid, state):
        """状态没变就不写盘（每轮都写会无谓磨损磁盘）"""
        with self._lock:
            uid = str(uid)
            old = self._data["state"]["live"].get(uid)
            if isinstance(old, dict) and old == state:
                return False
            self._data["state"]["live"][uid] = dict(state)
            self.save()
            return True


_store = _Store(_DATA_FILE)

# ============================================================================
# B站 HTTP 客户端
# ============================================================================
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

_BLOCK_CODES = {-412, -352, -799, -509}
# -412 请求被拦截；-352 风控校验失败；-799 请求过于频繁；-509 超出限制

# wbi 签名用的混淆表（B站前端固定值；nav 接口拿 img_key/sub_key 后重排前 32 位）
_WBI_MIXIN_TABLE = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40, 61,
    26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36,
    20, 34, 44, 52,
]

# 完整动态接口被风控后的冷却时间（秒）：冷却期内直接用 opus 接口，不再白打请求
_FULL_COOLDOWN = 1800


class BiliError(Exception):
    """B站接口返回非 0 code（业务错误）"""

    def __init__(self, code, message="", url=""):
        self.code = code
        self.message = str(message or "")
        self.url = url
        super().__init__(f"code={code} {self.message}".strip())


class BiliBlocked(BiliError):
    """被风控/限流（code 或 HTTP 412）：应当退避，而不是当普通错误重试"""


def wbi_mixin_key(img_key, sub_key):
    """把 nav 给的 img_key/sub_key 重排成 32 位 mixin key"""
    raw = str(img_key or "") + str(sub_key or "")
    return "".join(raw[i] for i in _WBI_MIXIN_TABLE if i < len(raw))[:32]


def wbi_sign(params, img_key, sub_key, wts=None):
    """wbi 签名：返回带 wts / w_rid 的新参数字典（纯函数，便于测试）"""
    signed = {k: v for k, v in (params or {}).items() if v is not None}
    signed["wts"] = int(wts if wts is not None else time.time())
    # 值里的 !'()* 必须剔除，否则签名对不上
    signed = {k: "".join(ch for ch in str(v) if ch not in "!'()*")
              for k, v in sorted(signed.items())}
    query = urlencode(signed)
    signed["w_rid"] = hashlib.md5((query + wbi_mixin_key(img_key, sub_key)).encode()).hexdigest()
    return signed


class _BiliClient:
    """最小可用的 B站接口客户端（只用 requests）

    - cookie / 代理 / 超时 实时从配置读（面板改完即时生效）
    - 自动补 buvid3/buvid4（缺它更容易被风控）
    - 完整动态接口需要 wbi 签名；被风控时进入冷却，调用方自动降级到 opus
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._session = None
        self._cookie_sig = None
        self._wbi = (0.0, "", "")
        self._buvid_ts = 0.0
        self.full_skip_until = 0.0
        self.full_last_error = ""

    # ---------- 基础 ----------
    def _timeout(self):
        return _cfg_int("net.timeout", 15, 5, 60)

    def _proxies(self):
        proxy = str(cfgv("net.proxy", "") or "").strip()
        return {"http": proxy, "https": proxy} if proxy else None

    def _headers(self, referer=None):
        return {
            "User-Agent": _UA,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Origin": "https://space.bilibili.com",
            "Referer": referer or "https://space.bilibili.com/",
        }

    def _sess(self):
        with self._lock:
            if self._session is None:
                self._session = requests.Session()
            self._apply_cookie(self._session)
            return self._session

    def _apply_cookie(self, session):
        cookie = str(cfgv("net.cookie", "") or "").strip()
        if cookie != self._cookie_sig:
            # 配置里的 cookie 变了（含清空）：先丢掉旧 cookie，再按新值重设
            try:
                session.cookies.clear()
            except Exception:
                pass
            self._buvid_ts = 0.0
            self._cookie_sig = cookie
            for part in cookie.split(";"):
                part = part.strip()
                if "=" in part:
                    name, _, value = part.partition("=")
                    try:
                        session.cookies.set(name.strip(), value.strip(), domain=".bilibili.com")
                    except Exception:
                        pass
        # 没有 buvid3 就补一个（一小时最多补一次）
        if "buvid3" not in session.cookies and time.time() - self._buvid_ts > 3600:
            self._buvid_ts = time.time()
            try:
                resp = session.get(
                    "https://api.bilibili.com/x/frontend/finger/spi",
                    headers=self._headers(), timeout=8, proxies=self._proxies(),
                )
                data = (resp.json() or {}).get("data") or {}
                for name, value in (("buvid3", data.get("b_3")), ("buvid4", data.get("b_4"))):
                    if value:
                        session.cookies.set(name, str(value), domain=".bilibili.com")
            except Exception:
                pass

    def _raw(self, method, url, params=None, json_body=None, referer=None):
        """发请求并返回**整个** JSON（含 code）；HTTP 412 直接抛 BiliBlocked"""
        with self._lock:
            session = self._sess()
            try:
                resp = session.request(
                    method, url, params=params, json=json_body,
                    headers=self._headers(referer),
                    timeout=self._timeout(), proxies=self._proxies(),
                )
            except requests.RequestException as exc:
                raise BiliError(0, f"网络错误：{type(exc).__name__} {exc}", url)
            if resp.status_code == 412:
                raise BiliBlocked(412, "请求被 B 站风控（HTTP 412）", url)
            if resp.status_code != 200:
                raise BiliError(resp.status_code, f"HTTP {resp.status_code}", url)
            try:
                data = resp.json()
            except ValueError:
                raise BiliError(resp.status_code, "响应不是合法 JSON", url)
            if not isinstance(data, dict):
                raise BiliError(resp.status_code, "响应格式异常", url)
            return data

    def _request(self, method, url, params=None, json_body=None, sign=False, referer=None):
        """带业务码校验的请求：返回 data 字段"""
        if sign:
            img_key, sub_key = self._wbi_keys()
            params = wbi_sign(params or {}, img_key, sub_key)
        data = self._raw(method, url, params=params, json_body=json_body, referer=referer)
        code = data.get("code")
        if code in _BLOCK_CODES:
            raise BiliBlocked(code, str(data.get("message") or ""), url)
        if code not in (0, None):
            raise BiliError(code, str(data.get("message") or ""), url)
        return data.get("data")

    # ---------- wbi ----------
    def _wbi_keys(self):
        ts, img_key, sub_key = self._wbi
        if img_key and sub_key and time.time() - ts < 1800:
            return img_key, sub_key
        data = self._raw("GET", "https://api.bilibili.com/x/web-interface/nav",
                         referer="https://www.bilibili.com/")
        wbi = ((data or {}).get("data") or {}).get("wbi_img") or {}
        img_key = str(wbi.get("img_url") or "").rsplit("/", 1)[-1].split(".")[0]
        sub_key = str(wbi.get("sub_url") or "").rsplit("/", 1)[-1].split(".")[0]
        self._wbi = (time.time(), img_key, sub_key)
        return img_key, sub_key

    # ---------- 业务接口 ----------
    def resolve_b23(self, text):
        """b23.tv 短链 → 真实链接 → UID（失败返回空串）"""
        match = re.search(r"b23\.(?:tv|wtf)/([A-Za-z0-9]+)", str(text or ""))
        if not match:
            return ""
        with self._lock:
            session = self._sess()
            try:
                resp = session.get("https://b23.tv/" + match.group(1),
                                   allow_redirects=True, headers=self._headers(),
                                   timeout=self._timeout(), proxies=self._proxies())
                return extract_uid(str(resp.url))
            except Exception:
                return ""

    def get_card(self, uid):
        """用户名片：昵称 / 头像（对海外 IP 也基本可用）"""
        data = self._request("GET", "https://api.bilibili.com/x/web-interface/card",
                             {"mid": int(uid)})
        card = (data or {}).get("card") or {}
        return {"name": str(card.get("name") or ""), "face": str(card.get("face") or "")}

    def search_user(self, keyword):
        """按名字搜 UP（风控严格；失败时调用方会提示改用 UID）"""
        data = self._request("GET", "https://api.bilibili.com/x/web-interface/search/type",
                             {"search_type": "bili_user", "keyword": keyword})
        result = (data or {}).get("result") or []
        for item in result:
            if str(item.get("uname") or "") == keyword:
                return {"uid": str(item.get("mid")), "name": item.get("uname")}
        if result:
            return {"uid": str(result[0].get("mid")), "name": result[0].get("uname")}
        return None

    def live_status(self, uids):
        """批量查直播间状态：{uid(str): info}"""
        ids = [int(u) for u in uids if str(u).isdigit()]
        if not ids:
            return {}
        data = self._request(
            "POST", "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids",
            json_body={"uids": ids}, referer="https://live.bilibili.com/",
        )
        return data if isinstance(data, dict) else {}

    def dynamic_feed(self, uid):
        """完整动态（需要 wbi；海外/机房 IP 常被 412）"""
        now = time.time()
        if now < self.full_skip_until:
            raise BiliBlocked(0, "完整动态接口冷却中")
        try:
            data = self._request(
                "GET", "https://api.bilibili.com/x/polymer/web-dynamic/v1/feed/space",
                {"host_mid": int(uid), "features": "itemOpusStyle",
                 "timezone_offset": -480, "web_location": "333.1387"},
                sign=True, referer=f"https://space.bilibili.com/{uid}/dynamic",
            )
        except BiliBlocked as exc:
            self.full_skip_until = now + _FULL_COOLDOWN
            self.full_last_error = str(exc)
            _plog("warn", f"完整动态接口被风控（{exc}），{_FULL_COOLDOWN // 60} 分钟内改用图文接口")
            raise
        return (data or {}).get("items") or []

    def opus_feed(self, uid):
        """图文动态（无需签名，海外可用的降级数据源）"""
        data = self._request(
            "GET", "https://api.bilibili.com/x/polymer/web-dynamic/v1/opus/feed/space",
            {"host_mid": int(uid), "page": 1, "type": "all"},
            referer=f"https://space.bilibili.com/{uid}/dynamic",
        )
        return (data or {}).get("items") or []

    def health(self):
        """给「B站推送状态」用的一句话数据源健康度"""
        if time.time() < self.full_skip_until:
            mins = max(1, int((self.full_skip_until - time.time()) / 60))
            full = f"冷却中（约 {mins} 分钟）"
        else:
            full = "可用"
        return f"完整动态 {full}；图文动态 可用"


_client = _BiliClient()

# ============================================================================
# 动态/直播数据归一化（纯函数，便于单测）
# ============================================================================
_DYNAMIC_KINDS = {
    1: "转发了一条动态",
    2: "发布了新图文动态",
    4: "发布了新文字动态",
    8: "发布了新投稿",
    16: "发布了新短视频",
    64: "发布了新专栏",
    256: "发布了新音频",
    512: "发布了新动态",
    2048: "发布了新动态",
    4308: "开播了",
    "DYNAMIC_TYPE_FORWARD": "转发了一条动态",
    "DYNAMIC_TYPE_DRAW": "发布了新图文动态",
    "DYNAMIC_TYPE_WORD": "发布了新文字动态",
    "DYNAMIC_TYPE_AV": "发布了新投稿",
    "DYNAMIC_TYPE_ARTICLE": "发布了新专栏",
    "DYNAMIC_TYPE_MUSIC": "发布了新音频",
    "DYNAMIC_TYPE_PGC": "发布了新剧集",
    "DYNAMIC_TYPE_COURSES": "发布了新课程",
    "DYNAMIC_TYPE_LIVE": "开播了",
    "DYNAMIC_TYPE_LIVE_RCMD": "开播了",
}


def kind_text(dynamic_type):
    """把动态类型映射成一句中文（未知类型给通用文案）"""
    return _DYNAMIC_KINDS.get(dynamic_type, "发布了新动态")


def _first_pic_src(items):
    for item in items or []:
        if isinstance(item, dict):
            for key in ("src", "url"):
                value = item.get(key)
                if value:
                    return str(value)
    return ""


def normalize_dynamic_full(item):
    """完整动态接口的一条 item → 统一结构；无法识别返回 None"""
    if not isinstance(item, dict):
        return None
    dynamic_id = str(item.get("id_str") or item.get("id") or "")
    if not dynamic_id.isdigit():
        return None

    modules = item.get("modules") or {}
    author = modules.get("module_author") or {}
    dynamic = modules.get("module_dynamic") or {}
    text = str(((dynamic.get("desc") or {}).get("text") or "")).strip()
    major = dynamic.get("major") or {}

    cover = ""
    title = ""
    opus = major.get("opus") or {}
    if isinstance(opus, dict):
        cover = cover or _first_pic_src(opus.get("pics"))
        if not text:
            text = str(((opus.get("summary") or {}).get("text") or "")).strip()
        if not title:
            title = str(opus.get("title") or "").strip()
    draw = major.get("draw") or {}
    if isinstance(draw, dict):
        cover = cover or _first_pic_src(draw.get("items"))
    archive = major.get("archive") or {}
    if isinstance(archive, dict):
        title = title or str(archive.get("title") or "").strip()
        cover = cover or str(archive.get("cover") or "")
    article = major.get("article") or {}
    if isinstance(article, dict):
        title = title or str(article.get("title") or "").strip()
        covers = article.get("covers") or []
        if covers and not cover:
            cover = str(covers[0] or "")
    common = major.get("common") or {}
    if isinstance(common, dict):
        cover = cover or str(common.get("cover") or "")
        title = title or str(common.get("title") or "").strip()

    return {
        "id": dynamic_id,
        "uid": str(author.get("mid") or ""),
        "name": str(author.get("name") or ""),
        "type": item.get("type"),
        "kind": kind_text(item.get("type")),
        "title": title,
        "text": text,
        "cover": cover,
        "url": f"https://t.bilibili.com/{dynamic_id}",
        "ts": int(author.get("pub_ts") or 0),
    }


def normalize_dynamic_opus(item):
    """图文动态接口的一条 item → 统一结构（字段少，尽力而为）"""
    if not isinstance(item, dict):
        return None
    opus_id = str(item.get("opus_id") or "")
    if not opus_id.isdigit():
        return None
    cover = item.get("cover") or {}
    if isinstance(cover, dict):
        cover = str(cover.get("url") or "")
    else:
        cover = str(cover or "")
    return {
        "id": opus_id,
        "uid": "",
        "name": "",
        "type": "DYNAMIC_TYPE_DRAW",
        "kind": kind_text("DYNAMIC_TYPE_DRAW"),
        "title": "",
        "text": str(item.get("content") or "").strip(),
        "cover": cover,
        "url": f"https://t.bilibili.com/{opus_id}",
        "ts": 0,
    }


def merge_dynamics(full_items, opus_items):
    """合并两个数据源的动态：按 id 去重（完整接口优先），按 id 升序"""
    merged = {}
    for raw in full_items or []:
        normalized = normalize_dynamic_full(raw)
        if normalized:
            merged[normalized["id"]] = normalized
    for raw in opus_items or []:
        normalized = normalize_dynamic_opus(raw)
        if normalized and normalized["id"] not in merged:
            merged[normalized["id"]] = normalized
    return sorted(merged.values(), key=lambda d: int(d["id"]))


def norm_live_status(value):
    """直播状态归一：0 未开播 / 1 直播中；2=轮播按未开播处理（与 HarukaBot 一致）"""
    try:
        status = int(value)
    except (TypeError, ValueError):
        status = 0
    return 0 if status == 2 else status


def live_transition(old_status, new_status):
    """状态迁移：'on' 开播 / 'off' 下播 / None 无变化"""
    old_status = norm_live_status(old_status)
    new_status = norm_live_status(new_status)
    if new_status == 1 and old_status != 1:
        return "on"
    if old_status == 1 and new_status == 0:
        return "off"
    return None


def parse_live_time(value):
    """直播间 live_time（北京时间字符串）→ unix 时间戳；不认识返回 0"""
    if not value or value in (0, "0"):
        return 0
    text = str(value).strip()[:19]
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone(timedelta(hours=8)))
            return int(dt.timestamp())
        except ValueError:
            continue
    return 0


def human_duration(seconds):
    """秒 → 「1 小时 2 分钟」这类人话；非法值返回空串"""
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return ""
    if total <= 0:
        return ""
    if total < 60:
        return f"{total} 秒"
    minutes = total // 60
    hours = minutes // 60
    minutes %= 60
    if hours and minutes:
        return f"{hours} 小时 {minutes} 分钟"
    if hours:
        return f"{hours} 小时"
    return f"{minutes} 分钟"


def truncate_text(text, limit):
    """截断正文（0=不截断）；空正文给「（无正文）」"""
    body = str(text or "").strip()
    if not body:
        return "（无正文）"
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 0
    if limit > 0 and len(body) > limit:
        return body[:limit].rstrip() + "…"
    return body


def format_push(template, **kwargs):
    """渲染推送模板；模板里写了未知占位符也不该让推送整个失败"""
    try:
        return str(template).format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return str(template)


# ============================================================================
# 输入解析（纯函数）
# ============================================================================
_CQ_RE = re.compile(r"\[CQ:[^\]]+\]", re.I)
_SPACE_RE = re.compile(r"(?:space|m)\.bilibili\.com/(?:space/)?(\d{1,12})", re.I)
_UID_ARG_RE = re.compile(r"^uid\s*[:：]?\s*(\d{1,12})$", re.I)
_PLAIN_UID_RE = re.compile(r"^\d{1,12}$")


def normalize_raw(raw):
    """消息文本归一：去 CQ 码（@机器人等）、去零宽字符、折叠空白"""
    text = _CQ_RE.sub("", str(raw or ""))
    text = text.replace("\u200b", "").replace("\u3000", " ").strip()
    return re.sub(r"\s+", " ", text)


def is_addressed(event):
    """这条消息是不是在跟机器人说话（@了机器人，或以机器人名开头）"""
    raw = str(event.get("raw_message") or "")
    self_qq = str(event.get("self_id") or get_bot_qq() or "")
    if self_qq and f"[CQ:at,qq={self_qq}]" in raw:
        return True
    name = str(get_bot_name() or "")
    return bool(name) and normalize_raw(raw).startswith(name)


def strip_bot_prefix(text):
    """去掉开头的机器人昵称（「依星 关注 123」这种写法也能用）"""
    name = str(get_bot_name() or "")
    text = str(text or "")
    if name and text.startswith(name):
        rest = text[len(name):].lstrip(" ,，:：")
        if rest:
            return rest
    return text


def extract_uid(text):
    """从用户输入里抠 UID：纯数字 / 空间链接 / UID:xxx；抠不到返回空串"""
    value = str(text or "").strip()
    if not value:
        return ""
    match = _SPACE_RE.search(value)
    if match:
        return match.group(1)
    match = _UID_ARG_RE.match(value.strip(" \"'“”‘’"))
    if match:
        return match.group(1)
    plain = value.strip(" \"'“”‘’")
    if _PLAIN_UID_RE.match(plain):
        return plain
    return ""


def arg_after(raw, keyword):
    """取触发词后面的参数（触发词本身允许后面空格/冒号）"""
    raw = str(raw or "")
    keyword = str(keyword or "")
    if keyword and raw.startswith(keyword):
        return raw[len(keyword):].lstrip(" :：").strip()
    return raw.strip()


def target_of(event):
    """事件 → ('group', gid) / ('private', uid)"""
    if event.get("message_type") == "group":
        return "group", str(event.get("group_id") or "")
    return "private", str(event.get("user_id") or "")


def target_ok(target):
    """该位置当前是否允许推送（群内用分群开关当总闸；私聊只要订阅了就推）"""
    if target[0] == "group":
        return _pt_enabled(target[1], __plugin_name_en__)
    return True


# ============================================================================
# 发送
# ============================================================================
def _send_chunks(event, lines, limit=1400):
    buf = ""
    for line in lines:
        line = str(line)
        if buf and len(buf) + len(line) + 1 > limit:
            send_message(event, buf)
            buf = line
        else:
            buf = f"{buf}\n{line}" if buf else line
    if buf:
        send_message(event, buf)


def _wait_ws_ready(timeout=10.0):
    """等 WebSocket 连上（最多 timeout 秒）；单测里会被替换成空实现"""
    try:
        from utils import ws as _ws
        deadline = time.time() + timeout
        while getattr(_ws, "ws", None) is None and time.time() < deadline:
            time.sleep(0.5)
    except Exception:
        pass


def _send_push(target, segments):
    """主动推送（没有触发事件，自己拼一个最小事件给 utils.api）

    机器人刚启动时插件先加载、WS 后连上：这里最多等 10 秒等连接就绪，
    否则开播/动态会在启动瞬间被静默丢掉。
    """
    kind, ident = target
    _wait_ws_ready()
    try:
        if kind == "group":
            send_message({"message_type": "group", "group_id": int(ident)}, segments)
        else:
            send_message({"message_type": "private", "user_id": int(ident)}, segments)
    except Exception as exc:
        _plog("error", f"推送到 {kind}:{ident} 失败：{exc}")


def _at_all_segment():
    return {"type": "at", "data": {"qq": "all"}}


def _text_segment(text):
    return {"type": "text", "data": {"text": text}}


def _image_segment(url):
    return {"type": "image", "data": {"file": url}}


def _live_cover(info):
    return str(info.get("cover_from_user") or info.get("keyframe") or "")


def _live_area(info):
    parent = str(info.get("area_v2_parent_name") or "")
    child = str(info.get("area_v2_name") or "")
    if parent and child:
        return f"{parent} / {child}"
    return child or parent or "未知分区"


def _live_url(info):
    room = info.get("short_id") or info.get("room_id")
    return f"https://live.bilibili.com/{room}" if room else "https://live.bilibili.com/"


def push_live_on(uid, info, name=None):
    """推「开播」到该 UP 的所有直播订阅位置"""
    if not cfgv("push.live", True):
        return 0
    uid = str(uid)
    name = name or _store.name(uid) or str(info.get("uname") or uid)
    url = _live_url(info)
    text = format_push(
        cfgv("templates.live_on", _DEFAULTS["templates"]["live_on"]),
        name=name, uid=uid, area=_live_area(info),
        title=str(info.get("title") or "（无标题）"), url=url,
    )
    cover = _live_cover(info) if cfgv("push.cover", True) else ""
    allow_at = bool(cfgv("push.live_at", False))
    sent = 0
    for target, sub in _store.targets_for(uid, "live"):
        if not target_ok(target):
            continue
        segments = []
        if allow_at and sub.get("at") and target[0] == "group":
            segments.append(_at_all_segment())
        segments.append(_text_segment(text))
        if cover:
            segments.append(_image_segment(cover))
        _send_push(target, segments)
        sent += 1
    if sent:
        _plog("info", f"开播推送：{name}（{uid}）→ {sent} 个位置")
    return sent


def push_live_off(uid, info, since=0, name=None):
    """推「下播」；下播不 @全体（与 HarukaBot 一致）"""
    if not cfgv("push.live_off", True):
        return 0
    uid = str(uid)
    name = name or _store.name(uid) or str(info.get("uname") or uid)
    duration = human_duration(int(time.time()) - int(since)) if since else ""
    text = format_push(
        cfgv("templates.live_off", _DEFAULTS["templates"]["live_off"]),
        name=name, uid=uid, duration=(f"本次直播时长 {duration}。" if duration else ""),
        url=_live_url(info),
    )
    sent = 0
    for target, _sub in _store.targets_for(uid, "live"):
        if not target_ok(target):
            continue
        _send_push(target, [_text_segment(text)])
        sent += 1
    if sent:
        _plog("info", f"下播推送：{name}（{uid}）→ {sent} 个位置")
    return sent


def push_dynamic(uid, item):
    """推一条动态（正文 + 封面 + 链接）"""
    if not cfgv("push.dynamic", True):
        return 0
    uid = str(uid)
    name = _store.name(uid) or item.get("name") or uid
    body = truncate_text(item.get("text") or item.get("title"), cfgv("poll.text_max_len", 200))
    title = str(item.get("title") or "").strip()
    if title and title not in body:
        body = f"{title}\n{body}"
    text = format_push(
        cfgv("templates.dynamic", _DEFAULTS["templates"]["dynamic"]),
        name=name, uid=uid, kind=item.get("kind") or "发布了新动态",
        text=body, title=title, url=item.get("url") or "",
    )
    cover = str(item.get("cover") or "") if cfgv("push.cover", True) else ""
    allow_at = bool(cfgv("push.dynamic_at", False))
    sent = 0
    for target, sub in _store.targets_for(uid, "dynamic"):
        if not target_ok(target):
            continue
        segments = []
        if allow_at and sub.get("at") and target[0] == "group":
            segments.append(_at_all_segment())
        segments.append(_text_segment(text))
        if cover:
            segments.append(_image_segment(cover))
        _send_push(target, segments)
        sent += 1
    if sent:
        _plog("info", f"动态推送：{name}（{uid}）→ {item.get('url')} → {sent} 个位置")
    return sent


# ============================================================================
# 轮询（单线程循环，间隔实时读配置）
# ============================================================================
_last_poll = {"live": 0.0, "dynamic": 0.0}
_last_error = {"live": "", "dynamic": ""}
# 停机久了不补发“考古”消息：超过这个秒数的状态变化只静默重建
_DOWNTIME_TOLERANCE = 3600
# 直播状态的内存镜像 {uid: {...}}：每轮都刷 ts（不写盘），状态变化时才落盘
_live_mem = {}


def _interval(path, default, lo=10):
    try:
        value = int(cfgv(path, default))
    except (TypeError, ValueError):
        value = default
    return max(lo, value)


def fetch_dynamics(uid):
    """取某 UP 的最新动态：完整接口优先，失败/冷却时降级到图文接口"""
    full_items = None
    full_error = None
    try:
        full_items = _client.dynamic_feed(uid)
    except BiliBlocked as exc:
        full_error = exc
    except BiliError as exc:
        full_error = exc
    if full_items is not None:
        # 完整接口已经拿到数据，图文接口只用来补漏（失败就算了）
        try:
            return merge_dynamics(full_items, _client.opus_feed(uid))
        except BiliError:
            return merge_dynamics(full_items, [])
    try:
        return merge_dynamics([], _client.opus_feed(uid))
    except BiliError as exc:
        raise full_error or exc


def poll_live():
    """一轮直播轮询：批量查状态，按状态迁移推送

    状态镜像放内存（每轮刷新 last_seen，**不写盘**），只有状态真的变化才落盘，
    这样既能在停机后判断“是不是刚重启”，又不会每 60 秒磨一次磁盘。
    """
    uids = _store.uids_for("live")
    _last_poll["live"] = time.time()
    if not uids:
        return
    infos = _client.live_status(uids)
    now = int(time.time())
    for uid in uids:
        info = infos.get(str(uid)) or infos.get(uid)
        if not isinstance(info, dict):
            continue
        new_status = norm_live_status(info.get("live_status"))
        title = str(info.get("title") or "")
        since = parse_live_time(info.get("live_time")) or now
        if info.get("uname"):
            _store.set_name(uid, str(info.get("uname")))
        name = _store.name(uid) or str(info.get("uname") or "")

        mem = _live_mem.get(uid)
        if mem is None:
            old = _store.live_state(uid)
            if old is None:
                # 第一次见到这个 UP：只记录基线，别把“正在直播”当新开播推出去
                _live_mem[uid] = {"status": new_status, "since": since,
                                  "title": title, "last_seen": now}
                _store.set_live_state(uid, {"status": new_status, "since": since,
                                            "title": title, "ts": now})
                continue
            mem = {"status": norm_live_status(old.get("status")),
                   "since": int(old.get("since") or 0),
                   "title": str(old.get("title") or ""),
                   "last_seen": int(old.get("ts") or 0)}
            _live_mem[uid] = mem
            if now - mem["last_seen"] > _DOWNTIME_TOLERANCE:
                # 停机太久：静默同步到当前状态，不补发过期的开播/下播
                mem.update({"status": new_status, "since": since,
                            "title": title, "last_seen": now})
                _store.set_live_state(uid, {"status": new_status, "since": since,
                                            "title": title, "ts": now})
                continue

        event = live_transition(mem["status"], new_status)
        prev_since = int(mem.get("since") or 0)
        mem["last_seen"] = now
        if not event:
            mem["title"] = title
            continue
        mem.update({"status": new_status, "since": since, "title": title})
        _store.set_live_state(uid, {"status": new_status, "since": since,
                                    "title": title, "ts": now})
        if event == "on":
            push_live_on(uid, info, name=name)
        else:
            push_live_off(uid, info, since=prev_since or since, name=name)

    if len(_live_mem) > 1000:  # 长期运行别让内存镜像只增不减
        alive = set(uids)
        for key in [k for k in _live_mem if k not in alive]:
            _live_mem.pop(key, None)


def poll_dynamic():
    """一轮动态轮询：每个有动态订阅的 UP 各查一次"""
    uids = _store.uids_for("dynamic")
    _last_poll["dynamic"] = time.time()
    if not uids:
        return
    max_new = _cfg_int("poll.max_new_per_poll", 3, 1, 10)
    for uid in uids:
        try:
            items = fetch_dynamics(uid)
        except BiliBlocked as exc:
            _last_error["dynamic"] = str(exc)
            _plog("warn", f"拉取动态被风控（{uid}）：{exc}；下轮继续")
            continue
        except BiliError as exc:
            _last_error["dynamic"] = str(exc)
            _plog("warn", f"拉取动态失败（{uid}）：{exc}")
            continue
        except Exception as exc:  # 单条异常不该带走整个轮询线程
            _last_error["dynamic"] = str(exc)
            _plog("error", f"拉取动态异常（{uid}）：{exc}")
            continue

        last = _store.dynamic_last(uid)
        if last is None:
            # 第一次轮询只建立基线，不把历史动态全推一遍
            if items:
                _store.set_dynamic_last(uid, max(int(d["id"]) for d in items))
            continue
        if not items:
            continue
        known = int(last or 0)
        fresh = [d for d in items if int(d["id"]) > known]
        if not fresh:
            continue
        fresh.sort(key=lambda d: int(d["id"]))
        for item in fresh[:max_new]:
            push_dynamic(uid, item)
            _store.set_dynamic_last(uid, item["id"])
        _last_error["dynamic"] = ""


def _safe_poll(func, label):
    try:
        func()
    except BiliBlocked as exc:
        _last_error[label] = str(exc)
        _plog("warn", f"{label}轮询被风控：{exc}")
    except BiliError as exc:
        _last_error[label] = str(exc)
        _plog("warn", f"{label}轮询失败：{exc}")
    except Exception as exc:
        _last_error[label] = str(exc)
        _plog("error", f"{label}轮询异常：{exc}")


def _poll_loop():
    # 插件在 WS 连上之前就被导入，先等几秒，别让首轮推送打在“未连接”上
    time.sleep(5)
    next_live = 0.0
    next_dynamic = 0.0
    while True:
        try:
            if not cfgv("enabled", True):
                time.sleep(3)
                continue
            now = time.time()
            if now >= next_live:
                next_live = now + _interval("poll.live_interval", 60, 30)
                _safe_poll(poll_live, "live")
            if now >= next_dynamic:
                next_dynamic = now + _interval("poll.dynamic_interval", 180, 60)
                _safe_poll(poll_dynamic, "dynamic")
        except Exception as exc:  # 线程绝不能死
            _plog("error", f"轮询循环异常：{exc}")
            time.sleep(5)
        time.sleep(1)


_poll_thread = None
_poll_thread_lock = threading.Lock()


def _ensure_poller():
    """按需启动轮询线程（幂等；配置改完调用一次即可）

    HARUKA_NO_POLL=1 时永不启动：单测/一次性排障脚本导入插件不该产生网络活动。
    """
    global _poll_thread
    if os.environ.get("HARUKA_NO_POLL"):
        return False
    with _poll_thread_lock:
        if _poll_thread is not None and _poll_thread.is_alive():
            return False
        _poll_thread = threading.Thread(target=_poll_loop, name="haruka-poller", daemon=True)
        _poll_thread.start()
    _plog("info", "推送轮询线程已启动")
    return True


# ============================================================================
# 指令实现
# ============================================================================
_ADMIN_CACHE = {}
_ADMIN_TTL = 120


def _group_perm_enabled(gid):
    return _store.group_perm(gid)


def _is_group_admin(gid, user_id):
    key = (str(gid), str(user_id))
    now = time.time()
    cached = _ADMIN_CACHE.get(key)
    if cached and now - cached[0] < _ADMIN_TTL:
        return cached[1]
    ok = False
    try:
        resp = http_get("get_group_member_info", {"group_id": int(gid), "user_id": int(user_id)})
        role = str(((resp or {}).get("data") or {}).get("role") or "")
        ok = role in ("admin", "owner")
    except Exception as exc:
        _plog("warn", f"查询群成员身份失败（{gid}/{user_id}）：{exc}")
    _ADMIN_CACHE[key] = (now, ok)
    return ok


def _check_perm(event):
    """群内指令权限：主人永远可用；群权限关=所有人可用；否则要管理员/群主"""
    user_id = event.get("user_id")
    if _is_master(user_id):
        return True
    if event.get("message_type") == "private":
        return True
    gid = event.get("group_id")
    if not _group_perm_enabled(gid):
        return True
    return _is_group_admin(gid, user_id)


def _deny(event):
    """权限不足：@了机器人/私聊才回话，否则静默放行给其它插件

    群里常有「关注一下这个」这类普通聊天，不该被订阅指令吃掉，更不该回一句权限不足。
    """
    if event.get("message_type") == "private" or is_addressed(event):
        send_message(event, cfgv("replies.no_perm", _DEFAULTS["replies"]["no_perm"]))
        return True
    return False


def _resolve_user(arg):
    """用户输入 → (uid, name, 错误文案)。允许 UID / 空间链接 / b23 短链 / UP 名"""
    uid = extract_uid(arg)
    if not uid and "b23." in str(arg):
        uid = _client.resolve_b23(arg)
    if uid:
        try:
            card = _client.get_card(uid)
        except BiliBlocked as exc:
            return "", "", f"B站接口风控（{exc.code}），请稍后再试"
        except BiliError as exc:
            if exc.code in (-404, -400, 62002, 62004):
                return "", "", "UID 不存在（注意 UID 不是直播间号）"
            return "", "", f"查询用户失败：{exc}"
        name = card.get("name") or _store.name(uid) or uid
        return uid, name, ""
    try:
        hit = _client.search_user(str(arg).strip())
    except BiliBlocked:
        return "", "", "B站搜索接口被风控，请改用 UID 或空间链接"
    except BiliError as exc:
        return "", "", f"搜索失败：{exc}"
    if not hit:
        return "", "", ""
    return hit["uid"], hit.get("name") or hit["uid"], ""


def _need_group(event):
    if event.get("message_type") == "group":
        return False
    send_message(event, cfgv("replies.group_only", _DEFAULTS["replies"]["group_only"]))
    return True


def _cmd_sub(event, raw, keyword):
    if not _check_perm(event):
        return _deny(event)
    arg = arg_after(raw, keyword)
    if not arg:
        send_message(event, format_push(cfgv("replies.usage", _DEFAULTS["replies"]["usage"]), cmd=keyword))
        return True
    uid, name, error = _resolve_user(arg)
    if error:
        # 接口/风控类错误：原样告诉用户，别伪装成“找不到”
        send_message(event, error)
        return True
    if not uid:
        send_message(event, format_push(cfgv("replies.not_found", _DEFAULTS["replies"]["not_found"]),
                                        arg=arg, reason="没有匹配的 UP"))
        return True
    target = target_of(event)
    if _store.has_sub(target, uid):
        send_message(event, format_push(cfgv("replies.already", _DEFAULTS["replies"]["already"]),
                                        name=name, uid=uid))
        return True
    _store.add_sub(target, uid, name)
    if target[0] == "group":
        # 群内订阅 = 自动打开本群推送开关（面板里也同步显示为「开」）
        _pt_set(target[1], __plugin_name_en__, True)
    count = len(_store.subs_of(target))
    send_message(event, format_push(cfgv("replies.sub_ok", _DEFAULTS["replies"]["sub_ok"]),
                                    name=name, uid=uid, count=count))
    _plog("info", f"新关注：{name}（{uid}）@ {target[0]}:{target[1]}")
    return True


def _cmd_unsub(event, raw, keyword):
    if not _check_perm(event):
        return _deny(event)
    arg = arg_after(raw, keyword)
    if not arg:
        send_message(event, format_push(cfgv("replies.usage", _DEFAULTS["replies"]["usage"]), cmd=keyword))
        return True
    uid = extract_uid(arg)
    if not uid:
        send_message(event, format_push(cfgv("replies.not_found", _DEFAULTS["replies"]["not_found"]),
                                        arg=arg, reason="请输入 UID"))
        return True
    target = target_of(event)
    name = _store.name(uid) or uid
    if not _store.remove_sub(target, uid):
        send_message(event, format_push(cfgv("replies.not_sub", _DEFAULTS["replies"]["not_sub"]),
                                        uid=uid, cmd=cfgv("commands.sub", "关注")))
        return True
    send_message(event, format_push(cfgv("replies.unsub_ok", _DEFAULTS["replies"]["unsub_ok"]),
                                    name=name, uid=uid))
    _plog("info", f"取关：{name}（{uid}）@ {target[0]}:{target[1]}")
    return True


def _on_off(flag, value, label):
    """生成「开启/关闭 直播|动态|全体 UID」这类指令的处理函数"""

    def _handler(event, raw, keyword):
        if not _check_perm(event):
            return _deny(event)
        arg = arg_after(raw, keyword)
        if not arg:
            send_message(event, format_push(cfgv("replies.usage", _DEFAULTS["replies"]["usage"]), cmd=keyword))
            return True
        uid = extract_uid(arg)
        if not uid:
            send_message(event, format_push(cfgv("replies.not_found", _DEFAULTS["replies"]["not_found"]),
                                            arg=arg, reason="请输入 UID"))
            return True
        target = target_of(event)
        if flag == "at" and target[0] != "group":
            return _need_group(event)
        if not _store.set_flag(target, uid, flag, value):
            send_message(event, format_push(cfgv("replies.not_sub", _DEFAULTS["replies"]["not_sub"]),
                                            uid=uid, cmd=cfgv("commands.sub", "关注")))
            return True
        name = _store.name(uid) or uid
        send_message(event, f"已{'开启' if value else '关闭'} {name}（{uid}）的{label}")
        return True

    return _handler


def _cmd_list(event, raw, keyword):
    if not _check_perm(event):
        return _deny(event)
    target = target_of(event)
    subs = _store.subs_of(target)
    if not subs:
        send_message(event, cfgv("replies.list_empty", _DEFAULTS["replies"]["list_empty"]))
        return True
    lines = [format_push(cfgv("replies.list_title", _DEFAULTS["replies"]["list_title"]), count=len(subs))]
    for uid in sorted(subs, key=lambda x: int(x) if x.isdigit() else 0):
        sub = subs[uid]
        name = sub.get("name") or _store.name(uid) or uid
        lines.append(
            f"{name}（{uid}） 直播:{'开' if sub.get('live') else '关'} "
            f"动态:{'开' if sub.get('dynamic') else '关'} "
            f"全体:{'开' if sub.get('at') else '关'}"
        )
    _send_chunks(event, lines)
    return True


def _cmd_live_now(event, raw, keyword):
    if not _check_perm(event):
        return _deny(event)
    target = target_of(event)
    subs = _store.subs_of(target)
    if not subs:
        send_message(event, cfgv("replies.list_empty", _DEFAULTS["replies"]["list_empty"]))
        return True
    living = []
    for uid, sub in subs.items():
        state = _store.live_state(uid) or {}
        if sub.get("live") and norm_live_status(state.get("status")) == 1:
            title = str(state.get("title") or "").strip()
            name = _store.name(uid) or sub.get("name") or uid
            living.append(f"{name}（{uid}）{(' ' + title) if title else ''}")
    if not living:
        send_message(event, "当前没有正在直播的关注")
        return True
    _send_chunks(event, [f"正在直播（{len(living)}）："] + living)
    return True


def _cmd_perm_on(event, raw, keyword):
    return _set_perm(event, True)


def _cmd_perm_off(event, raw, keyword):
    return _set_perm(event, False)


def _set_perm(event, enabled):
    if _need_group(event):
        return True
    gid = event.get("group_id")
    user_id = event.get("user_id")
    if not (_is_master(user_id) or _is_group_admin(gid, user_id)):
        return _deny(event)
    _store.set_group_perm(gid, enabled)
    send_message(event, "已开启权限：只有管理员和主人可以使用指令" if enabled
                 else "已关闭权限：所有人均可使用指令")
    return True


def _cmd_help(event, raw, keyword):
    lines = [
        "【B站推送】把 B站 UP 主的动态/开播推送到群或私聊",
        "用法：指令 + UID（也可用空间链接 / UP 名）",
        "",
    ]
    for cmd in _REG.all():
        lines.append(f"{'/'.join(cmd.keywords)}  —  {cmd.desc}")
    lines += [
        "",
        "群与私聊的关注列表各自独立；机器人退群会自动清理该群订阅。",
    ]
    _send_chunks(event, lines)
    return True


def _cmd_status(event, raw, keyword):
    if not _is_master(event.get("user_id")):
        send_message(event, "只有主人才能查看运行状态")
        return True
    now = time.time()

    def _ago(ts):
        if not ts:
            return "还没跑过"
        return human_duration(max(1, int(now - ts))) + "前"

    targets = _store.all_targets()
    lines = [
        "【B站推送状态】",
        f"总开关：{'开' if cfgv('enabled', True) else '关'}",
        f"关注：{_store.count_uids()} 个 UP / {len(targets)} 个位置（群或私聊）",
        f"轮询：直播每 {_interval('poll.live_interval', 60, 30)} 秒、动态每 {_interval('poll.dynamic_interval', 180, 60)} 秒",
        f"上次轮询：直播 {_ago(_last_poll['live'])}，动态 {_ago(_last_poll['dynamic'])}",
        f"数据源：{_client.health()}",
    ]
    for label in ("live", "dynamic"):
        if _last_error[label]:
            lines.append(f"最近错误（{label}）：{_last_error[label][:120]}")
    _send_chunks(event, lines)
    return True


def _cmd_test(event, raw, keyword):
    """往当前会话发一条示例推送，用来确认「发送链路」通不通"""
    if not _check_perm(event):
        return _deny(event)
    uid = _store.uids_for("dynamic")[0] if _store.uids_for("dynamic") else ""
    name = _store.name(uid) if uid else "测试 UP"
    sample = {
        "id": "0",
        "name": name,
        "kind": "发布了新动态",
        "title": "",
        "text": "这是一条测试推送：收到说明 B站推送插件的发送链路正常。",
        "cover": "",
        "url": "https://t.bilibili.com/",
    }
    text = format_push(cfgv("templates.dynamic", _DEFAULTS["templates"]["dynamic"]),
                       name=sample["name"], uid=uid or "-", kind=sample["kind"],
                       text=sample["text"], title="", url=sample["url"])
    send_message(event, [{"type": "text", "data": {"text": text}}])
    return True


def _cmd_enable(event, raw, keyword):
    return _set_plugin_enabled(event, True)


def _cmd_disable(event, raw, keyword):
    return _set_plugin_enabled(event, False)


def _set_plugin_enabled(event, enabled):
    if not _is_master(event.get("user_id")):
        send_message(event, "只有主人才能开关 B站推送")
        return True
    if event.get("message_type") == "group":
        _pt_set(event.get("group_id"), __plugin_name_en__, enabled)
        send_message(event, "已在本群开启 B站推送" if enabled else "已在本群关闭 B站推送")
    else:
        _CFG["enabled"] = bool(enabled)
        _save_cfg()
        _ensure_poller()
        send_message(event, "已开启 B站推送（全局）" if enabled else "已关闭 B站推送（全局）")
    return True


# ============================================================================
# 指令注册表（集中定义，命令表/帮助都从这里来）
# ============================================================================
_REG = None


def _build_registry():
    c = lambda key, default: str(cfgv(f"commands.{key}", default) or default)  # noqa: E731

    reg = CommandRegistry(PLUGIN)

    # 先注册「短词是别人前缀」的精确指令，避免被前缀指令抢走
    reg.register("关注列表", [c("list", "关注列表")], "查看本群/本私聊的关注列表", _cmd_list)
    reg.register("已开播", [c("live_now", "已开播")], "查看关注里正在直播的 UP", _cmd_live_now)
    reg.register("帮助", [c("help", "B站帮助")], "查看 B站推送 的指令说明", _cmd_help)
    reg.register("运行状态", [c("status", "B站推送状态")], "查看轮询与数据源状态（仅主人）", _cmd_status)
    reg.register("测试推送", [c("test", "B站推送测试")], "往当前会话发一条测试推送", _cmd_test)
    reg.register("开启权限", [c("perm_on", "开启权限")], "本群仅管理员可用指令（群主/主人）", _cmd_perm_on)
    reg.register("关闭权限", [c("perm_off", "关闭权限")], "本群所有人可用指令（群主/主人）", _cmd_perm_off)
    reg.register("开启推送", [c("enable", "开启B站推送")], "开启本群/全局推送（仅主人）", _cmd_enable)
    reg.register("关闭推送", [c("disable", "关闭B站推送")], "关闭本群/全局推送（仅主人）", _cmd_disable)

    # 带参数的前缀指令（注册顺序即匹配优先级）
    reg.register("关注", [c("sub", "关注")], "关注 UP 主（UID/空间链接/UP名）", _cmd_sub, kind="prefix")
    reg.register("取关", [c("unsub", "取关")], "取消关注（UID）", _cmd_unsub, kind="prefix")
    reg.register("开启动态", [c("dyn_on", "开启动态")], "开启某个 UP 的动态推送", _on_off("dynamic", True, "动态推送"), kind="prefix")
    reg.register("关闭动态", [c("dyn_off", "关闭动态")], "关闭某个 UP 的动态推送", _on_off("dynamic", False, "动态推送"), kind="prefix")
    reg.register("开启直播", [c("live_on", "开启直播")], "开启某个 UP 的直播推送", _on_off("live", True, "直播推送"), kind="prefix")
    reg.register("关闭直播", [c("live_off", "关闭直播")], "关闭某个 UP 的直播推送", _on_off("live", False, "直播推送"), kind="prefix")
    reg.register("开启全体", [c("at_on", "开启全体")], "该 UP 开播时 @全体（仅群聊）", _on_off("at", True, "开播 @全体"), kind="prefix")
    reg.register("关闭全体", [c("at_off", "关闭全体")], "不再 @全体", _on_off("at", False, "开播 @全体"), kind="prefix")
    return reg


def _sync_labels():
    """把「触发词 → 指令名」写进配置，供面板显示可读名称（只读字段）"""
    try:
        labels = _REG.labels() if _REG is not None else {}
        with _CFG_LOCK:
            _CFG.setdefault("command_labels", {})
            if _CFG["command_labels"] != labels:
                _CFG["command_labels"] = labels
                _save_cfg()
    except Exception as exc:
        _plog("warn", f"同步指令标签失败：{exc}")


def reload_config():
    """配置热重载钩子（面板保存 → SIGUSR1 → 这里）

    与其它插件不同的是：指令触发词是**在注册表里按配置动态构建**的，
    所以改触发词也会立刻生效（表重建），不需要重启进程。
    """
    global _REG
    _load_cfg()
    _REG = _build_registry()
    _sync_labels()
    _ensure_poller()
    _plog("info", "配置已重载")


# ============================================================================
# 事件入口
# ============================================================================
def _handle_notice(event):
    """机器人被踢/退群：清理该群订阅（HarukaBot 的 auto_delete）"""
    if event.get("notice_type") != "group_decrease":
        return False
    gid = event.get("group_id")
    if not gid:
        return False
    self_qq = str(event.get("self_id") or get_bot_qq() or "")
    leaving = str(event.get("user_id") or "")
    if leaving != self_qq and event.get("sub_type") != "kick_me":
        return False
    removed = _store.drop_group(gid)
    if removed:
        _plog("info", f"机器人退出群 {gid}，已清理 {removed} 个订阅")
    return bool(removed)


def handle(event):
    post_type = event.get("post_type")
    if post_type == "notice":
        return _handle_notice(event)
    if post_type != "message":
        return False
    message_type = event.get("message_type")
    if message_type not in ("group", "private"):
        return False
    # 群临时会话（私聊 sub_type=group）不处理，避免任何人借临时会话操作订阅
    if message_type == "private" and event.get("sub_type") == "group":
        return False

    raw = normalize_raw(event.get("raw_message") or "")
    if not raw:
        return False

    master = _is_master(event.get("user_id"))
    if (message_type == "group" and not master
            and bool(cfgv("require_at", False)) and not is_addressed(event)):
        # 配置要求 @机器人：没 @ 的消息不归本插件管，原样交给其它插件
        return False
    raw = strip_bot_prefix(raw)

    _ensure_poller()
    if _REG is not None and _REG.dispatch(event, raw, master):
        return True
    return False


# ============================================================================
# 模块加载
# ============================================================================
_load_cfg()
_store.load()
_REG = _build_registry()
_sync_labels()

# 单测/调试时用 HARUKA_NO_POLL=1 关掉后台线程（导入不该产生网络活动）
if not os.environ.get("HARUKA_NO_POLL"):
    _ensure_poller()
