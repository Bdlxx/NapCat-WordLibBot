# 栖星 AsterCore · 插件配置 schema
#
# 目标（用户要求）：**插件可配置项由插件自己声明**，WebUI 只实现"字段类型 → 控件"这一套映射，
# 于是所有插件通吃，面板不用为任何一个插件写专用代码。
#
# 声明方式（两种，都很轻，且**纯增量**、不改任何行为）：
#   1) 模块级 `__config_schema__ = {...}`     ← 老插件（Linux 版）也能直接用，兼容层照样加载
#   2) `PluginMeta(config_schema={...})`      ← 类插件写在自己元信息里
# 模块级优先（更显眼、离代码近）。
#
# 没有声明的插件**不是黑屏**：按当前配置值自动推断（`infer_schema`），
# 面板会注明"这是推断的"，并永远保留 JSON 原文编辑作为兜底。
#
# 字段类型表（与需求给的映射一一对应）：
#   text 单行输入(maxlength,placeholder) · textarea 多行(rows) · number 数字(min,max,step)
#   bool 开关 · select 下拉(options) · multiselect 多选(options) · list 动态列表(item_type)
#   password 密码框(secret) · group_select 群号选择器 · color 颜色 · file 文件路径(accept)
# 扩展一种：json（嵌套对象/数组，给 video_parser 那类深配置用；推断出来的 dict 也走它）

from __future__ import annotations

import json
import logging
import re
from typing import Any

log = logging.getLogger("astercore.config_schema")

# ---- 类型与各自的额外字段（前端据此渲染控件；服务端据此校验） ----
SCALAR_TYPES = ("text", "textarea", "number", "bool", "select", "password",
                "group_select", "color", "file", "json")
FIELD_TYPES = SCALAR_TYPES + ("multiselect", "list")

# 每种类型允许的额外字段（多出来的会被忽略，避免拼错字段名却毫无反馈）
TYPE_EXTRA: dict[str, tuple[str, ...]] = {
    "text": ("maxlength", "placeholder"),
    "textarea": ("rows", "placeholder"),
    "number": ("min", "max", "step", "unit"),
    "bool": (),
    "select": ("options",),
    "multiselect": ("options", "max_items"),
    "list": ("item_type", "options", "min_items", "max_items"),
    "password": ("secret", "placeholder"),
    "group_select": ("multiple", "max_items"),
    "color": (),
    "file": ("accept",),
    "json": ("rows",),
}

# 通用字段（所有类型都认）
# path：值在配置文件里的位置（点号路径，如 "settings.favor_add_max"、"glm.api_key"）。
#       不写就等于字段名本身。Linux 版老插件的配置是分段的（commands/settings/messages），
#       面板要能把控件写回正确的那一段，所以字段名与存储位置必须能分开。
COMMON = ("label", "help", "default", "required", "advanced", "group",
          "readonly", "path")

# 推断 schema 时，"名字像密码"的键一律按 password 处理（避免 API Key 大喇喇显示在屏幕上）
SECRET_KEY_RE = re.compile(
    r"(secret|token|passwd|password|api[_-]?key|apikey|cookie|credential|access[_-]?key)",
    re.IGNORECASE)


class SchemaError(ValueError):
    """schema 本身写错了（插件作者的锅），调用方应记录并降级"""


# ---------------------------------------------------------------- 归一化

def normalize_options(raw: Any) -> list[dict[str, str]]:
    """options 支持三种写法：[{value,label}] / ["a","b"] / {"a":"甲","b":"乙"}"""
    out: list[dict[str, str]] = []
    if isinstance(raw, dict):
        for k, v in raw.items():
            out.append({"value": str(k), "label": str(v)})
    elif isinstance(raw, (list, tuple)):
        for item in raw:
            if isinstance(item, dict):
                if "value" not in item:
                    continue
                val = item["value"]
                out.append({"value": str(val),
                            "label": str(item.get("label", val))})
            else:
                out.append({"value": str(item), "label": str(item)})
    return out


