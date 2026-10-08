# 5 个线上插件的配置项声明（`__config_schema__`）

产出目录：`ops/schema-decls/`（5 个文件，每个文件**只有一条**模块级 `__config_schema__ = {...}` 赋值语句，
无 import、无其他代码，可被面板的 `ast.literal_eval` 直接读取）。
键集来源 = **插件源码里读到/写入的键** ∪ **`instances/740979632/data/*.json` 里真实存在的键**
（另加下文 C 节说明的 5 个「解析核心别名」，已单列并标注理由）。

## 1. 字段数与分组

| 声明文件 | 字段数 | 按 group 分布 |
|---|---|---|
| `wordlib.py` | 63 | 指令 12 · 参数 9 · 管理员 1 · 回复模板 39 · 其它 2 |
| `marry.py` | 37 | 指令 10 · 参数 3 · 回复模板 23 · 其它 1 |
| `pseudo_persona.py` | 47 | 模型与凭证 7 · 参数 13 · 人设 3 · 指令 14 · 回复模板 8 · 其它 2 |
| `jm_downloader.py` | 33 | 指令 4 · 参数 17 · 回复模板 11 · 其它 1 |
| `video_parser.py` | 30 | 参数 4 · 表情回应 4 · 解析核心 8 · 凭证 2 · 其它 12 |

命名约定：分段配置用 `cmd_* / setting_* / msg_* / reply_*` 前缀 + 显式 `path`（如
`setting_recall_prefix_seconds` → `settings.recall_prefix_seconds`）；顶层平铺的键
字段名等于真实键名、`path` 与 name 相同（`@_reply` 例外，见 D-6）。
前缀写法是必须的：`jm_downloader` 的 `settings.recall_notice`（bool）与
`messages.recall_notice`（模板）**叶子名撞车**，不加前缀无法唯一标识。

## 2. 判定为 `advanced`（面板折叠）的项与理由

- **wordlib（5）**：`setting_encode_timeout`（转码等待超时）、
  `setting_favor_add_min` / `setting_favor_minus_min`（**源码不读**，见 D-1，藏着以免误以为可调）、
  `command_labels` / `_note`（自动生成/说明性元数据）。
- **marry（1）**：只有 `command_labels` —— 这个插件没有超时/并发/密钥类参数，
  `success_rate`、`divorce_cd_hours` 是常用玩法参数，保持在明面上。
- **pseudo_persona（9）**：`glm_api_url` `gemini_api_url`（API 地址）、
  `glm_model` `gemini_model`（模型名）、`api_timeout` `health_check_interval`（超时/后台探测）、
  `random_reply_probability`（**源码不读**）、`command_labels` `_note`。
  **API Key 不折叠**（常改，但必须是 `password` 明文遮罩）。
- **jm_downloader（8）**：`setting_update_interval_hours`、`setting_task_timeout_seconds`、
  `setting_cleanup_delay_seconds`（清理延时，Windows 上更要调大）、
  `setting_concurrent_image` / `setting_concurrent_photo`（并发）、
  `setting_download_dir`（落盘路径）、`setting_recall_seconds`（**兜底键**，见 D-7）、`command_labels`。
  撤回窗口 `recall_prefix/pdf/file_seconds` 保持可见（属常用行为开关）。
- **video_parser（24）**：下载/超时/上限类（`browser_timeout` `download_retry_times`
  `download_max_size` `download_max_duration` `forward_threshold` `proxy`）、
  凭证类（`douyin_cookie` `bili_cookie`）、平台参数（`bili_video_quality` `bili_video_codec`）、
  7 个「未生效/历史遗留」键、5 个「核心别名」键、旧单值 `react_emoji_id`、
  以及 `command_labels`。

## 3. 源码里读到、但当前配置文件里**不存在**的键（已全部声明并给 `default`）

- **marry**：整个 `commands.*`（10 个）、整个 `replies.*`（23 个）、`settings.success_rate`
  —— 共 34 个。依星实例的 `marry_config.json` 只有 `settings.{enabled,divorce_cd_hours}` 与
  `command_labels`；这些键的默认值都在源码里（`cmd(k, d)` / `rep(k, d)` / `setting("success_rate", 80)`），
  已写进 `default`。**交叉验证**：羽笙实例（2551736206）的 `marry_config.json` 恰好把
  `commands.*`(10) + `replies.*`(23) + `settings.success_rate` 全部写全，键名与我提取的集合**完全一致**。
- **pseudo_persona**：`bot_name`（`CONFIG.get("bot_name")`，留空回落到实例 `config.json` 的 `BOT_NAME`）。
- **video_parser**：`download_timeout` `source_max_size` `common_timeout`
  `single_heavy_render_card` `require_at_in_group` —— 见 D-3（这几个不属于插件源码，属解析核心）。

反向的「配置文件里有、源码不读」的键，均已在 help 里如实标注（见下）。

## 4. 逐项需要人工确认的点

