__config_schema__ = {
    # ---------------- 模型与凭证（current_model / glm.* / gemini.*）----------------
    "current_model": {
        "type": "select", "label": "当前 AI 模型", "group": "模型与凭证",
        "path": "current_model",
        "options": [{"value": "glm", "label": "GLM（glm.* 配置）"},
                    {"value": "gemini", "label": "Gemini（gemini.* 配置）"}],
        "help": "主人也可以用指令「切换glm / 切换gemini」切换；主模型连续失败时会自动临时切到另一个",
    },
    "glm_api_url": {
        "type": "text", "label": "GLM 接口地址", "group": "模型与凭证", "advanced": True,
        "path": "glm.api_url",
        "help": "OpenAI 兼容的 chat/completions 地址，必须包含 /v1/chat/completions",
    },
    "glm_api_key": {
        "type": "password", "label": "GLM API Key", "group": "模型与凭证",
        "path": "glm.api_key",
        "help": "中转/官方 Key；留空则该模型不可用（会自动走另一个模型）",
    },
    "glm_model": {
        "type": "text", "label": "GLM 模型名", "group": "模型与凭证", "advanced": True,
        "path": "glm.model", "help": "如 glm-4v-flash（带 v 的型号才能识图）",
    },
    "gemini_api_url": {
        "type": "text", "label": "Gemini 接口地址", "group": "模型与凭证", "advanced": True,
        "path": "gemini.api_url",
        "help": "OpenAI 兼容的 chat/completions 地址",
    },
    "gemini_api_key": {
        "type": "password", "label": "Gemini API Key", "group": "模型与凭证",
        "path": "gemini.api_key",
        "help": "中转/官方 Key；留空则该模型不可用（会自动走另一个模型）",
    },
    "gemini_model": {
        "type": "text", "label": "Gemini 模型名", "group": "模型与凭证", "advanced": True,
        "path": "gemini.model", "help": "如 gemini-2.5-flash",
    },

    # ---------------- 参数 ----------------
    "enabled": {
        "type": "bool", "label": "插件总开关", "group": "参数",
        "path": "enabled",
        "help": "全局总开关，关闭后群聊/私聊都不再回复（分群开关见「群组管理」）",
    },
    "reply_probability": {
        "type": "number", "label": "回复概率", "group": "参数",
        "path": "reply_probability", "min": 0, "max": 1, "unit": "0~1",
        "help": "被 @ 或回复机器人时真正回复的概率（1=必定回复）；允许小数故未设步长",
    },
    "record_group_unrelated": {
        "type": "bool", "label": "记录无关群消息", "group": "参数",
        "path": "record_group_unrelated",
        "help": "群聊里是否也把与机器人无关的消息记进上下文（False 仅记录回复/被@的，避免污染上下文）",
    },
    "max_history": {
        "type": "number", "label": "历史消息上限", "group": "参数",
        "path": "max_history", "min": 5, "max": 500, "step": 5, "unit": "条",
        "help": "每个会话（群/私聊）保留的历史条数",
    },
    "context_window": {
        "type": "number", "label": "上下文窗口", "group": "参数",
        "path": "context_window", "min": 1, "max": 200, "step": 1, "unit": "条",
        "help": "每次送给 AI 的最近消息条数",
    },
    "split_count": {
        "type": "number", "label": "分条发送上限", "group": "参数",
        "path": "split_count", "min": 0, "max": 20, "step": 1, "unit": "条",
        "help": "AI 用 |#|#| 分段时最多发几条，0=不拆分",
    },
    "split_delay_min": {
        "type": "number", "label": "分条最小间隔", "group": "参数",
        "path": "split_delay_min", "min": 0, "max": 60, "step": 1, "unit": "秒",
    },
    "split_delay_max": {
        "type": "number", "label": "分条最大间隔", "group": "参数",
        "path": "split_delay_max", "min": 0, "max": 60, "step": 1, "unit": "秒",
    },
    "temperature": {
        "type": "number", "label": "温度", "group": "参数",
        "path": "temperature", "min": 0, "max": 2,
        "help": "越大越发散（0~2，允许小数故未设步长）",
    },
    "max_tokens": {
        "type": "number", "label": "最大 Token", "group": "参数",
        "path": "max_tokens", "min": 16, "max": 8192, "step": 16,
        "help": "单次回复上限；太小会被截断",
    },
    "api_timeout": {
        "type": "number", "label": "接口超时", "group": "参数", "advanced": True,
        "path": "api_timeout", "min": 5, "max": 600, "step": 5, "unit": "秒",
        "help": "调用 AI 接口的等待上限，超时即判失败并尝试备用模型",
    },
    "health_check_interval": {
        "type": "number", "label": "健康检查间隔", "group": "参数", "advanced": True,
        "path": "health_check_interval", "min": 60, "max": 86400, "step": 60, "unit": "秒",
        "help": "主模型失败后多久探测一次、能否切回（源码下限 60 秒）",
    },
    "random_reply_probability": {
        "type": "number", "label": "随机回复概率（未生效）", "group": "参数", "advanced": True,
        "path": "random_reply_probability", "min": 0, "max": 1, "unit": "0~1",
        "help": "文件里有此键但当前源码未读取（历史遗留），保留兼容",
    },

    # ---------------- 人设 ----------------
    "default_persona": {
        "type": "textarea", "label": "默认人设（第一层）", "group": "人设", "rows": 6,
        "path": "default_persona",
        "help": "留空使用内置人设；占位符 {依星}/{羽笙}/{bot_display}/{bot_name} 会替换成当前机器人名",
    },
    "user_persona": {
        "type": "textarea", "label": "自定义人格（第二层）", "group": "人设", "rows": 12,
        "path": "user_persona",
        "help": "拼在默认人设之后，用于深度角色扮演；留空则只用人设第一层",
    },
    "bot_name": {
        "type": "text", "label": "机器人名（AI 视角）", "group": "人设",
        "path": "bot_name",
        "help": "AI 眼里的机器人名；留空则取实例 config.json 的 BOT_NAME（当前配置文件里没有这一项）",
    },

    # ---------------- 指令（commands.*）----------------
    "cmd_enable": {
        "type": "text", "label": "开启伪人", "group": "指令",
        "path": "commands.enable", "default": "开启伪人",
        "help": "触发词：后缀匹配，仅主人可用；群内=开本群，私聊=开全局",
    },
    "cmd_disable": {
        "type": "text", "label": "关闭伪人", "group": "指令",
        "path": "commands.disable", "default": "关闭伪人",
        "help": "触发词：后缀匹配，仅主人可用；群内=关本群，私聊=关全局",
    },
    "cmd_switch_glm": {
        "type": "text", "label": "切换 GLM", "group": "指令",
        "path": "commands.switch_glm", "default": "切换glm",
        "help": "触发词：整条消息全等，仅主人可用",
    },
    "cmd_switch_glm_alt": {
        "type": "text", "label": "切换 GLM（备用词）", "group": "指令",
        "path": "commands.switch_glm_alt", "default": "用glm",
        "help": "触发词：整条消息全等，仅主人可用",
    },
    "cmd_switch_gemini": {
        "type": "text", "label": "切换 Gemini", "group": "指令",
        "path": "commands.switch_gemini", "default": "切换gemini",
        "help": "触发词：整条消息全等，仅主人可用",
    },
    "cmd_switch_gemini_alt": {
        "type": "text", "label": "切换 Gemini（备用词）", "group": "指令",
        "path": "commands.switch_gemini_alt", "default": "用gemini",
        "help": "触发词：整条消息全等，仅主人可用",
    },
    "cmd_current_model": {
        "type": "text", "label": "查看当前模型", "group": "指令",
        "path": "commands.current_model", "default": "当前模型",
        "help": "触发词：整条消息全等，仅主人可用",
    },
    "cmd_current_model_alt": {
        "type": "text", "label": "查看当前模型（备用词）", "group": "指令",
        "path": "commands.current_model_alt", "default": "用什么模型",
        "help": "触发词：整条消息全等，仅主人可用",
    },
    "cmd_clear_history": {
        "type": "text", "label": "清除会话历史", "group": "指令",
        "path": "commands.clear_history", "default": "清除历史",
        "help": "触发词：整条消息全等，仅主人可用（只清当前会话）",
    },
    "cmd_clear_history_alt": {
        "type": "text", "label": "清除会话历史（备用词1）", "group": "指令",
        "path": "commands.clear_history_alt", "default": "清空历史",
        "help": "触发词：整条消息全等，仅主人可用",
    },
    "cmd_clear_history_alt2": {
        "type": "text", "label": "清除会话历史（备用词2）", "group": "指令",
        "path": "commands.clear_history_alt2", "default": "清空记忆",
        "help": "触发词：整条消息全等，仅主人可用",
    },
    "cmd_clear_all": {
        "type": "text", "label": "清除所有历史", "group": "指令",
        "path": "commands.clear_all", "default": "清除所有历史",
        "help": "触发词：整条消息全等，仅主人可用（清空全部会话）",
    },
    "cmd_clear_all_alt": {
        "type": "text", "label": "清除所有历史（备用词1）", "group": "指令",
        "path": "commands.clear_all_alt", "default": "清空所有历史",
        "help": "触发词：整条消息全等，仅主人可用",
    },
    "cmd_clear_all_alt2": {
        "type": "text", "label": "清除所有历史（备用词2）", "group": "指令",
        "path": "commands.clear_all_alt2", "default": "清空所有记忆",
        "help": "触发词：整条消息全等，仅主人可用",
    },

    # ---------------- 回复模板（messages.*）----------------
    "msg_switch_glm": {
        "type": "text", "label": "切换 GLM 成功", "group": "回复模板",
        "path": "messages.switch_glm", "help": "无占位符",
    },
    "msg_switch_gemini": {
        "type": "text", "label": "切换 Gemini 成功", "group": "回复模板",
        "path": "messages.switch_gemini", "help": "无占位符",
    },
    "msg_current_model": {
        "type": "text", "label": "当前模型回复", "group": "回复模板",
        "path": "messages.current_model",
        "help": "占位符：{model} 模型名（花括号写法，勿改成方括号）",
    },
    "msg_history_cleared": {
        "type": "text", "label": "会话历史已清除", "group": "回复模板",
        "path": "messages.history_cleared", "help": "无占位符",
    },
    "msg_all_history_cleared": {
        "type": "text", "label": "全部历史已清除", "group": "回复模板",
        "path": "messages.all_history_cleared", "help": "无占位符",
    },
    "msg_no_reply": {
        "type": "text", "label": "无回复兜底", "group": "回复模板",
        "path": "messages.no_reply", "help": "AI 返回空内容时的兜底话术；无占位符",
    },
    "msg_whats_up": {
        "type": "text", "label": "打招呼", "group": "回复模板",
        "path": "messages.whats_up", "help": "只叫机器人名字时的回复；无占位符",
    },
    "msg_check_image": {
        "type": "text", "label": "看图提示", "group": "回复模板",
        "path": "messages.check_image", "help": "只发图片没配文字时的过渡语；无占位符",
    },

    # ---------------- 元数据（自动生成/只读）----------------
    "command_labels": {
        "type": "json", "label": "指令标签映射", "group": "其它",
        "path": "command_labels", "advanced": True, "readonly": True, "rows": 8,
        "help": "插件启动时自动写入的「触发词 → 指令中文名」映射，供面板显示可读名称；只读",
    },
    "_note": {
        "type": "textarea", "label": "文件说明（只读）", "group": "其它",
        "path": "_note", "advanced": True, "readonly": True, "rows": 3,
        "help": "配置文件里的备注行，插件只透传不读取；只读，避免误改",
    },
}