def normalize_field(name: str, raw: Any) -> dict[str, Any]:
    """把一条字段声明归一化成前端可直接渲染的形状。

    容错策略：**单个字段写错不该让整页打不开** —— 能救的救（缺 type 按 text），
    救不了的（未知类型）抛 SchemaError 由上层跳过这一条并记录。
    """
    if isinstance(raw, str):
        # 简写：`"reply": "text"` 或 `"reply": "select"`
        raw = {"type": raw}
    if not isinstance(raw, dict):
        raise SchemaError(f"字段 {name!r} 的声明必须是 dict 或类型字符串")

    ftype = str(raw.get("type") or "text").strip().lower()
    if ftype not in FIELD_TYPES:
        raise SchemaError(f"字段 {name!r} 的类型 {ftype!r} 不支持"
                          f"（可用：{'/'.join(FIELD_TYPES)}）")

    field: dict[str, Any] = {"name": name, "type": ftype}
    field["label"] = str(raw.get("label") or name)
    for key in ("help", "placeholder", "unit", "accept", "group", "path"):
        if raw.get(key) not in (None, ""):
            field[key] = str(raw[key])
    if "path" in field:
        _check_path(field["path"], name)
    for key in ("required", "advanced", "readonly"):
        if raw.get(key):
            field[key] = True
    if "default" in raw:
        field["default"] = raw["default"]
    else:
        field["default"] = _default_for(ftype)

    for key in ("maxlength", "rows", "min", "max", "step",
                "min_items", "max_items"):
        if key in TYPE_EXTRA[ftype] and raw.get(key) is not None:
            try:
                field[key] = int(float(raw[key]))
            except (TypeError, ValueError):
                raise SchemaError(f"字段 {name!r} 的 {key} 必须是数字")

    # 数值字段的默认值必须落在 min/max 内：声明了 min=5 而默认是 0，
    # 会让用户"什么都不改直接保存"就吃到一条越界错误。
    if ftype == "number" and isinstance(field.get("default"), (int, float)):
        lo, hi = field.get("min"), field.get("max")
        if lo is not None and field["default"] < lo:
            field["default"] = lo
        if hi is not None and field["default"] > hi:
            field["default"] = hi

    if "options" in TYPE_EXTRA[ftype]:
        opts = normalize_options(raw.get("options"))
        if ftype in ("select", "multiselect") and not opts:
            raise SchemaError(f"字段 {name!r} 是 {ftype}，必须给 options")
        field["options"] = opts

    if ftype == "list":
        item_type = str(raw.get("item_type") or "text").strip().lower()
        if item_type not in SCALAR_TYPES:
            raise SchemaError(f"字段 {name!r} 的 item_type {item_type!r} 不支持")
        field["item_type"] = item_type
    if ftype == "password":
        # 规范：password 默认就是密文（secret: True），显式 false 可关掉
        field["secret"] = bool(raw.get("secret", True))
    if ftype == "group_select":
        field["multiple"] = bool(raw.get("multiple", True))

    # 拼错的额外字段名要能发现（否则"写了却没生效"）
    known = set(COMMON) | {"type"} | set(TYPE_EXTRA[ftype]) | {"options"}
    unknown = [k for k in raw if k not in known]
    if unknown:
        log.warning("字段 %s 有未识别的声明项 %s（已忽略）", name, unknown)
    return field


def _default_for(ftype: str) -> Any:
    return {"bool": False, "number": 0, "multiselect": [], "list": [],
            "json": {}, "group_select": []}.get(ftype, "")


# ------------------------------------------------- 值在配置里的位置（点号路径）

def _check_path(path: str, field_name: str) -> None:
    """path 合法性：非空段、点号分隔。写错了要让插件作者立刻知道。"""
    parts = path.split(".")
    if any(not p.strip() for p in parts):
        raise SchemaError(f"字段 {field_name!r} 的 path {path!r} 有空段（形如 settings.foo）")