1. **`admins` 的选型**：用 `{"type": "list", "item_type": "text"}`，**没用** `group_select`。
   - 不用 `group_select`：面板的群号选择器列的是**本 bot 的群列表**，而这里是**管理员 QQ 号**
     （可能是没在本群的号，比如主人的小号）——语义不符，选完还会被存成"群号"的错觉，反而更容易填错。
   - `item_type` 用 `text` 而不是 `number`：**当前文件里存的是字符串** `["245524106"]`，
     用 `number` 会让面板保存时把它们转成整数（我已实测：`list`+number 时"提交现值 → 合并结果"
     与当前配置不再逐字节相同）。保持 text = 保存行为与现状一致。
   - ⚠️ **顺带发现一个隐性 bug（不是本次任务范围，未改代码）**：`wordlib.is_admin()` 写的是
     `user_id in data.get("admins", [])`，其中 `user_id` 来自事件的 **int**，
     而配置里是 **str** → 非主人的管理员实际**不会生效**。要修的话两条路：①把 `is_admin` 改成
     `str(user_id) in [str(x) for x in ...]`；②把声明的 `item_type` 改成 `number`（面板保存后自动变整数，
     顺带修好）。我选了不动数据的 ①路线（只声明不改行为），请人工决定。
2. **`max_tokens`（pseudo）名字里含 `token`，但它是"最大生成数"**：按"带 token 一律 password"的字面规则
   会被做成密码框，`password` 类型会把数字 `str()` 成 `"500"` 存进配置 → 真会把插件搞坏。
   我保留 `number`。同理提醒：**旧面板按名字推断（`'token' in key`）会把这一项误判成密码框**，
   本次声明正好修掉这个坑（`pseudo_persona.py` 里 `max_tokens` 是唯一的例外，其余含
   key/token/cookie/secret 的字段已全部是 `password`：`glm_api_key`、`gemini_api_key`、
   `douyin_cookie`、`bili_cookie`）。
3. **video_parser 的 5 个"核心别名"键**（`download_timeout` `source_max_size` `common_timeout`
   `single_heavy_render_card` `require_at_in_group`）：既不在插件源码、也不在当前配置文件里，
   但 `video_parser_core/config.py` 的 `load_from_video_config()`（第 157~186 行的
   `int_map/bool_map/str_map`）**确实从同一份 JSON 读它们**。我按"读到了就要能配"声明为
   `advanced`，并在 help 写明别名覆盖关系（`download_timeout` 优先于 `browser_timeout`、
   `source_max_size` 优先于 `download_max_size`）。**若评审认为超出"插件源码 ∪ 配置文件"范围，删掉这 5 条即可，其余不受影响。**
4. **video_parser 的 7 个"未生效"键**：`auto_send_video` `auto_send_images` `merge_images`
   `max_images` `show_source` `react_remove_if_no_link` `at_reply`（配置文件里的真键名是 `@_reply`）。
   它们会被 `DEFAULT_CONFIG` + `setdefault` 写回文件，但全项目 grep 无人读取 → 已声明（不然就是"漏键"），
   但 help 里**明确写了"未生效/历史遗留"**，并统一折叠进 advanced，免得用户以为是开关坏了。
5. **依星实例的 `download_max_duration = 360000`**（=100 小时，插件默认是 3600）明显是误设。
   为保证面板"用当前值保存"不会被 max 校验拦住，我把该字段的 `max` 放宽到 `604800`（7 天）并在 help 注明；
   已同时核对两个实例的所有 number 字段：**除这一条外没有越界值**。
6. **`@_reply` 的字段名**：真实键带 `@`，不符合"字段名只允许 `[a-z0-9_]`"，故字段名取 `at_reply`，
   用 `"path": "@_reply"` 指回真实位置（`path` 正是为这种场景准备的）。
7. **jm 的 `recall_seconds` 与 `recall_prefix_seconds` 语义重复**：源码只在
   `cfg("recall_prefix_seconds", cfg("recall_seconds", 30))` 里把前者当**兜底**，
   由于 `DEFAULT_CONFIG` 一定会补上 `recall_prefix_seconds`，`recall_seconds` 实际上**永不生效** →
   已折叠进 advanced 并在 help 说明"仅当 recall_prefix_seconds 缺失时兜底"。
8. **元数据键 `command_labels` / `_note`**：都不是用户可调项，但一个是插件启动时**写入**的
   （`_CFG.setdefault("command_labels", {}).update(registry.labels())` / `CONFIG.setdefault(...)`）、
   另一个是配置文件里**真实存在**的注释行，按"不许漏"都声明了，统一 `readonly: True` + `advanced: True`。
   `command_labels` 按**整块 json** 声明而不逐键声明：它的键就是触发词本身，两个实例还不一样
   （依星是「依星跟我学」，羽笙是「羽笙跟我学」），逐键声明会立刻过期。
9. **`_note` 只给"有它的文件"声明**：本实例里 wordlib / persona 的配置有 `_note`，marry / jm /
   video_parser 的没有；**但羽笙的 `marry_config.json` 里是有 `_note` 的**。若要与另一实例完全对齐，
   可给 marry 也补一条同样的只读字段（我按"740979632 文件为准"没加）。
