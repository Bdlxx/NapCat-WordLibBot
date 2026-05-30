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

### Core Framework: `main.py` (SDK)
- Connects to NapCat via `websocket.WebSocketApp` with **auto-reconnect** (5s interval via `reconnect=5` in `run_forever`)
- **Echo filtering**: events with an `"echo"` field are silently dropped (these are responses to API calls, not user messages)
- Dynamically loads all plugins from `plugins/` directory via `pkgutil.iter_modules` — no `__init__.py` needed (PEP 420)
- Each plugin must export a `handle(event: dict) -> bool` function
- Plugin handlers called **in alphabetical filename order**; first returning `True` claims the event
- WebSocket reference stored globally in `utils.ws.ws` (set on connect in `on_open`, cleared on `on_close`)

### Plugin: `wordlib.py` — keyword → reply matching, sign-in, favor, nickname, praise
- **Admin hierarchy**: master QQ (from `MASTER_QQ` config list) has full access; admins (stored in `wordlib_config.json`) manage wordlib only
- **Two matching modes**: `exact` (full equality) or `fuzzy` (keyword in message). Both checked in `handle_message`, random reply from matched keywords
- **Multi-step state machine** via `user_word_add_state` dict: 3-step flow (keyword → reply → mode select) for interactive word addition
- **Variable substitution** in replies: see [VARIABLES.md](VARIABLES.md) for all available template variables
- **Image caching**: downloaded to `~/napcat/cache/images/`, md5-hashed, with container path mapping (`/app/cache/images/`)
- **Config-driven**: command keywords and reply templates come from `wordlib_config.json` (`commands` + `settings` + `messages` keys), merged over Python defaults at module load time via `_l()` + `cmd()` / `setting()` helpers

### Web Panel: `web/api.py` — Flask management UI
- **Dual bot management**: manages two bots (依星 + 羽笙) via `screen` sessions, reads/writes `data/*.json` configs
- **NapCat integration**: Docker container status check, log tailing, QR code retrieval for login
- **Plugin config CRUD**: dynamic form generation from plugin config JSON, saves back to JSON files
- **Auth**: password file at `/etc/mybot-panel/config.json`, session-based auth with Flask sessions
- **Frontend**: static HTML served from `web/` (login), `web/yusheng/`, `web/yixing/` (bot panels)
- **Runtime**: serves on `127.0.0.1:5000`, proxied via Nginx at `bot.猫.online`

### Utility Modules
- `utils/ws.py` — single global variable `ws` (the WebSocket connection object)
- `utils/api.py` — `send_message(event, message)` sends via WebSocket (string or message-segment list); `http_get(action, params)` calls NapCat REST API
- `utils/config.py` — reads `config.json`, provides typed accessors: `get_master_qq()`, `get_bot_qq()`, `get_napcat_http()`, `get_access_token()`
- `utils/plugin_toggle.py` — per-group plugin toggle system (default OFF)
- `utils/command_table.py` — generates command reference table

### Plugin Development (SDK Pattern)
Create a new plugin by adding a `.py` file to `plugins/`:
1. Export a `handle(event: dict) -> bool` function
2. Return `True` if the event was handled (stops chain), `False` to pass to next plugin
3. Use `utils.api.send_message(event, message)` to reply
4. Use `utils.config.get_config(key, default)` for config reads
5. Use `utils.plugin_toggle` for per-group enable/disable

Example minimal plugin:
```python
from utils.api import send_message
from utils.config import get_master_qq

def handle(event: dict) -> bool:
    if event.get("raw_message", "").strip() == "ping":
        send_message(event, "pong")
        return True
    return False
```

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
| `wordlib_config.json` | wordlib command keywords, settings, reply templates |
| `user_data.json` | `{user_id: {favor: N, nickname: "X"}}` |
| `sign_data.json` | daily sign-in records |
| `praise_data.json` | daily praise records |
| `plugin_toggle.json` | per-group plugin enable/disable state |

### Key Design Details
- **Timezone**: all time-based features use `Asia/Shanghai` (`zoneinfo.ZoneInfo`)
- **Config loading pattern**: each plugin uses `_l()` → `_CFG` + `cmd()`/`setting()` helpers for hot-reloadable strings without code changes
- **Old data migration**: `load_user_data()` auto-migrates from legacy `favor_data.json` + `nickname_data.json` to unified `user_data.json`
- **Variable reference**: see [VARIABLES.md](VARIABLES.md) for all available template variables in replies
- **No tests** exist in the project
