# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the bot (connects to NapCat via WebSocket)
python main.py

# Run the web config panel (Flask)
python web/api.py

# Runtime logs are written to runtime.log and also printed to stdout
```

**Dependencies**: Python 3.12+, `websocket-client`, `requests`, `flask`
**Install**: `pip install websocket-client requests flask`
**Config**: `config.json` — WS_URL, NAPCAT_HTTP, ACCESS_TOKEN, MASTER_QQ, BOT_QQ
**All persistent data** lives in `data/` (gitignored).

## Architecture

### Entry Point: `main.py`
- Connects to NapCat via `websocket.WebSocketApp` with **auto-reconnect** (5s interval via `reconnect=5` in `run_forever`)
- **Echo filtering**: events with an `"echo"` field are silently dropped (these are responses to API calls, not user messages)
- Dynamically loads all plugins from `plugins/` directory via `pkgutil.iter_modules` — no `__init__.py` needed (PEP 420)
- Each plugin must export a `handle(event: dict) -> bool` function
- Plugin handlers called **in alphabetical filename order**; first returning `True` claims the event
- WebSocket reference stored globally in `utils.ws.ws` (set on connect in `on_open`, cleared on `on_close`)

### Plugin: `wordlib.py` — keyword → reply matching, sign-in, favor, nickname, praise
- **Admin hierarchy**: master QQ (from `MASTER_QQ` config list) has full access; admins (stored in `admins.json`) manage wordlib only
- **Two matching modes**: `exact` (full equality) or `fuzzy` (keyword in message). Both checked in `handle_message`, random reply from matched keywords
- **Multi-step state machine** via `user_word_add_state` dict: 3-step flow (keyword → reply → mode select) for interactive word addition
- **Variable substitution** in replies: `[qq]`, `[name]`, `[nick]`, `[card]`, `[group_id]`, `[favor]`, `[time]`, `[date]`, `[datetime]`, `[bot_qq]`, `[message_id]`, `[raw_message]`, `[r1-100]`, `[r1-1000]`, `[rX-Y]` (dynamic range), `[img:URL]` (auto-downloaded & cached), `[@qq]`, `[avatar]`, `[next]` (message split)
- **Image caching**: downloaded to `~/napcat/cache/images/`, md5-hashed, with container path mapping (`/app/cache/images/`)
- **Config-driven**: command keywords and reply templates come from `wordlib_messages.json` (`commands` + `settings` keys + flat message keys), merged over Python defaults at module load time via `_l()` + `cmd()` / `setting()` helpers

### Plugin: `marry.py` — daily marriage/divorce system
- **Group-only**: all commands require `message_type == "group"`
- **Daily reset**: marriage pairings scoped to `group_id → date → user_id → partner_qq`, bidirectional storage (both A→B and B→A)
- **Config-driven** via `commands_config.json`: commands and reply templates defined in `commands` + `replies` keys, loaded via `_l()` → `cmd()` / `rep()` helpers. Reply templates use Python `str.format()` for variable substitution
- **Marriage config** in `marriage_config.json`: `success_rate` (0-100) and `divorce_cd_hours`
- **Divorce CD**: tracked in `marriage_cd.json` as unix timestamps; check via `load_cd()`, persist via `save_cd()`
- **Group member queries**: HTTP GET via NapCat REST API + `get_group_member_list` to find available partners

### Plugin: `pseudo_persona.py` — AI chat (pseudo-persona mode)
- **Dual model**: GLM-4V-Flash / Gemini 2.5 Flash, both using OpenAI-compatible API format (`/v1/chat/completions`)
- **Per-group memory**: `message_history` dict keyed by `group_{group_id}` / `private_{user_id}`, with configurable `max_history` (50) and `context_window` (20)
- **Trigger conditions**: message containing "羽笙", being @mentioned, or (master only) admin commands
- **Image support**: auto-downloads images from QQ message segments to base64 for multimodal models (`download_image_as_base64`)
- **Nickname injection**: system prompt dynamically enriched with user's custom nickname (from `user_data.json`) via `build_system_prompt_with_nickname()`
- **Message splitting**: splits long AI responses by sentence boundaries (`split_count`), sends with random delay (`split_delay_min/max`)
- **Master-only commands**: model switching, history clearing

### Web Panel: `web/api.py` — Flask management UI
- **Dual bot management**: manages two bots (依星 + 羽笙) via `screen` sessions, reads/writes `data/*.json` configs
- **NapCat integration**: Docker container status check, log tailing, QR code retrieval for login
- **Plugin config CRUD**: dynamic form generation from plugin config schemas (`build_fields_from_cfg`), saves back to JSON files
- **Auth**: password file at `/etc/mybot-panel/config.json`, session-based auth with Flask sessions
- **Frontend**: static HTML served from `web/` (login), `web/yusheng/`, `web/yixing/` (bot panels)
- **Runtime**: serves on `127.0.0.1:5000`, proxied via Nginx at `bot.猫.online`

### Utility Modules
- `utils/ws.py` — single global variable `ws` (the WebSocket connection object)
- `utils/api.py` — `send_message(event, message)` sends via WebSocket (string or message-segment list); `http_get(action, params)` calls NapCat REST API
- `utils/config.py` — reads `config.json`, provides typed accessors: `get_master_qq()`, `get_bot_qq()`, `get_napcat_http()`, `get_access_token()`

### Data Flow
1. NapCat sends OneBot-standard JSON via WebSocket → `on_message()` in main.py
2. Events with `"echo"` field are ignored (API call responses)
3. main.py iterates all plugin handlers with parsed event dict
4. Plugin inspects `post_type`, `message_type`, `raw_message`, `user_id`, etc.
5. Plugin replies via `send_message(event, message)` → WebSocket

### Data Storage (`data/*.json`, all gitignored)
| File | Purpose |
|---|---|
| `wordlib_data.json` | keyword → reply mappings with mode (exact/fuzzy) |
| `wordlib_messages.json` | wordlib command keywords, settings, reply templates |
| `commands_config.json` | marry plugin command keywords and reply templates |
| `marriage_config.json` | marriage success rate, divorce CD hours |
| `marriage.json` | daily marriages (bidirectional: A→B and B→A) |
| `marriage_cd.json` | divorce cooldown timestamps |
| `user_data.json` | `{user_id: {favor: N, nickname: "X"}}` |
| `sign_data.json` | daily sign-in records `{user_id: {total: N, last_date: "YYYY-MM-DD"}}` |
| `praise_data.json` | daily praise records `{user_id: "YYYY-MM-DD"}` |
| `admins.json` | admin QQ list (wordlib management) |
| `persona_config.json` | AI model, API keys, persona prompt |
| `pseudo_messages.json` | pseudo-persona reply templates |
| `fortune_cache.json` | fortune-telling cache |
| `tarot_cache.json` | tarot reading cache |

### Key Design Details
- **Timezone**: all time-based features use `Asia/Shanghai` (`zoneinfo.ZoneInfo`)
- **Config loading pattern**: each plugin uses `_l()` → `_CFG` + `cmd()`/`setting()`/`rep()` helpers for hot-reloadable strings without code changes
- **Old data migration**: `load_user_data()` auto-migrates from legacy `favor_data.json` + `nickname_data.json` to unified `user_data.json`
- **Variable reference**: see [VARIABLES.md](VARIABLES.md) for all available template variables in replies
- **No tests** exist in the project
