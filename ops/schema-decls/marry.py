__config_schema__ = {
    # ---------------- 指令关键词（commands.*）----------------
    "cmd_enable": {
        "type": "text", "label": "开启结婚", "group": "指令",
        "path": "commands.enable", "default": "开启结婚",
        "help": "触发词：后缀匹配，仅主人可用；群内=开本群，私聊=开全局",
    },
    "cmd_disable": {
        "type": "text", "label": "关闭结婚", "group": "指令",
        "path": "commands.disable", "default": "关闭结婚",
        "help": "触发词：后缀匹配，仅主人可用；群内=关本群，私聊=关全局",
    },
    "cmd_set_prob": {
        "type": "text", "label": "设置结婚概率", "group": "指令",
        "path": "commands.set_prob", "default": "设置结婚概率",
        "help": "触发词：前缀匹配，仅主人可用，用法「设置结婚概率 80」",
    },
    "cmd_set_cd": {
        "type": "text", "label": "设置离婚CD", "group": "指令",
        "path": "commands.set_cd", "default": "设置离婚CD",
        "help": "触发词：前缀匹配，仅主人可用，用法「设置离婚CD 24」",
    },
    "cmd_marry": {
        "type": "text", "label": "娶群友", "group": "指令",
        "path": "commands.marry", "default": "娶群友",
        "help": "触发词：整条消息全等，随机娶一位群友",
    },
    "cmd_marry_f": {
        "type": "text", "label": "嫁群友", "group": "指令",
        "path": "commands.marry_f", "default": "嫁群友",
        "help": "触发词：整条消息全等，随机嫁给一位群友",
    },
    "cmd_marry_t": {
        "type": "text", "label": "指定娶", "group": "指令",
        "path": "commands.marry_t", "default": "娶",
        "help": "触发词：前缀匹配，后面必须 @ 一个人（如「娶 @某人」）",
    },
    "cmd_marry_ft": {
        "type": "text", "label": "指定嫁", "group": "指令",
        "path": "commands.marry_ft", "default": "嫁",
        "help": "触发词：前缀匹配，后面必须 @ 一个人（如「嫁 @某人」）",
    },
    "cmd_divorce": {
        "type": "text", "label": "闹离婚", "group": "指令",
        "path": "commands.divorce", "default": "闹离婚",
        "help": "触发词：整条消息全等",
    },
    "cmd_my_object": {
        "type": "text", "label": "我的对象", "group": "指令",
        "path": "commands.my_object", "default": "我的对象",
        "help": "触发词：整条消息全等，查看今天的对象（带头像）",
    },

    # ---------------- 参数（settings.*）----------------
    "setting_enabled": {
        "type": "bool", "label": "插件总开关", "group": "参数",
        "path": "settings.enabled",
        "help": "全局总开关，关闭后所有群都不再响应（分群开关见「群组管理」）",
    },
    "setting_success_rate": {
        "type": "number", "label": "结婚成功率", "group": "参数",
        "path": "settings.success_rate", "default": 80,
        "min": 0, "max": 100, "step": 1, "unit": "%",
        "help": "0=永远失败，100=必定成功；当前配置文件里没有这一项，属默认值",
    },
    "setting_divorce_cd_hours": {
        "type": "number", "label": "离婚冷却", "group": "参数",
        "path": "settings.divorce_cd_hours", "min": 0, "max": 720, "unit": "小时",
        "help": "离婚后要等多久才能再次离婚；允许小数（如 0.25 = 15 分钟），故未设置步长",
    },

    # ---------------- 回复模板（replies.*）----------------
    "reply_only_group": {
        "type": "text", "label": "仅群内可用", "group": "回复模板",
        "path": "replies.only_group", "default": "该功能只能在群内使用。", "help": "无占位符",
    },
    "reply_no_members": {
        "type": "text", "label": "取不到群成员", "group": "回复模板",
        "path": "replies.no_members", "default": "无法获取群成员列表，请稍后再试。", "help": "无占位符",
    },
    "reply_already_married": {
        "type": "text", "label": "今天已有对象", "group": "回复模板",
        "path": "replies.already_married", "default": "你今天已经有对象了，不能再次结婚。", "help": "无占位符",
    },
    "reply_no_one_left": {
        "type": "text", "label": "群内无人可选", "group": "回复模板",
        "path": "replies.no_one_left", "default": "群内所有其他成员今天都有对象了，明天再试吧。", "help": "无占位符",
    },
    "reply_self_marry": {
        "type": "text", "label": "不能娶嫁自己", "group": "回复模板",
        "path": "replies.self_marry", "default": "不能娶/嫁自己哦。", "help": "无占位符",
    },
    "reply_not_in_group": {
        "type": "text", "label": "对方不在本群", "group": "回复模板",
        "path": "replies.not_in_group", "default": "对方不在本群，无法结婚。", "help": "无占位符",
    },
    "reply_target_married": {
        "type": "text", "label": "对方已有对象", "group": "回复模板",
        "path": "replies.target_married", "default": "对方今天已经有对象了，不能娶/嫁。", "help": "无占位符",
    },
    "reply_failed": {
        "type": "text", "label": "表白失败", "group": "回复模板",
        "path": "replies.failed", "default": "表白失败，对方拒绝了你的求婚。", "help": "无占位符",
    },
    "reply_just_married": {
        "type": "text", "label": "你刚结过婚", "group": "回复模板",
        "path": "replies.just_married", "default": "你刚刚已经结婚了，请稍后再试。", "help": "无占位符",
    },
    "reply_target_just_married": {
        "type": "text", "label": "对方刚结过婚", "group": "回复模板",
        "path": "replies.target_just_married", "default": "对方刚刚有了对象，请稍后再试。", "help": "无占位符",
    },
    "reply_divorce_cooldown": {
        "type": "text", "label": "离婚冷却中", "group": "回复模板",
        "path": "replies.divorce_cooldown", "default": "你刚刚离过婚，请等待 {hours} 小时 {minutes} 分钟后再离婚。",
        "help": "占位符：{hours} 剩余小时、{minutes} 剩余分钟（花括号写法，勿改成方括号）",
    },
    "reply_no_divorce": {
        "type": "text", "label": "今天没有对象", "group": "回复模板",
        "path": "replies.no_divorce", "default": "你今天都没有对象，离什么婚？", "help": "无占位符",
    },
    "reply_divorce_success": {
        "type": "text", "label": "离婚成功", "group": "回复模板",
        "path": "replies.divorce_success", "default": "离婚成功，你可以重新开始新的恋情了。", "help": "无占位符",
    },
    "reply_no_object": {
        "type": "text", "label": "今天还没有对象", "group": "回复模板",
        "path": "replies.no_object", "default": "你今天还没有对象哦。", "help": "无占位符",
    },
    "reply_master_only": {
        "type": "text", "label": "仅主人（概率）", "group": "回复模板",
        "path": "replies.master_only", "default": "只有主人才能设置概率。", "help": "无占位符",
    },
    "reply_master_only_cd": {
        "type": "text", "label": "仅主人（CD）", "group": "回复模板",
        "path": "replies.master_only_cd", "default": "只有主人才能设置CD。", "help": "无占位符",
    },
    "reply_format_prob": {
        "type": "text", "label": "概率格式错误", "group": "回复模板",
        "path": "replies.format_prob", "default": "格式错误：设置结婚概率 数字", "help": "无占位符",
    },
    "reply_prob_range": {
        "type": "text", "label": "概率超出范围", "group": "回复模板",
        "path": "replies.prob_range", "default": "概率必须在0-100之间。", "help": "无占位符",
    },
    "reply_prob_set": {
        "type": "text", "label": "概率设置成功", "group": "回复模板",
        "path": "replies.prob_set", "default": "结婚成功率已设置为 {rate}%",
        "help": "占位符：{rate} 新概率（花括号写法）",
    },
    "reply_format_cd": {
        "type": "text", "label": "CD格式错误", "group": "回复模板",
        "path": "replies.format_cd", "default": "格式错误：设置离婚CD 小时", "help": "无占位符",
    },
    "reply_cd_non_neg": {
        "type": "text", "label": "CD不能为负", "group": "回复模板",
        "path": "replies.cd_non_neg", "default": "CD必须是非负数。", "help": "无占位符",
    },
    "reply_cd_set": {
        "type": "text", "label": "CD设置成功", "group": "回复模板",
        "path": "replies.cd_set", "default": "离婚CD已设置为 {hours} 小时",
        "help": "占位符：{hours} 新的冷却小时数（花括号写法）",
    },
    "reply_not_number": {
        "type": "text", "label": "请输入数字", "group": "回复模板",
        "path": "replies.not_number", "default": "请输入数字。", "help": "设置概率/CD 时输入非法共用一个模板",
    },

    # ---------------- 元数据（自动生成/只读）----------------
    "command_labels": {
        "type": "json", "label": "指令标签映射", "group": "其它",
        "path": "command_labels", "advanced": True, "readonly": True, "rows": 6,
        "help": "插件启动时自动写入的「触发词 → 指令中文名」映射，供面板显示可读名称；只读",
    },
}