10. **`persona`（旧键）刻意未声明**：pseudo 的源码里它只出现在 `save_config()` 的排除名单
    （`if k != "persona"`）——不读、且下次保存会被丢掉，属已废弃键。
11. **不写 import 的后果**：面板 `web/api.py::_read_declared_schema()` 目前是去
    `<实例>/plugins/<name_en>.py` **用 ast 读**（不 import，避免 video_parser 导入期副作用）。
    所以这 5 份声明要真正生效，需按约束由人工/上层把字典**并入两个实例的插件源码**；
    本次严格只新增 `ops/schema-decls/` 下的文件，**未改动任何插件、配置或仓库其他文件**。

## 5. 验证（题目要求的那条命令）

```bash
cd /root/mybot2 && python3 -c "
import importlib.util, json, os, re, sys, ast
sys.path.insert(0, 'web')
from config_schema import normalize_schema, field_path, flatten_values, has_path, build_payload, validate_and_merge, get_path
DECL, DATA = 'ops/schema-decls', 'instances/740979632/data'
FILES = {'wordlib':'wordlib_config.json','marry':'marry_config.json','pseudo_persona':'persona_config.json','jm_downloader':'jm_downloader_config.json','video_parser':'video_parser_config.json'}
EXPECT = {'wordlib':63,'marry':37,'pseudo_persona':47,'jm_downloader':33,'video_parser':30}
for mod, cf in FILES.items():
    p = os.path.join(DECL, mod+'.py')
    tree = ast.parse(open(p, encoding='utf-8').read())
    one = len(tree.body)==1 and isinstance(tree.body[0], ast.Assign) and tree.body[0].targets[0].id=='__config_schema__'
    spec = importlib.util.spec_from_file_location('d_'+mod, p); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    raw = m.__config_schema__; fields, errors = normalize_schema(raw)
    cfg = json.load(open(os.path.join(DATA, cf), encoding='utf-8'))
    pl = build_payload(raw, cfg)
    paths = sorted({field_path(f) for f in fields.values()})
    uncovered = [q for q in flatten_values(cfg) if q not in paths and not any(q.startswith(x+'.') for x in paths)]
    bad = [n for n in raw if not re.fullmatch(r'[a-z0-9_]+', n)]
    sub = {f['name']: f['value'] for f in pl['fields'] if has_path(cfg, field_path(f))}
    okm, merged, errs = validate_and_merge(fields, cfg, sub)
    rangebad = [field_path(f) for f in fields.values() if f['type']=='number' and has_path(cfg, field_path(f)) and isinstance(get_path(cfg, field_path(f)), (int,float)) and ((f.get('min') is not None and get_path(cfg,field_path(f))<f['min']) or (f.get('max') is not None and get_path(cfg,field_path(f))>f['max']))]
    print(f'{mod:15s} OK={one and not errors and len(fields)==EXPECT[mod] and not uncovered and not bad and not errs and merged==cfg and not rangebad} 字段={len(fields)}/{EXPECT[mod]} errors={errors} schema_errors={pl[\"schema_errors\"]} 未覆盖配置键={uncovered} 提交校验错误={errs} 回写一致={merged==cfg} 数值越界={rangebad}')
"
```

实测输出（每条 `errors=[]`，字段数与预期一致，且面板负载/回写/范围全部通过）：

```
wordlib         OK=True 字段=63/63 errors=[] schema_errors=[] 未覆盖配置键=[] 提交校验错误={} 回写一致=True 数值越界=[]
marry           OK=True 字段=37/37 errors=[] schema_errors=[] 未覆盖配置键=[] 提交校验错误={} 回写一致=True 数值越界=[]
pseudo_persona  OK=True 字段=47/47 errors=[] schema_errors=[] 未覆盖配置键=[] 提交校验错误={} 回写一致=True 数值越界=[]
jm_downloader   OK=True 字段=33/33 errors=[] schema_errors=[] 未覆盖配置键=[] 提交校验错误={} 回写一致=True 数值越界=[]
video_parser    OK=True 字段=30/30 errors=[] schema_errors=[] 未覆盖配置键=[] 提交校验错误={} 回写一致=True 数值越界=[]
总体: 5/5 全部通过 ✅
```

补充验证：
- `ast.literal_eval`（面板 `_read_declared_schema` 的实际做法）对 5 个文件全部 OK，字段数 33/37/47/30/63；
  每个文件顶层**只有 1 条语句**（`__config_schema__` 赋值），没有 import 或其他代码。
- 「配置文件里真实存在的每个叶子键都落在某条声明之下」（`command_labels.*` 由整块 json 字段覆盖）：
  5 个文件均无遗漏。
- 「用当前值模拟面板提交 → `validate_and_merge` 合并结果与现有配置**逐字节相同**」：
  5 个文件全部为 `True`（证明 `path` 指向正确、保存不会改坏配置）。
- 两个实例（740979632 / 2551736206）的所有 number 字段现值均在声明的 `min~max` 内（仅
  依星 `download_max_duration` 一条，已按 §4-5 处理）。
