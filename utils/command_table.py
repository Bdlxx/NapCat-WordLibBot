"""
命令表生成 - 读取词库插件配置 JSON，生成命令表
"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def _read_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {}


def build_command_table(bot_name="羽笙"):
    """生成词库插件的完整命令表文本"""
    lines = []
    lines.append(f"===== {bot_name} 命令表 =====\n")

    # 词库插件
    wc = _read_json(os.path.join(DATA_DIR, "wordlib_config.json"))
    w_commands = wc.get("commands", {})
    if w_commands:
        lines.append("【词库插件】")
        descs = {
            "add": "添加词条（两步或一步）",
            "delete": "删除词条",
            "query": "查询词条",
            "encode": "转码消息",
            "sign1": "每日签到",
            "sign2": "每日签到（简写）",
            "nickname": "设置自定义昵称",
            "rank": "签到排行榜",
            "praise1": "让机器人赞你",
            "add_fuzzy": "添加模糊匹配词条",
            "enable": "本群开启词库",
            "disable": "本群关闭词库",
        }
        for key, cmd_text in w_commands.items():
            desc = descs.get(key, "")
            if desc:
                lines.append(f"  {cmd_text}  — {desc}")
        lines.append("")

    # 分群开关说明
    lines.append("【分群开关说明】")
    lines.append("  所有插件在每个群默认关闭，需在群内发送对应命令开启")
    lines.append("  私聊发送开启/关闭命令 = 全局控制")
    lines.append("")

    lines.append(f"===== 共 {len(lines)-1} 行 =====")
    return "\n".join(lines)
