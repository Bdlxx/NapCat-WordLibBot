"""
分群插件开关管理
每个群独立控制各插件的开启/关闭，默认所有插件在群内关闭
全局开关（config.json 中的 enabled）作为主人总闸
"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

TOGGLE_FILE = os.path.join(DATA_DIR, "plugin_toggle.json")

# 默认状态：所有插件在分群中关闭
PLUGINS = ["wordlib"]


def _load():
    if os.path.exists(TOGGLE_FILE):
        try:
            with open(TOGGLE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def _save(data):
    # 保留 _note
    note = None
    if os.path.exists(TOGGLE_FILE):
        try:
            with open(TOGGLE_FILE, "r", encoding="utf-8") as f:
                note = json.load(f).get("_note")
        except:
            pass
    if note:
        data["_note"] = note
    with open(TOGGLE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_enabled(group_id: str, plugin: str) -> bool:
    """
    检查某个插件在指定群是否开启
    默认（未配置）返回 False
    """
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


def get_all_toggles() -> dict:
    """获取所有群的所有插件开关状态，用于 web 面板展示"""
    data = _load()
    result = {}
    for group_id, toggles in data.items():
        if group_id == "_note":
            continue
        result[group_id] = {p: toggles.get(p, False) for p in PLUGINS}
    return result


def set_group_toggles(group_id: str, toggles: dict):
    """批量设置某个群的所有插件开关"""
    data = _load()
    gid = str(group_id)
    data[gid] = {p: toggles.get(p, False) for p in PLUGINS}
    _save(data)


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