def field_path(field: dict[str, Any]) -> str:
    """字段的存储位置：显式 path 优先，否则就是字段名本身。"""
    return str(field.get("path") or field["name"])


def get_path(values: Any, path: str) -> Any:
    """按点号路径取值；中途缺失返回 None（不抛异常 —— 插件可能刚升级还没写默认值）"""
    cur = values
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def has_path(values: Any, path: str) -> bool:
    cur = values
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False
        cur = cur[part]
    return True


def set_path(values: dict[str, Any], path: str, value: Any) -> None:
    """按点号路径写值，中间缺的层级自动建（dict）"""
    parts = path.split(".")
    cur = values
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def flatten_values(values: Any, prefix: str = "") -> dict[str, Any]:
    """把嵌套配置摊平成 {点号路径: 值}（只摊 dict，list 当作叶子）"""
    out: dict[str, Any] = {}
    if not isinstance(values, dict):
        return out
    for k, v in values.items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(flatten_values(v, key + "."))
        else:
            out[key] = v
    return out


def normalize_schema(raw: Any) -> tuple[dict[str, dict], list[str]]:
    """归一化整张 schema。返回 (字段表, 错误列表)；坏字段被跳过而不是整页失败。"""
    if not raw:
        return {}, []
    if not isinstance(raw, dict):
        return {}, [f"schema 必须是 dict，收到 {type(raw).__name__}"]
    fields: dict[str, dict] = {}
    errors: list[str] = []
    for name, decl in raw.items():
        key = str(name)
        try:
            fields[key] = normalize_field(key, decl)
        except SchemaError as e:
            errors.append(str(e))
            log.warning("跳过字段声明: %s", e)
    return fields, errors


# ---------------------------------------------------------------- 推断（未声明的插件）

def is_secret_key(name: str) -> bool:
    return bool(SECRET_KEY_RE.search(name or ""))


def infer_field(name: str, value: Any) -> dict[str, Any]:
    """按当前值推断字段类型 —— 让没声明 schema 的插件也能有表单。"""
    if isinstance(value, bool):
        return normalize_field(name, {"type": "bool"})
    if isinstance(value, (int, float)):
        return normalize_field(name, {"type": "number"})
    if isinstance(value, list):
        item_type = "text"
        for v in value:
            if isinstance(v, bool) or isinstance(v, (int, float, str)):
                item_type = ("bool" if isinstance(v, bool) else
                             "number" if isinstance(v, (int, float)) else "text")
                break
            if isinstance(v, (dict, list)):
                item_type = "json"
                break
        return normalize_field(name, {"type": "list", "item_type": item_type})
    if isinstance(value, dict):
        return normalize_field(name, {"type": "json"})
    # 字符串：名字像密钥就当密码框
    if is_secret_key(name):
        return normalize_field(name, {"type": "password"})
    if isinstance(value, str) and ("\n" in value or len(value) > 120):
        return normalize_field(name, {"type": "textarea"})
    return normalize_field(name, {"type": "text"})


def infer_schema(values: dict[str, Any]) -> dict[str, dict]:
    fields: dict[str, dict] = {}
    for name, value in (values or {}).items():
        try:
            fields[name] = infer_field(str(name), value)
        except SchemaError as e:               # 理论上不会发生
            log.warning("推断字段 %s 失败: %s", name, e)
    return fields


# ---------------------------------------------------------------- 取值/校验/合并

