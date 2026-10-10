__config_schema__ = {
    # ---------------- 基础参数（顶层平铺）----------------
    "enabled": {
        "type": "bool", "label": "插件总开关", "group": "参数",
        "path": "enabled",
        "help": "全局总开关，关闭后所有群都不再解析（分群开关见「群组管理」）",
    },
    "show_download_fail_tip": {
        "type": "bool", "label": "下载失败时提示", "group": "参数",
        "path": "show_download_fail_tip",
        "help": "解析成功但下载失败时，是否在群里提示一句",
    },
    "audio_to_file": {
        "type": "bool", "label": "音频以文件发送", "group": "参数",
        "path": "audio_to_file",
        "help": "关闭时音频按语音发送，开启时按文件发送（避免语音被压缩）",
    },
    "debounce_seconds": {
        "type": "number", "label": "解析防抖间隔", "group": "参数",
        "path": "debounce_seconds", "min": 0, "max": 600, "step": 1, "unit": "秒",
        "help": "同一会话里相同链接/资源在该时间内不重复解析，0=关闭防抖",
    },

    # ---------------- 表情回应（解析命中后回一个表情）----------------
    "react_on_start": {
        "type": "bool", "label": "命中链接时回表情", "group": "表情回应",
        "path": "react_on_start",
        "help": "解析核心确认命中受支持链接后，给触发消息回一个表情（告知正在解析）",
    },
    "react_emoji_ids": {
        "type": "list", "item_type": "number", "label": "表情池", "group": "表情回应",
        "path": "react_emoji_ids",
        "help": "每次随机抽一个的 QQ 表情 ID 列表（如 128064=👀、128269=🔍、129300=🤔）；留空回退旧单值键",
    },
    "react_emoji_id": {
        "type": "number", "label": "表情 ID（旧版单值）", "group": "表情回应", "advanced": True,
        "path": "react_emoji_id", "min": 0, "max": 999999, "step": 1,
        "help": "旧版单值配置，仅在表情池为空时作为兜底；当前配置里存在此键但已不再优先使用",
    },
    "react_remove_if_no_link": {
        "type": "bool", "label": "非链接时撤销表情（未生效）", "group": "表情回应", "advanced": True,
        "path": "react_remove_if_no_link",
        "help": "历史遗留键：现在只有真正命中解析才回表情，不会误标，此键不再被读取",
    },

    # ---------------- 解析核心（16 平台）----------------
    "forward_threshold": {
        "type": "number", "label": "合并转发阈值", "group": "解析核心", "advanced": True,
        "path": "forward_threshold", "min": 1, "max": 50, "step": 1, "unit": "段",
        "help": "一条消息要发的内容段数达到该值就改用合并转发",
    },
    "proxy": {
        "type": "text", "label": "代理地址", "group": "解析核心", "advanced": True,
        "path": "proxy",
        "help": "给下载器/解析器用的代理，如 http://127.0.0.1:7890；留空不使用（YouTube 等需要）",
    },
    "browser_timeout": {
        "type": "number", "label": "下载超时", "group": "解析核心", "advanced": True,
        "path": "browser_timeout", "min": 5, "max": 600, "step": 5, "unit": "秒",
        "help": "单个资源下载的超时时间（若另配了 download_timeout，后者优先）",
    },
    "download_retry_times": {
        "type": "number", "label": "下载重试次数", "group": "解析核心", "advanced": True,
        "path": "download_retry_times", "min": 0, "max": 10, "step": 1, "unit": "次",
    },
    "download_max_size": {
        "type": "number", "label": "下载大小上限", "group": "解析核心", "advanced": True,
        "path": "download_max_size", "min": 1, "max": 4096, "step": 1, "unit": "MB",
        "help": "超过该大小的媒体不下载（防止群里被大文件拖死）",
    },
    "download_max_duration": {
        "type": "number", "label": "视频时长上限", "group": "解析核心", "advanced": True,
        "path": "download_max_duration", "min": 10, "max": 604800, "step": 10, "unit": "秒",
        "help": "超过该时长的视频不下载（上限放到 7 天，因为依星实例当前值是 360000 秒=100 小时）",
    },
    "bili_video_quality": {
        "type": "select", "label": "B站画质", "group": "解析核心", "advanced": True,
        "path": "bili_video_quality",
        "options": ["P_360P", "P_480P", "P_720P", "P_1080P"],
        "help": "越高越清晰、下载越慢；部分高画质需要大会员 Cookie",
    },
    "bili_video_codec": {
        "type": "select", "label": "B站编码", "group": "解析核心", "advanced": True,
        "path": "bili_video_codec",
        "options": ["AVC", "HEVC", "AV1"],
        "help": "AVC 兼容性最好（QQ 播放稳妥）",
    },
    "douyin_cookie": {
        "type": "password", "label": "抖音 Cookie", "group": "凭证", "advanced": True,
        "path": "douyin_cookie",
        "help": "从浏览器复制的抖音 Cookie，用于去水印/高码率；失效后需重新复制",
    },
    "bili_cookie": {
        "type": "password", "label": "B站 Cookie", "group": "凭证", "advanced": True,
        "path": "bili_cookie",
        "help": "含 SESSDATA 的 B站 Cookie，用于绕过 412 风控；也可发「B站登录」扫码（扫码结果存在共享 cookie 池）",
    },

    # ---------------- 历史遗留/核心兼容键（均未被使用或仅核心识别）----------------
    "auto_send_video": {
        "type": "bool", "label": "自动发送视频（未生效）", "group": "其它", "advanced": True,
        "path": "auto_send_video",
        "help": "插件会把它写回配置文件但当前解析核心不读取，保留兼容",
    },
    "auto_send_images": {
        "type": "bool", "label": "自动发送图片（未生效）", "group": "其它", "advanced": True,
        "path": "auto_send_images",
        "help": "插件会把它写回配置文件但当前解析核心不读取，保留兼容",
    },
    "merge_images": {
        "type": "bool", "label": "合并图片（未生效）", "group": "其它", "advanced": True,
        "path": "merge_images",
        "help": "配置文件里存在但当前解析核心不读取（是否合并转发由 forward_threshold 决定）",
    },
    "max_images": {
        "type": "number", "label": "最大图片数（未生效）", "group": "其它", "advanced": True,
        "path": "max_images", "min": 1, "max": 200, "step": 1, "unit": "张",
        "help": "配置文件里存在但当前解析核心不读取，保留兼容",
    },
    "show_source": {
        "type": "bool", "label": "显示来源（未生效）", "group": "其它", "advanced": True,
        "path": "show_source",
        "help": "配置文件里存在但当前解析核心不读取，保留兼容",
    },
    "at_reply": {
        "type": "bool", "label": "@触发者（未生效）", "group": "其它", "advanced": True,
        "path": "@_reply",
        "help": "配置里的键名是 @_reply（字段名不能带 @，故用 path 指回）；当前解析核心不读取",
    },
    "parse_timeout": {
        "type": "number", "label": "解析总时长上限", "group": "参数", "advanced": True,
        "path": "parse_timeout", "min": 30, "max": 3600, "step": 30, "unit": "秒",
        "help": "解析+下载+合并+发送 的总时长。网络慢或视频大时必须放宽，否则会报「解析失败」；"
                "超时不会取消后台下载，因此还可能出现「先提示失败、稍后又发出视频」",
    },
    "download_parallel": {
        "type": "number", "label": "分段下载路数", "group": "参数", "advanced": True,
        "path": "download_parallel",
        "default": 8, "min": 1, "max": 16, "step": 1, "unit": "路",
        "help": "大文件改用多连接 Range 分段下载（1=单连接）。单连接被 CDN 限速时 8 路能快一个数量级；"
                "服务端不支持 Range 会自动回退单连接，断了只补那一段",
    },
    "cache_cleanup_enabled": {
        "type": "bool", "label": "自动清理解析缓存", "group": "缓存",
        "path": "cache_cleanup_enabled",
        "default": True,
        "help": "解析下载的中间文件只增不减（线上曾到 11GB），开启后按下面的天数/大小周期清理",
    },
    "cache_max_age_days": {
        "type": "number", "label": "缓存保留天数", "group": "缓存",
        "path": "cache_max_age_days",
        "default": 7, "min": 0, "max": 365, "step": 1, "unit": "天",
        "help": "超过这个天数的缓存会被删除；0 = 不按时间清理。最近 1 小时动过的文件永不删",
    },
    "cache_max_size_mb": {
        "type": "number", "label": "缓存大小上限", "group": "缓存",
        "path": "cache_max_size_mb",
        "default": 2048, "min": 0, "max": 102400, "step": 128, "unit": "MB",
        "help": "缓存总量超过上限时，从最旧的文件开始删到上限的 90%；0 = 不按大小清理",
    },
    "cache_cleanup_interval_hours": {
        "type": "number", "label": "清理间隔", "group": "缓存", "advanced": True,
        "path": "cache_cleanup_interval_hours",
        "default": 6, "min": 1, "max": 168, "step": 1, "unit": "小时",
        "help": "多久检查清理一次（启动后先等 90 秒再清第一次）",
    },
    "download_timeout": {
        "type": "number", "label": "下载超时（核心别名）", "group": "其它", "advanced": True,
        "path": "download_timeout", "min": 5, "max": 3600, "step": 5, "unit": "秒",
        "help": "解析核心 config.py 也会读这个键；与 browser_timeout 同时存在时以本键为准",
    },
    "source_max_size": {
        "type": "number", "label": "大小上限（核心别名）", "group": "其它", "advanced": True,
        "path": "source_max_size", "min": 1, "max": 4096, "step": 1, "unit": "MB",
        "help": "解析核心 config.py 也会读这个键；与 download_max_size 同时存在时以本键为准",
    },
    "common_timeout": {
        "type": "number", "label": "接口超时（核心别名）", "group": "其它", "advanced": True,
        "path": "common_timeout", "min": 5, "max": 600, "step": 5, "unit": "秒",
        "help": "解析核心请求各平台接口用的超时（知乎/小黑盒/ pixiv 等）",
    },
    "single_heavy_render_card": {
        "type": "bool", "label": "单媒体渲染卡片（核心）", "group": "其它", "advanced": True,
        "path": "single_heavy_render_card",
        "help": "解析核心的开关，默认关闭（暂未启用该功能）",
    },
    "require_at_in_group": {
        "type": "bool", "label": "群里必须@才解析（核心）", "group": "其它", "advanced": True,
        "path": "require_at_in_group",
        "help": "解析核心的开关；注意：插件侧的群聊过滤在核心之前，当前实际由分群开关控制",
    },
    "command_labels": {
        "type": "json", "label": "指令标签映射", "group": "其它",
        "path": "command_labels", "advanced": True, "readonly": True, "rows": 4,
        "help": "插件启动时自动写入的「触发词 → 指令中文名」映射（开启/关闭视频解析、B站登录）；只读",
    },
}
