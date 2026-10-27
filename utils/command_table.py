"""
命令表生成 - 读取所有插件配置 JSON，合成完整命令表
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
    """生成所有插件的完整命令表文本"""
    lines = []
    lines.append(f"===== {bot_name} 命令表 =====\n")

    # 词库插件
    wc = _read_json(os.path.join(DATA_DIR, "wordlib_config.json"))
    w_commands = wc.get("commands", {})
    if w_commands:
        lines.append("【词库插件】")
        # 映射中文说明
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

    # 结婚插件
    mc = _read_json(os.path.join(DATA_DIR, "marry_config.json"))
    m_commands = mc.get("commands", {})
    if m_commands:
        lines.append("【结婚插件】")
        descs = {
            "marry": "随机娶一位群友",
            "marry_t": "娶指定的群友（@对方）",
            "marry_f": "随机嫁给一位群友",
            "marry_ft": "嫁给指定的群友（@对方）",
            "divorce": "和今天的对象离婚",
            "my_object": "查看今天的对象",
            "set_prob": "设置结婚成功率（主人）",
            "set_cd": "设置离婚CD（主人）",
            "enable": "本群开启结婚",
            "disable": "本群关闭结婚",
        }
        for key, cmd_text in m_commands.items():
            desc = descs.get(key, "")
            if desc:
                lines.append(f"  {cmd_text}  — {desc}")
        lines.append("")

    # 伪人插件
    pc = _read_json(os.path.join(DATA_DIR, "persona_config.json"))
    p_commands = pc.get("commands", {})
    # 去重（alt 命令合并显示）
    seen = set()
    p_deduped = []
    for key, cmd_text in p_commands.items():
        base = key.replace("_alt", "").replace("_alt2", "")
        if base not in seen:
            seen.add(base)
            p_deduped.append((base, cmd_text))
    if p_commands:
        lines.append("【伪人插件】")
        descs = {
            "enable": "本群开启伪人",
            "disable": "本群关闭伪人",
            "switch_glm": "切换模型为GLM",
            "switch_gemini": "切换模型为Gemini",
            "current_model": "查看当前模型",
            "clear_history": "清除当前对话记忆",
            "clear_all": "清除所有对话记忆",
        }
        # 显示所有 unique 命令，附带 aliases
        used_bases = set()
        for key, cmd_text in p_commands.items():
            base = key.replace("_alt", "").replace("_alt2", "")
            if base not in used_bases:
                used_bases.add(base)
                # 收集同组的 aliases
                aliases = [cmd_text]
                for k2, v2 in p_commands.items():
                    if k2 != key and k2.replace("_alt", "").replace("_alt2", "") == base:
                        aliases.append(v2)
                desc = descs.get(base, "")
                alias_str = " / ".join(aliases)
                if desc:
                    lines.append(f"  {alias_str}  — {desc}")
                else:
                    lines.append(f"  {alias_str}")
        lines.append("")

    # 视频解析插件
    lines.append("【视频解析插件】")
    lines.append("  自动检测群内分享的视频链接并解析")
    lines.append("  支持平台：哔哩哔哩 / 抖音 / 快手 / 小红书 / TikTok")
    lines.append("  开启视频解析  — 本群开启")
    lines.append("  关闭视频解析  — 本群关闭")
    lines.append("")

    # JM下载插件
    jc = _read_json(os.path.join(DATA_DIR, "jm_downloader_config.json"))
    j_commands = jc.get("commands", {})
    if j_commands:
        lines.append("【JM下载插件】")
        j_descs = {
            "download": "下载本子并转PDF分享（例：jm 123456；多本 jm 123 456；单章 jm 123 p456）",
            "detail": "查看本子元信息（例：jm详情 123456）",
            "enable": "本群开启JM下载（仅主人）",
            "disable": "本群关闭JM下载（仅主人）",
        }
        for key, cmd_text in j_commands.items():
            desc = j_descs.get(key, "")
            if desc:
                lines.append(f"  {cmd_text}  — {desc}")
        lines.append("  jm更新  — 手动更新 jmcomic 库（仅主人，插件默认自动更新）")
        lines.append("")

    # B站推送插件
    hc = _read_json(os.path.join(DATA_DIR, "haruka_config.json"))
    h_commands = hc.get("commands", {})
    if h_commands:
        lines.append("【B站推送插件】")
        h_descs = {
            "sub": "关注 UP 主（例：关注 546195；也支持空间链接/UP名）",
            "unsub": "取消关注（例：取关 546195）",
            "list": "查看本群/本私聊的关注列表",
            "dyn_on": "开启动态推送（例：开启动态 546195）",
            "dyn_off": "关闭动态推送（例：关闭动态 546195）",
            "live_on": "开启直播推送（例：开启直播 546195）",
            "live_off": "关闭直播推送（例：关闭直播 546195）",
            "at_on": "开播时 @全体（例：开启全体 546195，仅群聊）",
            "at_off": "不再 @全体（例：关闭全体 546195）",
            "live_now": "查看关注里正在直播的 UP",
            "perm_on": "本群仅管理员可用指令（群主/主人）",
            "perm_off": "本群所有人可用指令（群主/主人）",
            "help": "查看 B站推送 指令说明",
            "status": "查看轮询/数据源状态（仅主人）",
            "test": "往当前会话发一条测试推送",
            "enable": "开启本群/全局推送（仅主人；群内=本群）",
            "disable": "关闭本群/全局推送（仅主人；群内=本群）",
        }
        for key, cmd_text in h_commands.items():
            desc = h_descs.get(key, "")
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