def coerce_value(field: dict[str, Any], value: Any) -> tuple[bool, Any, str]:
    """按字段类型把值转成插件真正该收到的东西。返回 (ok, 值, 错误)"""
    ftype = field["type"]
    name = field.get("label") or field["name"]

    if ftype == "bool":
        if isinstance(value, bool):
            return True, value, ""
        if isinstance(value, (int, float)):
            return True, bool(value), ""
        if isinstance(value, str):
            low = value.strip().lower()
            if low in ("true", "1", "yes", "on", "是"):
                return True, True, ""
            if low in ("false", "0", "no", "off", "否", ""):
                return True, False, ""
        return False, None, f"{name}：需要 true/false"

    if ftype == "number":
        if isinstance(value, bool):
            return False, None, f"{name}：需要数字"
        try:
            num = float(value)
        except (TypeError, ValueError):
            return False, None, f"{name}：需要数字"
        if float(num).is_integer():
            # 整数值一律存成 int：配置里出现 55.0 很别扭，插件做 == 比较与
            # 手改 JSON 的人都会觉得诡异（step 是 0.5 也不影响这一条）
            num = int(num)
        if field.get("min") is not None and num < field["min"]:
            return False, None, f"{name}：不能小于 {field['min']}"
        if field.get("max") is not None and num > field["max"]:
            return False, None, f"{name}：不能大于 {field['max']}"
        return True, num, ""

    if ftype in ("text", "textarea", "color", "file", "password", "json"):
        if ftype == "json":
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return True, {}, ""
                try:
                    return True, json.loads(text), ""
                except ValueError as e:
                    return False, None, f"{name}：JSON 格式错误（{e}）"
            if isinstance(value, (dict, list)):
                return True, value, ""
            return False, None, f"{name}：需要 JSON 对象/数组"
        if value is None:
            return True, "", ""
        if not isinstance(value, str):
            value = str(value)
        maxlen = field.get("maxlength")
        if maxlen and len(value) > maxlen:
            return False, None, f"{name}：最多 {maxlen} 个字符"
        return True, value, ""

    if ftype == "group_select":
        # 多选（默认）必须是**列表**：早期实现把它 str() 成 "['123']" 存进配置，
        # 插件读到的就不是群号列表了 —— 这类错只有在真存真读时才看得出来。
        if field.get("multiple", True):
            return _coerce_str_list(field, value, name)
        if value is None:
            return True, "", ""
        if isinstance(value, (list, tuple)):
            value = value[0] if value else ""
        return True, str(value), ""

    if ftype == "select":
        if value is None:
            return True, "", ""
        return True, str(value), ""

    if ftype in ("multiselect", "list"):
        if value is None:
            value = []
        if not isinstance(value, list):
            return False, None, f"{name}：需要列表"
        max_items = field.get("max_items")
        if max_items is not None and len(value) > max_items:
            return False, None, f"{name}：最多 {max_items} 项"
        if ftype == "multiselect":
            return _coerce_str_list(field, value, name)
        min_items = field.get("min_items")
        if min_items is not None and len(value) < min_items:
            return False, None, f"{name}：至少 {min_items} 项"
        if ftype == "list":
            item_field = {"name": field["name"], "type": field["item_type"],
                          "label": name}
            item_field.update({k: v for k, v in field.items()
                               if k in ("options", "min", "max", "step", "maxlength")})
            out = []
            for i, item in enumerate(value):
                ok, val, err = coerce_value(item_field, item)
                if not ok:
                    return False, None, f"{err}（第 {i + 1} 项）"
                out.append(val)
            return True, out, ""

    return True, value, ""


def _coerce_str_list(field: dict[str, Any], value: Any, name: str
                    ) -> tuple[bool, Any, str]:
    """转成字符串列表（多选控件/群号多选共用）"""
    if value is None:
        value = []
    if not isinstance(value, (list, tuple)):
        return False, None, f"{name}：需要列表"
    max_items = field.get("max_items")
    if max_items is not None and len(value) > max_items:
        return False, None, f"{name}：最多 {max_items} 项"
    return True, [str(v) for v in value], ""


