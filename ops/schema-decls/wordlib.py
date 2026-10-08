__config_schema__ = {
    # ---------------- 指令关键词（commands.*）----------------
    "cmd_add": {
        "type": "text", "label": "添加词条", "group": "指令",
        "path": "commands.add", "default": "依星跟我学",
        "help": "触发词：前缀匹配（消息以此开头即进入添加词条流程）",
    },
    "cmd_add_fuzzy": {
        "type": "text", "label": "添加模糊词条", "group": "指令",
        "path": "commands.add_fuzzy", "default": "添加模糊词条",
        "help": "触发词：前缀匹配（消息包含关键词即回复）",
    },
    "cmd_delete": {
        "type": "text", "label": "删除词条", "group": "指令",
        "path": "commands.delete", "default": "依星忘掉",
        "help": "触发词：前缀匹配，支持「关键词」「关键词 序号」「序号」三种写法",
    },
    "cmd_query": {
        "type": "text", "label": "查询词条", "group": "指令",
        "path": "commands.query", "default": "依星回忆一下",
        "help": "触发词：前缀匹配，查询词库列表或某个关键词的详情",
    },
    "cmd_encode": {
        "type": "text", "label": "消息转码", "group": "指令",
        "path": "commands.encode", "default": "转码",
        "help": "触发词：整条消息全等（exact）",
    },
    "cmd_sign1": {
        "type": "text", "label": "每日签到（1）", "group": "指令",
        "path": "commands.sign1", "default": "依星签到",
        "help": "触发词：整条消息全等；两个签到词任意一个都算签到",
    },
    "cmd_sign2": {
        "type": "text", "label": "每日签到（2）", "group": "指令",
        "path": "commands.sign2", "default": "签到",
        "help": "触发词：整条消息全等；留空则只保留另一个签到词",
    },
    "cmd_nickname": {
        "type": "text", "label": "设置昵称", "group": "指令",
        "path": "commands.nickname", "default": "依星以后叫我",
        "help": "触发词：前缀匹配，消耗好感度设置自定义昵称",
    },
    "cmd_rank": {
        "type": "text", "label": "签到排行", "group": "指令",
        "path": "commands.rank", "default": "签到排行",
        "help": "触发词：整条消息全等",
    },
    "cmd_praise1": {
        "type": "text", "label": "赞我", "group": "指令",
        "path": "commands.praise1", "default": "依星赞我",
        "help": "触发词：整条消息全等（让机器人给发送者点赞）",
    },
    "cmd_enable": {
        "type": "text", "label": "开启词库", "group": "指令",
        "path": "commands.enable", "default": "开启词库",
        "help": "触发词：后缀匹配，仅主人可用；群内=开本群，私聊=开全局",
    },
    "cmd_disable": {
        "type": "text", "label": "关闭词库", "group": "指令",
        "path": "commands.disable", "default": "关闭词库",
        "help": "触发词：后缀匹配，仅主人可用；群内=关本群，私聊=关全局",
    },

    # ---------------- 参数（settings.*）----------------
    "setting_enabled": {
        "type": "bool", "label": "插件总开关", "group": "参数",
        "path": "settings.enabled",
        "help": "全局总开关，关闭后所有群都不再响应（分群开关见「群组管理」）",
    },
    "setting_favor_add_max": {
        "type": "number", "label": "签到好感度上限", "group": "参数",
        "path": "settings.favor_add_max", "min": 0, "max": 100, "step": 1,
        "help": "每次签到随机增加的好感度上限（下限在源码里固定为 0）",
    },
    "setting_favor_minus_max": {
        "type": "number", "label": "重复签到扣分上限", "group": "参数",
        "path": "settings.favor_minus_max", "min": 0, "max": 100, "step": 1,
        "help": "当天重复签到时随机扣除的好感度上限（下限固定为 0）",
    },
    "setting_nickname_need_favor": {
        "type": "number", "label": "设置昵称所需好感度", "group": "参数",
        "path": "settings.nickname_need_favor", "min": 0, "max": 100000, "step": 1,
        "help": "好感度达到该值才允许改昵称",
    },
    "setting_rank_top_n": {
        "type": "number", "label": "排行榜显示人数", "group": "参数",
        "path": "settings.rank_top_n", "min": 1, "max": 100, "step": 1, "unit": "人",
    },
    "setting_praise_count": {
        "type": "number", "label": "点赞次数", "group": "参数",
        "path": "settings.praise_count", "min": 1, "max": 100, "step": 1, "unit": "次",
        "help": "「赞我」每次给发送者点的赞数",
    },
    "setting_encode_timeout": {
        "type": "number", "label": "转码等待超时", "group": "参数", "advanced": True,
        "path": "settings.encode_timeout", "min": 10, "max": 3600, "step": 10, "unit": "秒",
        "help": "发出「转码」后等待用户发内容的最长时间",
    },
    "setting_favor_add_min": {
        "type": "number", "label": "签到好感度下限（未生效）", "group": "参数", "advanced": True,
        "path": "settings.favor_add_min", "min": 0, "max": 100, "step": 1,
        "help": "文件里存在但当前源码把下限写死为 0，此键暂不被读取，仅保留兼容",
    },
    "setting_favor_minus_min": {
        "type": "number", "label": "重复签到扣分下限（未生效）", "group": "参数", "advanced": True,
        "path": "settings.favor_minus_min", "min": 0, "max": 100, "step": 1,
        "help": "文件里存在但当前源码把下限写死为 0，此键暂不被读取，仅保留兼容",
    },

    # ---------------- 管理员 ----------------
    "admins": {
        "type": "list", "item_type": "text", "label": "管理员 QQ", "group": "管理员",
        "path": "admins",
        "help": "管理员可在群内增删/查询词条（主人始终拥有全部权限）；一项一个 QQ 号，按现有配置存为字符串",
    },

    # ---------------- 回复模板（messages.*）----------------
    "msg_sign_success": {
        "type": "text", "label": "签到成功", "group": "回复模板",
        "path": "messages.sign_success",
        "help": "占位符：[add] 增加的好感度、[favor] 当前好感度",
    },
    "msg_sign_already": {
        "type": "text", "label": "今日已签到", "group": "回复模板",
        "path": "messages.sign_already",
        "help": "占位符：[minus] 扣除的好感度、[favor] 当前好感度",
    },
    "msg_nickname_set": {
        "type": "text", "label": "昵称设置成功", "group": "回复模板",
        "path": "messages.nickname_set",
        "help": "占位符：[nick] 新昵称",
    },
    "msg_nickname_fail": {
        "type": "text", "label": "好感度不足", "group": "回复模板",
        "path": "messages.nickname_fail",
        "help": "占位符：[need] 还差多少好感度",
    },
    "msg_nickname_format_error": {
        "type": "text", "label": "昵称格式错误", "group": "回复模板",
        "path": "messages.nickname_format_error",
        "help": "无占位符",
    },
    "msg_nickname_empty": {
        "type": "text", "label": "昵称为空", "group": "回复模板",
        "path": "messages.nickname_empty", "help": "无占位符",
    },
    "msg_praise_success": {
        "type": "text", "label": "点赞成功", "group": "回复模板",
        "path": "messages.praise_success", "help": "占位符：[count] 点赞次数",
    },
    "msg_praise_already": {
        "type": "text", "label": "今日已点赞", "group": "回复模板",
        "path": "messages.praise_already", "help": "无占位符",
    },
    "msg_praise_fail": {
        "type": "text", "label": "点赞失败", "group": "回复模板",
        "path": "messages.praise_fail", "help": "无占位符",
    },
    "msg_rank_empty": {
        "type": "text", "label": "排行榜为空", "group": "回复模板",
        "path": "messages.rank_empty", "help": "无占位符",
    },
    "msg_rank_title": {
        "type": "text", "label": "排行榜标题", "group": "回复模板",
        "path": "messages.rank_title",
        "help": "占位符：[top] 实际展示的人数；末尾可用 [next] 让后续内容另发一条",
    },
    "msg_rank_item": {
        "type": "text", "label": "排行榜条目", "group": "回复模板",
        "path": "messages.rank_item",
        "help": "占位符：[idx] 名次、[name] 昵称、[uid] QQ、[total] 签到次数",
    },
    "msg_add_step1": {
        "type": "text", "label": "添加词条-步骤1", "group": "回复模板",
        "path": "messages.add_step1", "help": "无占位符（提示输入关键词）",
    },
    "msg_add_step2": {
        "type": "text", "label": "添加词条-步骤2", "group": "回复模板",
        "path": "messages.add_step2", "help": "无占位符（提示输入回答内容）",
    },
    "msg_add_step3": {
        "type": "textarea", "label": "添加词条-步骤3", "group": "回复模板",
        "path": "messages.add_step3", "rows": 4,
        "help": "无占位符（提示选择精准/模糊匹配，支持换行）",
    },
    "msg_add_success_exact": {
        "type": "text", "label": "添加成功（精准）", "group": "回复模板",
        "path": "messages.add_success_exact",
        "help": "占位符：[keyword] 关键词、[count] 该关键词现有回复数",
    },
    "msg_add_success_fuzzy": {
        "type": "text", "label": "添加成功（模糊）", "group": "回复模板",
        "path": "messages.add_success_fuzzy",
        "help": "占位符：[keyword] 关键词、[count] 该关键词现有回复数",
    },
    "msg_add_format_error": {
        "type": "text", "label": "添加格式错误", "group": "回复模板",
        "path": "messages.add_format_error", "help": "占位符：[cmd] 实际使用的添加指令词",
    },
    "msg_add_empty": {
        "type": "text", "label": "添加内容为空", "group": "回复模板",
        "path": "messages.add_empty", "help": "无占位符",
    },
    "msg_keyword_empty": {
        "type": "text", "label": "关键词为空", "group": "回复模板",
        "path": "messages.keyword_empty", "help": "无占位符",
    },
    "msg_reply_empty": {
        "type": "text", "label": "回答为空", "group": "回复模板",
        "path": "messages.reply_empty", "help": "无占位符",
    },
    "msg_mode_invalid": {
        "type": "text", "label": "匹配模式无效", "group": "回复模板",
        "path": "messages.mode_invalid", "help": "无占位符",
    },
    "msg_delete_success": {
        "type": "text", "label": "删除成功", "group": "回复模板",
        "path": "messages.delete_success", "help": "占位符：[keyword] 被删除的关键词",
    },
    "msg_delete_reply_success": {
        "type": "text", "label": "删除回复成功", "group": "回复模板",
        "path": "messages.delete_reply_success",
        "help": "占位符：[keyword] 关键词、[idx] 回复序号、[content] 被删内容",
    },
    "msg_delete_not_found": {
        "type": "text", "label": "关键词不存在", "group": "回复模板",
        "path": "messages.delete_not_found", "help": "占位符：[keyword] 关键词",
    },
    "msg_delete_idx_invalid": {
        "type": "text", "label": "序号无效", "group": "回复模板",
        "path": "messages.delete_idx_invalid", "help": "占位符：[count] 当前关键词总数",
    },
    "msg_delete_reply_idx_invalid": {
        "type": "text", "label": "回复序号无效", "group": "回复模板",
        "path": "messages.delete_reply_idx_invalid", "help": "占位符：[count] 当前关键词的回复条数",
    },
    "msg_delete_idx_must_number": {
        "type": "text", "label": "序号必须是数字", "group": "回复模板",
        "path": "messages.delete_idx_must_number", "help": "无占位符",
    },
    "msg_delete_idx_positive": {
        "type": "text", "label": "序号必须为正整数", "group": "回复模板",
        "path": "messages.delete_idx_positive", "help": "无占位符",
    },
    "msg_delete_format_error": {
        "type": "text", "label": "删除格式错误", "group": "回复模板",
        "path": "messages.delete_format_error", "help": "占位符：[cmd] 实际使用的删除指令词",
    },
    "msg_wordlib_empty": {
        "type": "text", "label": "词库为空", "group": "回复模板",
        "path": "messages.wordlib_empty", "help": "无占位符",
    },
    "msg_query_list_title": {
        "type": "text", "label": "词库列表标题", "group": "回复模板",
        "path": "messages.query_list_title",
        "help": "无占位符；末尾可用 [next] 让列表另发一条",
    },
    "msg_query_list_item": {
        "type": "text", "label": "词库列表条目", "group": "回复模板",
        "path": "messages.query_list_item",
        "help": "占位符：[idx] 序号、[keyword] 关键词、[count] 回复条数",
    },
    "msg_query_detail_title": {
        "type": "text", "label": "词条详情标题", "group": "回复模板",
        "path": "messages.query_detail_title",
        "help": "占位符：[keyword] 关键词、[count] 回复条数",
    },
    "msg_query_detail_item": {
        "type": "text", "label": "词条详情条目", "group": "回复模板",
        "path": "messages.query_detail_item",
        "help": "占位符：[idx] 序号、[mode] 匹配模式、[content] 回复内容",
    },
    "msg_query_no_reply": {
        "type": "text", "label": "关键词暂无回复", "group": "回复模板",
        "path": "messages.query_no_reply", "help": "占位符：[keyword] 关键词",
    },
    "msg_encode_start": {
        "type": "text", "label": "转码开始提示", "group": "回复模板",
        "path": "messages.encode_start", "help": "无占位符",
    },
    "msg_encode_result": {
        "type": "text", "label": "转码结果", "group": "回复模板",
        "path": "messages.encode_result", "help": "占位符：[code] 转码后的可复制文本",
    },
    "msg_encode_timeout": {
        "type": "text", "label": "转码超时", "group": "回复模板",
        "path": "messages.encode_timeout", "help": "无占位符",
    },

    # ---------------- 元数据（自动生成/只读）----------------
    "command_labels": {
        "type": "json", "label": "指令标签映射", "group": "其它",
        "path": "command_labels", "advanced": True, "readonly": True, "rows": 6,
        "help": "插件启动时自动写入的「触发词 → 指令中文名」映射，供面板显示可读名称；只读",
    },
    "_note": {
        "type": "textarea", "label": "文件说明（只读）", "group": "其它",
        "path": "_note", "advanced": True, "readonly": True, "rows": 3,
        "help": "配置文件顶部的备注行，插件只透传不读取；只读，避免误改",
    },
}
