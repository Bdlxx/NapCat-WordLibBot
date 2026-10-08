__config_schema__ = {
    # ---------------- 指令关键词（commands.*）----------------
    "cmd_download": {
        "type": "text", "label": "下载本子", "group": "指令",
        "path": "commands.download", "default": "jm",
        "help": "触发词：前缀匹配，后面必须跟数字/本子 ID（如「jm 123456」「jm 123 p456」）",
    },
    "cmd_detail": {
        "type": "text", "label": "查看本子详情", "group": "指令",
        "path": "commands.detail", "default": "jm详情",
        "help": "触发词：前缀匹配，仅查看元信息不下载（如「jm详情 123456」）",
    },
    "cmd_enable": {
        "type": "text", "label": "开启JM下载", "group": "指令",
        "path": "commands.enable", "default": "开启jm下载",
        "help": "触发词：后缀匹配，仅主人可用；群内=开本群，私聊=开全局",
    },
    "cmd_disable": {
        "type": "text", "label": "关闭JM下载", "group": "指令",
        "path": "commands.disable", "default": "关闭jm下载",
        "help": "触发词：后缀匹配，仅主人可用；群内=关本群，私聊=关全局",
    },

    # ---------------- 参数（settings.*）----------------
    "setting_enabled": {
        "type": "bool", "label": "插件总开关", "group": "参数",
        "path": "settings.enabled",
        "help": "全局总开关，关闭后所有群都不再响应（分群开关见「群组管理」）",
    },
    "setting_send_pdf": {
        "type": "bool", "label": "发送 PDF", "group": "参数",
        "path": "settings.send_pdf",
        "help": "下载完成后把本子转成 PDF 发给群",
    },
    "setting_delete_after_send": {
        "type": "bool", "label": "发送后清理文件", "group": "参数",
        "path": "settings.delete_after_send",
        "help": "发送成功后删除本地下载的图片/PDF",
    },
    "setting_auto_update": {
        "type": "bool", "label": "自动更新 jmcomic", "group": "参数",
        "path": "settings.auto_update",
        "help": "后台定时检查并升级实例 venv 里的 jmcomic 库",
    },
    "setting_recall_enabled": {
        "type": "bool", "label": "消息自动撤回", "group": "参数",
        "path": "settings.recall_enabled",
        "help": "开启后本插件发出的消息按下面的时间自动撤回（需 NapCat HTTP 可用）",
    },
    "setting_recall_notice": {
        "type": "bool", "label": "撤回前提醒", "group": "参数",
        "path": "settings.recall_notice",
        "help": "是否先发一条「将在 N 秒后撤回」的前置提醒",
    },
    "setting_recall_prefix_seconds": {
        "type": "number", "label": "前置消息撤回时间", "group": "参数",
        "path": "settings.recall_prefix_seconds", "min": 5, "max": 3600, "step": 1, "unit": "秒",
        "help": "查询/进度等前置消息的撤回延时",
    },
    "setting_recall_pdf_seconds": {
        "type": "number", "label": "PDF 提醒撤回时间", "group": "参数",
        "path": "settings.recall_pdf_seconds", "min": 5, "max": 3600, "step": 1, "unit": "秒",
        "help": "「PDF 已发送」这类提醒消息的撤回延时",
    },
    "setting_recall_file_seconds": {
        "type": "number", "label": "PDF 文件撤回时间", "group": "参数",
        "path": "settings.recall_file_seconds", "min": 5, "max": 86400, "step": 5, "unit": "秒",
        "help": "PDF 文件消息的撤回延时（上传耗时较长，通常比提醒宽松）",
    },
    "setting_debounce_seconds": {
        "type": "number", "label": "下载防抖间隔", "group": "参数",
        "path": "settings.debounce_seconds", "min": 0, "max": 3600, "step": 1, "unit": "秒",
        "help": "同会话相同链接/本子 ID 在该时间内不重复响应，0=关闭防抖",
    },
    "setting_update_interval_hours": {
        "type": "number", "label": "更新检查间隔", "group": "参数", "advanced": True,
        "path": "settings.update_interval_hours", "min": 1, "max": 720, "step": 1, "unit": "小时",
        "help": "自动更新 jmcomic 的检查周期",
    },
    "setting_task_timeout_seconds": {
        "type": "number", "label": "任务超时", "group": "参数", "advanced": True,
        "path": "settings.task_timeout_seconds", "min": 60, "max": 86400, "step": 60, "unit": "秒",
        "help": "单次下载子进程的最长存活时间，超时会被杀掉",
    },
    "setting_cleanup_delay_seconds": {
        "type": "number", "label": "清理延时", "group": "参数", "advanced": True,
        "path": "settings.cleanup_delay_seconds", "min": 0, "max": 7200, "step": 10, "unit": "秒",
        "help": "发送文件后延迟多久再删除本地文件（NapCat 是异步读文件，不能立即删；Windows 建议加大）",
    },
    "setting_concurrent_image": {
        "type": "number", "label": "并发下载图片数", "group": "参数", "advanced": True,
        "path": "settings.concurrent_image", "min": 1, "max": 100, "step": 1, "unit": "线程",
        "help": "传给 jmcomic 的单章节内图片并发数，过大易被站点限流",
    },
    "setting_concurrent_photo": {
        "type": "number", "label": "并发下载章节数", "group": "参数", "advanced": True,
        "path": "settings.concurrent_photo", "min": 1, "max": 100, "step": 1, "unit": "线程",
        "help": "同时下载的章节数",
    },
    "setting_download_dir": {
        "type": "text", "label": "下载目录", "group": "参数", "advanced": True,
        "path": "settings.download_dir",
        "help": "相对实例 data/ 的图片下载目录名（PDF 生成后临时放在 data/jm_pdf/）",
    },
    "setting_recall_seconds": {
        "type": "number", "label": "前置消息撤回时间（兜底）", "group": "参数", "advanced": True,
        "path": "settings.recall_seconds", "min": 5, "max": 3600, "step": 1, "unit": "秒",
        "help": "仅在 recall_prefix_seconds 缺失时作为兜底；正常配置下不生效",
    },

    # ---------------- 回复模板（messages.*）----------------
    "msg_usage": {
        "type": "textarea", "label": "用法提示", "group": "回复模板",
        "path": "messages.usage", "rows": 5,
        "help": "只发「jm」不带 ID 时显示；无占位符，支持换行",
    },
    "msg_busy": {
        "type": "text", "label": "任务进行中", "group": "回复模板",
        "path": "messages.busy", "help": "同一群已有任务时的提示；无占位符",
    },
    "msg_querying": {
        "type": "text", "label": "查询中", "group": "回复模板",
        "path": "messages.querying",
        "help": "占位符：{ids} 本次要处理的 ID 列表（花括号写法，勿改成方括号）",
    },
    "msg_no_pdf": {
        "type": "text", "label": "未生成 PDF", "group": "回复模板",
        "path": "messages.no_pdf", "help": "无占位符",
    },
    "msg_send_fail": {
        "type": "text", "label": "PDF 发送失败", "group": "回复模板",
        "path": "messages.send_fail",
        "help": "无占位符（插件会在其后自动追加一行本地文件路径）",
    },
    "msg_fail": {
        "type": "text", "label": "下载失败", "group": "回复模板",
        "path": "messages.fail", "help": "占位符：{err} 失败原因",
    },
    "msg_timeout": {
        "type": "text", "label": "下载超时", "group": "回复模板",
        "path": "messages.timeout", "help": "无占位符",
    },
    "msg_pdf_header": {
        "type": "textarea", "label": "PDF 分享说明", "group": "回复模板",
        "path": "messages.pdf_header", "rows": 3,
        "help": "占位符：{titles} 本子标题（顿号连接）；支持换行",
    },
    "msg_detail_header": {
        "type": "textarea", "label": "本子详情模板", "group": "回复模板",
        "path": "messages.detail_header", "rows": 7,
        "help": "占位符：{title} {album_id} {authors} {episodes} {pages} {tags} {update_date}；支持换行",
    },
    "msg_recall_notice": {
        "type": "text", "label": "撤回提醒", "group": "回复模板",
        "path": "messages.recall_notice",
        "help": "占位符：{prefix} 前置消息撤回秒数、{pdf} PDF 提醒撤回秒数",
    },
    "msg_recall_pdf_notice": {
        "type": "text", "label": "PDF 撤回提醒", "group": "回复模板",
        "path": "messages.recall_pdf_notice", "help": "占位符：{seconds} 秒后撤回",
    },

    # ---------------- 元数据（自动生成/只读）----------------
    "command_labels": {
        "type": "json", "label": "指令标签映射", "group": "其它",
        "path": "command_labels", "advanced": True, "readonly": True, "rows": 6,
        "help": "插件启动时自动写入的「触发词 → 指令中文名」映射（含未暴露为配置的「jm更新」），只读",
    },
}
