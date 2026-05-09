# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the bot (connects to NapCat via WebSocket)
python main.py

# Run the web config panel (Flask)
python web/api.py

# Runtime logs are written to runtime.log and also printed to stdout
# Bot interaction logs go to bot.log
```

**Dependencies**: Python 3.12+, `websocket-client`, `requests`, `flask` (installed in `venv/`)
**Config**: `config.json` — set `WS_URL`, `NAPCAT_HTTP`, `ACCESS_TOKEN`, `MASTER_QQ`, `BOT_QQ`
**No requirements.txt** exists; install with `pip install websocket-client requests flask`

## Architecture

### Entry Point: `main.py`
- Connects to NapCat via WebSocket (`websocket.WebSocketApp` with auto-reconnect)
- Dynamically loads all plugins from `plugins/` directory via `pkgutil.iter_modules`
- Each plugin must export a `handle(event: dict) -> bool` function
- Plugin handlers are called **in alphabetical filename order**; the first returning `True` claims the event
- WebSocket reference stored globally in `utils.ws.ws` (set on connect, cleared on close)

### Plugin Loading Order (alphabetical)
1. `marry.py` — marriage system
2. `pseudo_persona.py` — AI chat (pseudo-persona mode)
3. `wordlib.py` — word library, sign-in, favor, nickname, praise

### Utility Modules
- `utils/ws.py` — single global variable `ws` (the WebSocket connection object), shared across modules
- `utils/api.py` — `send_message(event, message)` sends via WebSocket; `http_get(action, params)` calls NapCat REST API
- `utils/config.py` — reads `config.json`, provides typed accessors: `get_master_qq()`, `get_bot_qq()`, `get_napcat_http()`, `get_access_token()`

### Data Flow
1. NapCat sends OneBot-standard JSON event via WebSocket → `on_message()` in main.py
2. main.py iterates all plugin handlers with parsed event dict
3. Plugin inspects `post_type`, `message_type`, `raw_message`, `user_id`, etc.
4. Plugin calls `send_message(event, message)` to reply via WebSocket

### Data Storage
All persistent data is in `data/` directory (gitignored) as JSON files:
- `wordlib_messages.json` — wordlib commands, settings, and reply message templates
- `wordlib_data.json` — keyword → reply mappings (exact/fuzzy)
- `commands_config.json` — marry plugin commands and replies
- `marriage_config.json` — marriage success rate and divorce CD settings
- `user_data.json` — per-user data: `{user_id: {favor: N, nickname: "X"}}`
- `sign_data.json` — daily sign-in records
- `marriage.json` — daily marriage pairings (bidirectional: A→B and B→A stored)
- `persona_config.json` — pseudo-persona AI config (model, API keys, persona)
- `pseudo_messages.json` — pseudo-persona reply templates

### Web Config Panel
- Flask application in `web/api.py`, served at `bot.猫.online` via Nginx reverse proxy
- Frontend HTML in `web/` (login) and `web/yusheng/`, `web/yixing/` (bot panels)
- Runs on `127.0.0.1:5000`, manages bot start/stop/restart via `screen`, reads/writes `data/*.json` configs
- Auth via `/etc/mybot-panel/config.json` (password file, one password per bot name)

### Key Design Details
- **No `__init__.py` files** — relies on Python 3.3+ implicit namespace packages (PEP 420)
- **Command configuration**: `wordlib_commands.json` and `commands_config.json` allow customizing command keywords without editing Python code
- **Reply message templates**: `wordlib_messages.json`, `pseudo_messages.json`, and `commands_config.json` (marry replies) allow customizing bot responses
- **Variable substitution**: wordlib replies support variables like `[name]`, `[@qq]`, `[favor]`, `[r1-100]`, `[img:URL]`, `[next]` (message split), `[avatar]`
- **Image caching**: `~/napcat/cache/images/` directory for downloaded images (avatar, img: tags)
- **Time zone**: All time-based features use `Asia/Shanghai` timezone
- **No tests** exist in the project
