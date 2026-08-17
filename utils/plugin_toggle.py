"""
分群插件开关管理 + 插件元数据注册
每个群独立控制各插件的开启/关闭，默认所有插件在群内关闭
全局开关（config.json 中的 enabled）作为主人总闸

插件元数据注册：
  新增插件时在 PLUGIN_META 添加一条记录即可，无需改其他代码。
  WebUI 通过 get_plugin_meta() 获取所有插件信息。
"""

import json
import os
import re
import importlib.util

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

TOGGLE_FILE = os.path.join(DATA_DIR, "plugin_toggle.json")

# ========== 插件元数据注册表 ==========
# 在此添加新插件，WebUI 会自动识别并显示
PLUGIN_META = {
    "wordlib": {
        "name_cn": "词库插件",
        "name_en": "wordlib",
        "config_file": "wordlib_config.json",
        "description": "关键词匹配回复、签到好感度、自定义昵称",
    },
    "marry": {
        "name_cn": "结婚插件",
        "name_en": "marry",
        "config_file": "marry_config.json",
        "description": "群内每日结婚/离婚系统",
    },
    "pseudo": {
        "name_cn": "伪人插件",
        "name_en": "pseudo_persona",
        "config_file": "persona_config.json",
        "description": "AI 对话回复、角色扮演，支持 GLM 和 Gemini 双模型",
    },
    "video_parser": {
        "name_cn": "视频解析",
        "name_en": "video_parser",
        "config_file": "video_parser_config.json",
        "description": "抖音/B站/快手/小红书/TikTok视频解析去水印",
    },
    "jm_downloader": {
        "name_cn": "JM下载",
        "name_en": "jm_downloader",
        "config_file": "jm_downloader_config.json",
        "description": "jm命令下载禁漫本子并转PDF分享，自动更新jmcomic库",
    },
}

PLUGINS = list(PLUGIN_META.keys())