def validate_and_merge(fields: dict[str, dict], current: dict[str, Any],
                       submitted: dict[str, Any],
                       *, strict: bool = True) -> tuple[bool, dict[str, Any], dict[str, str]]:
    """把表单提交的值合并进现有配置。

    三条铁律：
      1. **未在 schema 里声明的键原样保留**（用户在 JSON 里手写的、插件自加的都不能丢）
      2. 只有在 `strict=True`（插件声明了 schema）时才做类型转换与必填校验；
         推断出来的 schema 只用于渲染，不当法律用
      3. 每个字段的错误单独返回，前端能精确标红到控件

    写入位置由字段的 `path` 决定（缺省等于字段名）。**必须深拷贝**：分段配置
    （settings/commands/messages）里浅拷贝会让 set_path 改到调用方持有的那个子字典上。
    """
    import copy
    merged: dict[str, Any] = copy.deepcopy(current) if isinstance(current, dict) else {}
    before = current if isinstance(current, dict) else {}
    errors: dict[str, str] = {}
    if not isinstance(submitted, dict):
        return False, merged, {"_": "提交内容必须是对象"}

    for name, value in submitted.items():
        field = fields.get(name)
        if field is None:
            # 未声明的键：原样存（点号键按路径写入，与 build_payload 的 flat 视图一致）
            if "." in name:
                set_path(merged, name, value)
            else:
                merged[name] = value
            continue
        if field.get("readonly"):
            continue
        path = field_path(field)
        if not strict:
            set_path(merged, path, value)
            continue
        ok, val, err = coerce_value(field, value)
        if not ok:
            errors[name] = err
            continue
        # 配置文件里本来没有这一项、用户也没改动它（提交值就是声明里的默认值）→ 不写入。
        # 否则"打开面板点一次保存"就会把插件声明但从未使用过的键（超时、别名键等）
        # 以 0/空串的形式塞进配置，甚至改坏插件行为。
        if not has_path(before, path) and _same_value(val, field.get("default")):
            continue
        set_path(merged, path, val)

    if strict:
        for name, field in fields.items():
            # 必填只看**合并后的结果**：声明了 required 就必须有值（这是作者明确的意图，
            # 桌面端的既有语义与测试都钉住了它）。
            if field.get("required") and not _has_value(get_path(merged, field_path(field))):
                errors.setdefault(name, f"{field.get('label') or name}：必填")
    return (not errors), merged, errors


def _has_value(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    if isinstance(v, (list, dict)):
        return len(v) > 0
    return True


def _same_value(a: Any, b: Any) -> bool:
    """宽松相等：表单里数字是 int/float 混着来的，bool 与 0/1 也别判成"改过"。
    空串、None、空列表都视为"没设置"（声明里的默认值多是这些）。"""
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return float(a) == float(b)
    if a is None or b is None:
        return not _has_value(a) and not _has_value(b)
    if isinstance(a, str) and isinstance(b, str):
        return a.strip() == b.strip()
    return a == b


# ---------------------------------------------------------------- 对外汇总

def build_payload(declared_raw: Any, values: dict[str, Any]
                  ) -> dict[str, Any]:
    """给面板的一份完整数据：字段表 + 当前值 + 是声明还是推断 + schema 自身的问题"""
    declared_fields, decl_errors = normalize_schema(declared_raw)
    declared = bool(declared_raw)
    if declared and declared_fields:
        fields = declared_fields
    else:
        fields = infer_schema(values)
        if declared and not declared_fields:
            # 声明了但一条都没解析出来 → 退回推断，并如实告知
            declared = False
    out_fields = []
    for name, f in fields.items():
        f = dict(f)
        p = field_path(f)
        present = has_path(values, p)
        f["value"] = get_path(values, p) if present else f.get("default")
        # unset：配置文件里当前**没有**这一项（插件声明了它但还没写过）。面板据此提示，
        # 保存时也不会把声明里的默认值"落地"进配置文件（见 validate_and_merge）。
        f["unset"] = not present
        out_fields.append(f)
    return {
        "declared": declared,
        "fields": out_fields,
        "values": dict(values or {}),
        "flat": flatten_values(values),          # {点号路径: 值}，面板做 JSON 视图与脏值比对用
        "schema_errors": decl_errors,
        "types": list(FIELD_TYPES),
    }