def _scan_plugins_dir(plugins_dir: str) -> dict:
    """扫描插件目录，返回 {key: meta}

    与主程序（main.py）的加载逻辑保持一致：
    - 只统计目录下实际存在、且模块级定义了 handle() 的 .py 文件
    - 已注册（PLUGIN_META）的用注册信息（含 config_file）
    - 未注册的自动读取 SDK 元数据变量（__plugin_name_cn__ 等），config_file 按命名规范推断
    返回的 meta 键：name_cn / name_en / config_file / description / version / author
    """
    if not plugins_dir or not os.path.isdir(plugins_dir):
        return {}
    result = {}
    for fname in sorted(os.listdir(plugins_dir)):
        if not fname.endswith('.py') or fname == '__init__.py':
            continue
        fpath = os.path.join(plugins_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                src = fh.read()
        except Exception:
            continue
        # 模拟 main.py 的 hasattr(module, "handle") 判断
        if not re.search(r'^def\s+handle\s*\(', src, re.M):
            continue
        name_en = fname[:-3]
        reg = None
        for k, v in PLUGIN_META.items():
            if v.get('name_en') == name_en:
                reg = k
                break
        if reg:
            rmeta = PLUGIN_META[reg]
            result[reg] = {
                'name_cn': rmeta.get('name_cn', name_en),
                'name_en': rmeta.get('name_en', name_en),
                'config_file': rmeta.get('config_file'),
                'description': rmeta.get('description', ''),
                'version': '', 'author': '',
            }
            continue
        # 未注册：自动读取元数据变量
        _v = lambda pat: (m := re.search(rf'^{pat}\s*=\s*["\']([^"\']+)["\']', src, re.M)) and m.group(1) or ''
        result[name_en] = {
            'name_cn': _v('__plugin_name_cn__') or name_en,
            'name_en': name_en,
            'config_file': f"{name_en}_config.json",
            'description': _v('__plugin_desc__'),
            'version': _v('__plugin_version__'),
            'author': _v('__plugin_author__'),
        }
    return result


def get_plugin_meta(plugin_key: str = None, plugins_dir: str = None) -> dict:
    """获取插件元数据
    无参数时返回注册表全部；有参数时返回单个插件元数据（不存在返回 None）
    plugins_dir: 提供时自动扫描目录中实际存在且有 handle() 的插件（与主程序加载一致）
    """
    if plugins_dir:
        scanned = _scan_plugins_dir(plugins_dir)
        if plugin_key is None:
            return scanned
        return scanned.get(plugin_key)
    if plugin_key:
        return PLUGIN_META.get(plugin_key)
    return dict(PLUGIN_META)


def scan_plugin_metadata(plugins_dir: str = None, plugin_key: str = None):
    """从插件 .py 文件读取 SDK 规范元数据变量
    扫描插件文件中的 __plugin_name_cn__、__plugin_desc__ 等变量。
    返回 {key: {name_cn, name_en, version, desc, author, config_file}} 或 None
    """
    if not plugins_dir or not os.path.isdir(plugins_dir):
        return {} if plugin_key is None else None

    result = {}
    for fname in sorted(os.listdir(plugins_dir)):
        if not fname.endswith('.py') or fname == '__init__.py':
            continue
        fpath = os.path.join(plugins_dir, fname)
        try:
            with open(fpath, 'r', encoding='utf-8') as fh:
                src = fh.read()
        except:
            continue

        name_en = fname[:-3]
        if plugin_key is not None and name_en != plugin_key:
            continue

        meta = {'name_en': name_en}
        # 用正则提取模块级变量
        _v = lambda pat: (m := re.search(rf'^{pat}\s*=\s*["\']([^"\']+)["\']', src, re.M)) and m.group(1) or ''
        meta['name_cn'] = _v('__plugin_name_cn__') or ''
        meta['version'] = _v('__plugin_version__') or ''
        meta['desc'] = _v('__plugin_desc__') or ''
        meta['author'] = _v('__plugin_author__') or ''

        # 对应 PLUGIN_META 中的 config_file
        cfile = f"{{name_en}}_config.json"
        meta['config_file'] = cfile

        if plugin_key is not None:
            return meta
        result[name_en] = meta

    return result if plugin_key is None else None


def get_available_plugins(plugins_dir: str = None) -> list:
    """返回可用插件列表 [(key, meta), ...]

    plugins_dir 为 None 时返回注册表全部（不检查文件系统）；
    提供 plugins_dir 时动态扫描该目录：只返回实际存在且有 handle() 的插件
    （与主程序加载一致，未注册的新插件也会自动出现）
    """
    if plugins_dir is None:
        return [(k, v) for k, v in PLUGIN_META.items()]
    return list(_scan_plugins_dir(plugins_dir).items())


def _load(data_dir=None):
    """读取开关数据
    data_dir: 指定数据目录，为 None 时使用默认目录
    """
    toggle_file = os.path.join(data_dir, "plugin_toggle.json") if data_dir else TOGGLE_FILE
    if os.path.exists(toggle_file):
        try:
            with open(toggle_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def _save(data, data_dir=None):
    """保存开关数据
    data_dir: 指定数据目录，为 None 时使用默认目录
    """
    toggle_file = os.path.join(data_dir, "plugin_toggle.json") if data_dir else TOGGLE_FILE
    if data_dir:
        os.makedirs(data_dir, exist_ok=True)
    note = None
    if os.path.exists(toggle_file):
        try:
            note = json.load(open(toggle_file, 'r', encoding='utf-8')).get("_note")
        except:
            pass
    if note:
        data["_note"] = note
    with open(toggle_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_enabled(group_id: str, plugin: str) -> bool:
    """检查某个插件在指定群是否开启，默认（未配置）返回 False"""
    data = _load()
    group_data = data.get(str(group_id), {})
    return group_data.get(plugin, False) is True


def set_enabled(group_id: str, plugin: str, enabled: bool):
    """设置某个插件在指定群的开关状态"""
    data = _load()
    gid = str(group_id)
    if gid not in data:
        data[gid] = {}
    data[gid][plugin] = enabled
    _save(data)


def get_all_toggles(plugins_list: list = None) -> dict:
    """获取所有群的所有插件开关状态，返回完整矩阵（所有插件都有条目）
    plugins_list: 指定插件列表（如动态扫描结果），为 None 时用注册表
    """
    data = _load()
    plist = plugins_list or PLUGINS
    result = {}
    for group_id, toggles in data.items():
        if group_id == "_note":
            continue
        result[group_id] = {p: toggles.get(p, False) for p in plist}
    return result


def get_toggles_matrix(data_dir=None, plugins_list: list = None) -> dict:
    """返回群组开关表格数据（含所有群和所有插件，默认 false）
    返回: {
        "groups": ["群号1", "群号2", ...],
        "plugins": ["插件key1", ...],
        "toggles": {"群号": {"插件key": bool, ...}, ...}
    }
    data_dir: 可选，指定数据目录
    plugins_list: 可选，指定插件列表（如动态扫描结果），为 None 时用注册表
    """
    data = _load(data_dir)
    groups = sorted([gid for gid in data.keys() if gid != "_note"])
    plugins = list(plugins_list or PLUGINS)
    toggles = {}
    for gid in groups:
        toggles[gid] = {p: data[gid].get(p, False) for p in plugins}
    return {"groups": groups, "plugins": plugins, "toggles": toggles}


def set_group_toggles(group_id: str, toggles: dict):
    """批量设置某个群的所有插件开关"""
    data = _load()
    gid = str(group_id)
    data[gid] = {p: toggles.get(p, False) for p in set(list(PLUGINS) + list(toggles.keys()))}
    _save(data)


def set_batch_toggles(toggles_data: dict, data_dir=None):
    """批量设置多个群的插件开关
    toggles_data: {"群号": {"插件key": bool, ...}, ...}
    data_dir: 可选，指定数据目录
    """
    data = _load(data_dir)
    for gid, toggles in toggles_data.items():
        if gid == "_note":
            continue
        data[gid] = {p: toggles.get(p, False) for p in set(list(PLUGINS) + list(toggles.keys()))}
    _save(data, data_dir)


def get_all_groups_summary() -> list:
    """返回所有群的开关摘要，用于消息展示"""
    data = _load()
    result = []
    for gid in sorted(data.keys()):
        if gid == "_note":
            continue
        enabled_list = [p for p in PLUGINS if data[gid].get(p)]
        if enabled_list:
            result.append(f"群 {gid}: {', '.join(enabled_list)}")
    return result
