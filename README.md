<div align="center">

# GRID v3

### General Reconnaissance & Intelligence Dashboard

*An all-in-one, local-first agent for OSINT, networks, radio, satellites, microcontrollers, computer vision, and automation — with a persistent, human-like memory layer.*

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/) [![Local-First](https://img.shields.io/badge/Local--First-Optional%20Sync-green.svg)](README.md) [![Tools](https://img.shields.io/badge/80%2B%20Tools-Recon%2FRadio%2FSAT%2FIoT-orange.svg)](README.md) [![User Manual](https://img.shields.io/badge/User%20Manual-GRID_Tools_Test_Guide-blueviolet.svg)](GRID_Tools_Test_Guide.docx)

</div>

> 📘 **New to GRID?** Download the **[GRID Tools Test Guide](GRID_Tools_Test_Guide.docx)** — the full manual with command reference, tool descriptions, and examples.

---

## ✨ What is GRID?

GRID is a self-aware terminal agent that runs locally, with optional network tools. It combines **16 capability groups** — OSINT, network recon, SDR/radio, satellite tracking, microcontroller IoT, computer vision, agent platforms, and automation — under a single conversational interface powered by your local LLM (Ollama), or any OpenAI-compatible backend.

Unlike tool wrappers that live or die on a fixed context window, GRID ships with a **layered memory engine** inspired by modern agent-memory research (e.g. Tencent's 4-tier memory pyramid). It doesn't forget between sessions: it distills what it learns into reusable knowledge instead of drowning in truncated logs.

---

## 🧠 The New: Layered Memory Engine

The latest release adds a real memory system that works across sessions with **zero new dependencies** (DuckDB keyword recall, fully local).

| Layer | What it holds | Where it lives |
|---|---|---|
| **L3 · User profile** | Durable facts & preferences about you | `grid_persona.md` |
| **L2 · Scenarios** | Summaries of completed tasks | DuckDB `memory_scenarios` |
| **L1 · Atoms** | Standalone factual statements | DuckDB `memory_atoms` |
| **L0 · Transcript** | Raw conversation | `memory.md` |
| **Refs** | Full verbatim tool outputs (offloaded) | `refs/<id>.md` |

**How it works:**
- **User profile first**: `grid_persona.md` is injected into every turn as the `USER PROFILE` block, before technical memory. The model is told to use it and not ask you to repeat yourself.
- **Every 5 turns**, GRID silently runs one LLM distillation pass over recent history via `Recaller.distill()` — extracting atomic facts, task scenarios, and durable **user** facts. System specs, IPs and tool output are excluded from the profile.
- **Remember lines**: when the model spots a durable fact about you, it can append `REMEMBER: <fact>`. The harness stores it and hides the line from the reply.
- **On every turn**, `_build_messages()` injects the profile plus *only the memories relevant to the current request* (keyword recall) alongside your recent turns — so context stays lean and relevant, not bloated.
- **Tool-output offload**: verbose tool results (>800 chars) are written whole to `refs/`; the model is handed a short preview + a reference id it can pull the full output from on demand — dramatically cutting token usage on long chains.

**Memory commands & tools:**

| Command / Tool | Purpose |
|---|---|
| `/memory` | Show memory stats (atoms / scenarios / refs / profile) |
| `/memory <query>` | Recall memories relevant to a query |
| `/memory add <fact>` | Save a durable fact about you to the profile |
| `/memory profile` | Show the full user profile |
| `/memory forget <fact>` | Remove matching profile facts |
| `/memory build-profile` | Mine previous chats for durable user facts |
| `/memory clear` | Reset the technical memory store (profile untouched) |
| `/memory clear-profile` | Clear the user profile |
| `remember that ...` | Chat shortcut for `/memory add` |
| `forget that ...` | Chat shortcut for `/memory forget` |
| `/ref <id>` | Read a full offloaded tool output |
| `memory_recall` | Tool — search layered memory for context |
| `memory_status` | Tool — memory layer health |
| `ref_read` | Tool — pull an offloaded ref by id |

The profile refuses credentials, API keys, passwords and secrets. You can also edit `grid_persona.md` directly; it is read again on the next turn.

*Inspired by the layered-memory approach popularised by agent frameworks such as Hermes and OpenClaw and TencentDB Agent Memory — humanlike memory, not a bigger scratchpad.*

---

## 🥊 GRID vs Hermes vs OpenClaw — Why GRID Wins

GRID isn't another messaging tool for one AI. It's the **only agent that fuses a full OSINT / field-ops stack directly to a human-like memory**. Hermes and OpenClaw give you a *chat brain* with toys bolted on — GRID ships as a **recon dashboard, a radio rig, a satellite dish, a camera lab, and a microcontroller bench**, all in one terminal. And it does it with **1 file to run** (`python grid_agent.py`), **local-first operation**, and **80+ built-in tools / 100+ sub-commands**.

| Capability | **GRID (v3) - 81 tools** | Hermes | OpenClaw |
|---|---|---|---|
| 🧠 **4-tier memory** (user profile · scenarios · atoms · offloaded refs) | ✅ built-in, auto-distills every 5 turns | ⚠️ SQLite + user modeling | ⚠️ file-based marks/YAML |
| 🔍 **OSINT** (domain/IP/email/phone/username, dorking, webcam/CCTV) | ✅ **built-in** | ❌ none | ⚠️ web-search only |
| 📡 **Network recon** (Nmap, DNS, netstat, full TCP/UDP netcat suite) | ✅ **built-in** | ❌ none | ⚠️ limited |
| 🎛️ **SDR / HAM radio** (Radio-Browser, KiwiSDR, RTL-SDR) | ✅ **built-in** | ❌ | ❌ |
| 🛰️ **Satellite tracking** (ISS, passes, TLE, catalog) | ✅ **built-in** | ❌ | ❌ |
| 🔌 **Microcontroller IoT** (ESP32/Arduino/LoRa via serial & TCP) | ✅ **built-in** | ❌ | ❌ |
| 👁️ **Computer vision** (OCR, faces, camera validation, video forensics) | ✅ **built-in** | ❌ | ⚠️ visual |
| 🖱️ **Computer use** (mouse, keyboard, screen, typing) | ✅ | ✅ | ✅ |
| 🪞 **Self-authoring skills** | ✅ | ✅ self-improving loop | ✅ 100+ skills |
| 🗄️ **SQL analytics + sync** | ✅ DuckDB + PocketBase | ⚠️ SQLite | ⚠️ SQLite |
| 💬 **Messaging** (Telegram, email, social agent) | ✅ | ✅ first-class | ✅ **first-class** |
| 🚀 **LLM backends** | ✅ Ollama + any OpenAI-compatible | ✅ 200+ via OpenRouter | ✅ 15+ providers |
| 🧾 **Deployment** | ✅ Python, 1 process, local | Node/TS Electron | Python+Node Electron |

### The pitch-line
- **Hermes** is a great *coding agent* — but no OSINT, no network, no radio, no satellites, no vision. For anything past a text editor, **it's a brain with no hands.**
- **OpenClaw** is the best *messaging gateway* — but it's a **heavy Node/Electron app built to babysit chat channels**, not to do field work.
- **GRID alone** packs the **16-capability stack** — OSINT investigation, network ops, SDR capture, ISS passes, ESP32 control, and video forensics — **with memory that remembers who you are across sessions.** All on a slice of a laptop.

**✨ Bottom line —** Hermes writes your code. OpenClaw reads your DMs. **GRID recons the world.** If your work touches *networks, airwaves, orbit, or physical devices*, nothing else comes close.

---

## Requirements

- **Python 3.10+**
- **Ollama** (local LLM) — https://ollama.ai
- **Tesseract OCR** *(optional)* — for image text extraction:
  - `winget install UB-Mannheim.TesseractOCR`
  - or https://github.com/UB-Mannheim/tesseract/wiki

## Quick Start

```bash
# Step 1: Install all dependencies
python install.py

# Step 2: Launch GRID
python grid_agent.py
```

On first launch, select your LLM backend (Ollama), then pick a model.

### Clean start (recommended)

Use an isolated environment, check the setup, then launch without the wizard.

```powershell
# 1. Install Ollama, then pull the model
ollama serve
ollama pull gemma4:e2b

# 2. Create an isolated environment
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\pip.exe install -r requirements.txt

# 3. Create config from the example
Copy-Item config.example.json config.json
# edit config.json if your Ollama model name differs

# 4. Check the setup before launching
.\.venv\Scripts\python.exe grid_agent.py --check

# 5. Launch without the setup prompts
.\.venv\Scripts\python.exe grid_agent.py --no-input
```

`--check` verifies Python, the required imports, `config.json`, the Ollama server, the selected model and the 80-tool registry. It does not start PocketBase or touch `grid_data.duckdb`.

Useful flags:

- `--no-banner` — skip the 5-second Matrix banner.
- `--install-missing` — install optional packages (RTL-SDR, MiniGrid, UPnP, etc.). Without it, missing optional tools are reported and disabled.
- `--no-input` — use `config.json` instead of the backend/model wizard.

If `--check` fails, fix the FAIL lines it prints. Do not launch until all required checks pass.

If the model says it has no tools, make sure Ollama is running and the model supports at least a 16k context. GRID sets `num_ctx=16384`; a smaller context truncates the 80-tool schema.

### Chat input

Type `/` and press **Tab** to complete a slash command. Subcommands complete too (`/persona ` shows `set` and `clear`). **Up/Down** walks prompt history, and matching history appears as grey inline text.

### GRID Life

GRID v3 adds a persistent local life layer: identity, goals, commitments, a heartbeat, an iLog, and messages that wait for you. It stores everything in the same DuckDB as the rest of GRID. External actions are permissioned and denied by default.

| Command | Action |
|---|---|
| `/life` | Start autopilot (stays awake) |
| `/life <task>` | Start autopilot on a task |
| **Enter** | Let GRID choose its own next goal |
| **Esc twice** | Return to manual |
| `/life pause` / `/life resume` | Stop or resume autonomous work |

`/life` starts the conversation itself: it greets you in the current persona, says what it is about to work on, reports each cycle, and asks a follow-up when it needs a decision. It also checks in every few cycles. **Esc twice** is the only thing you need to return to manual chat.

A `/life <task>` goal is **one-shot**: after one successful cycle it is marked done, but GRID **stays awake** and asks what to do next. It only returns to manual when you press **Esc twice**. For a long-running goal, add it explicitly with `/life goal add ongoing <title>`.

Defaults live in `config.json` under `life`: a 30-minute heartbeat, quiet hours 22:00–08:00, a 09:00 brief, and an **unlimited** daily action budget (`max_actions_per_day: 0`). Set a positive number if you want a throttle; reaching it makes GRID rest, never stop. Proactive messages still have their own `max_messages_per_day` cap. The standalone `python grid_life.py status|tick|log` works when GRID is closed.

An explicit `/life pause` still wins. Advanced subcommands (`status`, `log`, `goals`, `identity`, `pause`, `resume`) exist for debugging but are not part of normal use. Autopilot uses `autopilot_interval_seconds` (20s) and `autopilot_checkin_cycles` (3) from `config.json`. Pressing **Enter** instead of typing lets GRID choose its own next goal.

GRID Life uses the same identity as `/persona`. If you set `/persona set TinaGrid`, then:
- `/life` starts as TinaGrid and knows `Moltbook as TinaGrid`;
- its prompt includes the persona, the persistent Moltbook history, and the full 81-tool registry;
- `/persona clear` resets the life identity to `GRID` and asks again on the next `/life`.

If no persona is set, `/life` asks for a name first. It also asks what to work on if there are no active goals.

### Autopilot

`/life` keeps working until you press **Esc twice**:

- it greets you, states the goal, and starts the first cycle;
- each cycle shows the tool steps and result;
- it asks a follow-up when the model emits `ASK_USER:` and checks in every few cycles;
- `run_command` is terminated immediately on cancel; blocking network/hardware calls finish or hit their timeout, then autopilot stops;
- every tool goes through the permission policy before it runs;
- it reads recent chats, durable memory, tool logs, scan results and local database counts to understand you better, can inspect more with `db_query`, and redacts obvious secrets;
- with a cloud backend, this local context is omitted unless `life.allow_cloud_context` is true;
- after a one-shot goal it asks what to do next instead of exiting;
- when the daily throttle is reached, it rests and keeps its routine, but stays in autopilot until Esc twice;
- idle replies are conversation, not tool calls; if you give it a real task it records a goal and starts a work cycle;
- when you press Enter, it can give itself one small goal (bounded by `max_self_goals_per_day`, default 24);
- it runs the normal heartbeat during autopilot, so daily briefs, commitments and reflections still appear.

`autopilot_interval_seconds` controls the gap between work cycles, `autopilot_checkin_cycles` controls check-ins, and `autopilot_idle_seconds` controls how long it waits before asking again when there are no goals.

### Always-on resident

The resident is the version of GRID Life that keeps its own clock after the terminal closes. One process owns `grid_data.duckdb` at a time:

- `.\install_autostart.ps1` installs a `GRID Life` shortcut that starts `--resident` at login (and the tray icon);
- when you open the interactive app, it asks the resident to finish its current thought and hand over the database;
- when you exit the app, set `life.resident_autostart` to `true` and the app relaunches the resident for you;
- quiet hours put the resident to sleep instead of ending it; pause/resume still works;
- after login the resident waits `resident_startup_grace_seconds` (default 120) before its first model call, so Windows can finish loading;
- GRID starts Ollama with a hidden console, so Ollama's `llama-server` and GPU-discovery children inherit a hidden console instead of flashing terminal windows;
- the resident denies every non-read tool unless you configure `permissions`, so it cannot silently send email, run shell commands or touch hardware;
- logs live in `logs/resident-YYYYMMDD.log`.

```powershell
python grid_agent.py --no-input --resident
```

Check it from another terminal:

```powershell
curl http://127.0.0.1:8770/health
curl http://127.0.0.1:8770/status
```

The control surface is loopback-only. `POST /handoff` asks it to release the database; `POST /pause` and `POST /resume` map to `/life pause` and `/life resume`.

### Agent Skills

GRID v3 supports the Agent Skills `SKILL.md` standard. Only each skill’s name
and description are loaded into the prompt; the procedure is loaded on demand:

- `skill_search <query>` — find a skill
- `skill_load <name>` — load its instructions
- `skill_read <name>/references/file.md` — read a referenced file

Four MIT skills ship in `skill_library/`: `daily-brief`, `osint-report`,
`local-recon` and `skill-authoring`. Drop an Anthropic or community skill into
`skills/<name>/SKILL.md` or `skill_library/<name>/`; GRID validates the
frontmatter and name. Keep the skill’s license, and review any `scripts/`
before running it. `/life` sees the same skill list and can load them during
autopilot.

### Documents

`document_read <path>` converts a local PDF, DOCX, XLSX, PPTX, HTML, CSV, JSON or text file to Markdown/text for analysis. MarkItDown is optional; without it, GRID falls back to text, HTML, JSON, CSV, Excel and DOCX. Install everything with:

```powershell
.\run.ps1 --install-missing
```

Files are capped at 20 MB and 16,000 characters per read. No URLs are accepted.

### MCP

GRID is an MCP client and server:

- `mcp_servers` — list configured servers
- `mcp_tools <server>` — list a server’s tools
- `mcp_call <server> <tool> <json>` — call one

Configure servers in `config.json`:

```json
"mcp_servers": {
  "playwright": {
    "command": "npx",
    "args": ["@playwright/mcp@latest"],
    "enabled": true
  }
}
```

Each server starts lazily and is limited by an optional `allow` list. `mcp_call` is an external action and follows the permission policy.

GRID itself can be a read-only MCP server:

```powershell
python grid_mcp_server.py
```

It exposes local system, file, DNS, web, document and skill tools to Claude Code, Codex, Cursor or another MCP client.

### Use GRID from OpenCode

OpenCode V2 can connect to GRID as a local MCP server:

```powershell
cd C:\repos\Grid_Agent\GridSetup
.\install_opencode_mcp.ps1
opencode
```

Then verify from another terminal, or with `/mcps` inside OpenCode:

```powershell
opencode mcp list
# ✓ grid  connected
```

The installer creates a machine-specific `opencode.jsonc` from `opencode.example.jsonc` with your Python and GridSetup paths. Once connected, ask OpenCode:

```text
Use GRID to get my system info.
Use GRID to search skills for osint and load osint-report.
Use GRID to read README.md.
Use GRID to fetch https://example.com and summarize it.
```

This bridge is **read-only**: system, files, documents, DNS, web, OSINT and skills. It does not expose `/life`, shell, writes, email, radio, satellite or hardware. The GRID MCP tools use GridSetup as their working directory; use absolute paths for files elsewhere.

For a global install instead of project-local, run:

```powershell
opencode mcp add grid --global -- "$PWD\.venv\Scripts\python.exe" "$PWD\grid_mcp_server.py"
```

and add `"cwd": "C:\\repos\\Grid_Agent\\GridSetup"` to that server in `~/.config/opencode/opencode.jsonc`. OpenCode hot-reloads config; no restart is required.

### Optional tools

| Tool | Install | Notes |
|---|---|---|
| `sherlock_scan` | `pip install sherlock-project` | Username search across public sites |
| `nuclei_scan` | Nuclei binary on PATH | Requires input prefixed with `authorized`; dangerous, always asks |
| `rea` | Optional: Node 22.23.4+ and a Chrome-family browser (uses `rea-agents`) | Authorized passive site teardown; native fallback without Node |
| `pio_build` | `pip install platformio` | ESP32/Arduino build; build scripts are code, so it asks |
| `pystray` | `pip install pystray` | System tray host |

`--install-missing` installs the Python packages. Nuclei is a separate binary.

### Authorized reverse-engineering (`rea`)

`rea` performs a **passive** teardown of a web target you own or have written permission to test: page DOM and screenshot, network requests, API endpoint strings, third-party origins, stack fingerprints, security headers, cookies and redacted secret patterns. It never exploits, fuzzes, logs in or calls discovered APIs.

Authorization is required. A target is accepted only when one of these is true:

```text
rea authorized https://staging.example.com     # explicit one-off
/rea authorize staging.example.com             # add to config.json allowlist
```

or the host is private/lab (`localhost`, `127.0.0.1`, `*.local`, `*.test`, RFC1918). Everything else is refused before any request is made. The allowlist lives in `config.json`:

```json
"security": {
  "authorized_targets": ["staging.example.com", "*.lab.example"],
  "rea": { "enabled": true, "command": "", "browser": "", "allow_npx": false, "scroll_steps": 4, "timeout_seconds": 300 }
}
```

Reports are written to `refs/rea/<host>-<timestamp>/` (`report.md`, `manifest.json`, `network.json`, `headers.json`, `page.html`, plus `rea.json` and `screenshot.png` when the REA backend runs). The REA backend scrolls through the page before capture (PageDown steps, then back to the top) so lazy-loaded bundles, animations and network calls are included; set `security.rea.scroll_steps` to change the depth or `0` to disable. Install the backend once with `npm install -g rea-agents@6.10.1` (or point `security.rea.command` at a local copy). GRID will not download or execute npm code unless you explicitly set `security.rea.allow_npx` to `true`. If Node or Chrome is unavailable, the native fallback still produces a static report.

### Local API for desktop and Android (`--api`)

GRID can run as a loopback AG-UI host for the Kotlin clients:

```powershell
python grid_agent.py --api --no-input
```

The token is created at `run/api_token` (gitignored); every request needs `Authorization: Bearer <token>`. The default bind is `127.0.0.1:8771`. `--api` asks a running resident to hand over DuckDB, so use it as the host process while a desktop client is connected.

Endpoints:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/v1/health` | protocol, model, thread/report counts |
| `GET` | `/api/v1/model` | active model and available models |
| `POST` | `/api/v1/model` | switch the active model |
| `POST` | `/api/v1/command` | run a terminal-style local command (`/memory`, `/life`, `/plan`, `/jobs`, ...) |
| `GET` | `/api/v1/threads` | thread summaries |
| `GET` | `/api/v1/threads/<id>` | stored messages |
| `POST` | `/api/v1/agent` | `RunAgentInput`; returns an SSE stream |
| `POST` | `/api/v1/approvals/<id>` | approve or deny a dangerous tool |
| `GET` | `/api/v1/rea/reports` | teardown artifacts |
| `GET` | `/api/v1/rea/reports/<id>` | report manifest + Markdown |
| `GET` | `/api/v1/rea/reports/<id>/screenshot` | PNG preview |

The stream follows AG-UI 1.0: `RUN_STARTED`, `STEP_STARTED`, `TEXT_MESSAGE_*`, `TOOL_CALL_*`, `ACTIVITY_*`, `CUSTOM`, `STEP_FINISHED`, `RUN_FINISHED`. Dangerous tools emit `CUSTOM grid.approval_required` and wait for the approval endpoint. REA results emit `CUSTOM grid.artifact` with the report path.

Config:

```json
"api": {
  "host": "127.0.0.1",
  "port": 8771,
  "token_file": "run/api_token",
  "threads_file": "run/api_threads.json"
}
```

### Kotlin clients (desktop + Android)

The Compose Desktop shell and Android companion live under `clients/` and talk to `--api` over AG-UI.

```powershell
# terminal 1: host
python grid_agent.py --api --no-input

# terminal 2: desktop
cd clients
.\gradlew.bat :desktopApp:run
```

The desktop finds the token at `../run/api_token`, `run/api_token`, or `GRID_API_TOKEN`; pass `--url` or `--token-file` to override. It renders user/assistant messages, live tool cards, REA report artifacts, and approval requests. Tool-only runs show a single tool card (no duplicated assistant bubble); each assistant reply carries its duration and token count, the sidebar has a session token meter, and the chat has a visible scrollbar. The model is shown in the sidebar and can be switched from the **Change model** menu without restarting. Type `/` in the composer for the command palette (`/help`, `/new`, `/clear`, `/model`, `/tokens`, `/rea`, `/tools`, `/tool`, every registered GRID tool, and terminal-style commands), with arrow-key selection and Tab completion; the cursor lands at the end of the completed command. Local commands such as `/memory`, `/life`, `/plan`, `/ref`, `/jobs`, `/pb`, `/persona`, `/social`, `/comms`, `/ctf`, `/game`, `/gcal`, `/gsheet`, `/save` and `/export` run against the host through `POST /api/v1/command` and render their output in chat.

Android:

```powershell
cd clients
.\gradlew.bat :androidApp:assembleDebug
adb install -r androidApp\build\outputs\apk\debug\androidApp-debug.apk
```

On first launch, enter the host URL and paste the contents of `run/api_token`. The token is encrypted with an Android Keystore AES/GCM key. The default URL is `http://10.0.2.2:8771` for the emulator. For a physical device, set `api.host` to `0.0.0.0` in `config.json` (LAN exposure; token still required), restart `--api`, and use `http://<computer-LAN-IP>:8771`. Cleartext HTTP is allowed for this development build.

The AG-UI Kotlin SDK is compiled for Java 21. Gradle uses the foojay toolchain resolver to download a Java 21 toolchain for compilation and runs; `clients/local.properties` must point at the Android SDK (`sdk.dir`).

| Path | Purpose |
|---|---|
| `clients/shared/` | KMP client wrapper, `GridEvent` model, SSE contract test |
| `clients/desktopApp/` | Compose Desktop UI |
| `clients/androidApp/` | Android Compose companion + Keystore token store |

### Context compression

Optional Headroom support compresses only non-system history/tool messages; the system prompt and tool names stay intact:

```json
"life": { "compress_context": true }
```

Install with `pip install headroom-ai`. Measure tool-selection quality with `python evals/run_evals.py` before keeping it on.

### Tray and autostart

```powershell
pip install pystray
.\install_autostart.ps1
```

This installs two startup shortcuts: **GRID Tray** (Open GRID, Start autopilot, Pause life, Resume life, Quit) and **GRID Life** (`--resident`, no console). Remove both with `.\uninstall_autostart.ps1`. The tray only launches GRID; the resident and tools stay in the GRID process.

You can also start either mode directly:

```powershell
python grid_agent.py --no-input --autopilot
python grid_agent.py --no-input --autopilot "Map my home network"
python grid_agent.py --no-input --resident
```

Esc twice returns foreground autopilot to manual. The resident has no UI; use `/life pause`, `/life resume` or the loopback endpoints above. Set `life.resident_autostart: true` in `config.json` if you want the app to relaunch the resident every time you exit.

### Permissions and auto-email

Autonomous runs use `permissions` in `config.json`:

```json
"permissions": {
  "mode": "ask",
  "auto_approve": [],
  "deny": []
}
```

| Mode | Behaviour |
|---|---|
| `ask` | Read-only tools run; sensitive, local-write, external, hardware and dangerous tools ask first |
| `auto` | Read-only, local-write, external and hardware tools run; sensitive and dangerous tools still ask |
| `read_only` | Only read-only tools run |

For iLands-style automatic email, keep `ask` and opt in only the tools you trust:

```json
"permissions": {
  "mode": "ask",
  "auto_approve": ["email_send"],
  "deny": []
}
```

The `email` section must already have working SMTP settings. With `mode: "auto"`, external actions such as `email_send`, `telegram_send` and `social` run without a prompt; destructive actions still ask. When a prompt appears, `a` means “always this session”; `n` denies. The default is deny.


> 📘 After first launch, open **`GRID_Tools_Test_Guide.docx`** for the full command reference.

---

## What's Included

| File | Purpose |
|---|---|
| `grid_agent.py` | Main app — CLI, tool registry, orchestrator, **layered memory** |
| `grid_vision.py` | Computer vision — OCR, face detection, camera validation, video forensics |
| `grid_osint.py` | OSINT engine — domain/IP/email/phone/username intel, camera search, dorking |
| `grid_db.py` | DuckDB layer — tool logging, caching, analytics, **memory tables** |
| `grid_pb.py` | PocketBase integration — cloud sync, artifact upload |
| `grid_satellite.py` | Satellite tracking (ISS, passes, TLE, catalog) |
| `grid_radio.py` | Radio & SDR (Radio-Browser, KiwiSDR, RTL-SDR) |
| `grid_micro.py` | Microcontroller IoT (ESP32, Arduino, LoRa) |
| `grid_skills.py` | Self-authored Python skills |
| `grid_skilldocs.py` | Agent Skills (`SKILL.md`) discovery, validation and loading |
| `skill_library/` | Built-in SKILL.md procedures (MIT) |
| `grid_life.py` | Persistent identity, goals, commitments, heartbeat and iLog |
| `grid_awake.py` | Autopilot, step display and double-Esc cancel |
| `grid_resident.py` | Always-on resident, loopback control surface and app handoff |
| `grid_api.py` | Local AG-UI HTTP/SSE API for desktop and Android clients |
| `clients/` | Kotlin Multiplatform client + Compose Desktop shell |
| `tools/` | Optional profile backfill, pilot harness and boot-window logger |
| `grid_permissions.py` | Ask/auto/read-only policy for autonomous tool use |
| `grid_docs.py` | `document_read` + optional MarkItDown |
| `grid_mcp.py` / `grid_mcp_server.py` | MCP client manager and read-only GRID MCP server |
| `grid_optional.py` | Optional Sherlock, Nuclei and PlatformIO wrappers |
| `grid_context.py` | Optional Headroom context compression |
| `grid_tray.py` | Optional tray host |
| `install_autostart.ps1` / `uninstall_autostart.ps1` | Login autostart control |
| `opencode.example.jsonc` / `install_opencode_mcp.ps1` | Connect OpenCode to GRID's MCP server |
| `grid_agent_social.py` | Moltbook social agent platform |
| `grid_google.py` / `grid_sheets.py` | Google Calendar & Sheets / Excel |
| `install.py` | One-time setup — deps, models, config |
| `requirements.txt` | Python package list |
| `GRID_Tools_Test_Guide.docx` | Full user manual + command reference |
| `pocketbase.exe` | PocketBase server (optional, for cloud sync) |

## 🌐 Moltbook Social Agent (New)

GRID connects to **Moltbook** — the social network for autonomous agents — and runs an autonomous presence for your persona. Register an agent, then let GRID reply, vote, follow, comment, post, and track your growth — on a schedule or on demand.

### First-time setup

```bash
# 1. Register your agent persona on Moltbook (pick a username)
/social register <username>

# 2. Verify the claim challenge if the platform requires it
/social status
/social verify <code> <answer>
```

### One autonomous cycle (everything at once)

```
/social auto
```

A single cycle runs all phases: reply to new comments on **your own posts**, upvote promising posts & comments, comment on interesting threads, follow active agents, post **1 new community-aware post** to the best-matching submolt (ranked against your interests), scan search topics, check trending submolts, and save a dated stats snapshot for the trend report.

### Background daemon (runs every ~30 min)

```
/social auto-daemon on     # start
/social auto-daemon off    # stop
```

### Reports & history

| Command | Purpose |
|---|---|
| `/social summary` | Plain-language digest: your activity + hot topics |
| `/social analyze` | Pandas data report: profile card, feed stats, top posts/authors, engagement on your posts |
| `/social trend [day\|week\|month\|year\|all]` | Time-series report from saved snapshots — how karma/followers/engagement progress |
| `/social history [limit]` | Full activity log with post/comment links |

### Key behaviors

- **Engagement counts are accurate** — GRID only counts comments/replies on posts **you authored**, not threads you merely commented on.
- **Rate-limit safe** — when Moltbook returns a 429 hourly cap, GRID pauses write actions for an hour and logs it once instead of hammering.
- **Secret-guarded** — every reply, comment, and post is scanned; content that looks like credentials (API keys, tokens) is refused.
- **Your credentials never leave your machine** — agent API keys live in `moltbook_agents.json`, which is gitignored.

### Troubleshooting

- **New posts/comments stay hidden or show `pending`/`failed`** — Moltbook gates every published item behind a CAPTCHA-style math challenge returned in the create response. GRID auto-solves and submits it (the answer must have exactly 2 decimal places, e.g. `15.00`). If "Auto-verified" is not in the cycle log line, your LLM backend could not read the obfuscated challenge and the item stays hidden. Verify it manually with `/social verify <code> <answer>` — the code + challenge are only returned at create time, so grab them from the raw response if your generator flagged it pending.
- **A `failed` post is permanent** — a wrong answer cannot be retried. Delete it via the API and remove the submolt from `moltbook_posted.json`, otherwise the auto-cycle treats that community as already posted and never posts there again.
- **`[Reply]` never fires even with comments** — the reply cycle scans posts from `/posts?author=<name>`, which hides `pending` posts. Since the fix, GRID also merges your profile's `recentPosts` (which includes unverified posts), so comments on not-yet-verified posts are still answered.
- **Only one auto-post ever happens** — the cycle skips communities already listed in the claim file. If a post was deleted or failed, release its submolt name from `moltbook_posted.json` so a fresh post is generated next cycle.
- **Answer formatting matters** — two decimals required (`30` → `30.00`). The LLM solver is set to temperature `0` and told to return just the number; the fallback is the heuristic solver only. Manual submit: `/social verify <code> <answer>`.

## Screenshots

| | |
|---|---|
| ![GRID Session](screenshots/grid_session.png) | ![Radio & SDR](screenshots/radio_sdr.png) |
| ![Satellite Tracking](screenshots/satellite.png) | ![Microcontroller](screenshots/microcontroller.png) |

---

## Capabilities

- **OSINT** — email/phone/username intelligence, IP/domain enrichment, camera search, Google dorking
- **Network** — ping, DNS, netstat, NMAP scanning, netcat suite (listener/client/scan/proxy/transfer/chat)
- **Computer Vision** — OCR, face detection/comparison, camera-stream validation, video forensics
- **Computer Use** — mouse, keyboard, screenshots
- **Data & Code** — CSV/JSON analysis via pandas, arbitrary Python execution
- **Database** — DuckDB SQL queries, PocketBase sync
- **Memory** — user profile, facts, scenarios, offloaded refs, relevance ranking, keyword recall
- **Communication** — Telegram, email
- **System** — hardware info, process management, weather
- **Flight / Satellite / Radio / IoT** — live flight tracking, satellite passes, SDR, microcontrollers
- **CTF Sandbox** — offline local capture-the-flag practice: `/ctf` spawns isolated challenges (SQL injection, Python env-var jail, base64 forensics, ROT13, port-banner grab) for GRID to solve with its own tools
- **Game Worlds** — playable environments: `grid_game.py` gives GRID an open-world exploration sandbox (map, gather, hunt, reach the Cache) usable with zero dependencies, plus a bridge to Gymnasium MiniGrid RL benchmarks (`pip install gymnasium minigrid`)

## Recent Changes — GRID Game Worlds

- **GRADDR open world**: `grid_game.py` generates a procedural map (grass/forest/water/ruin), scattered items (water, rations, key, compass), and wandering monsters. GRID explores with `game world move <dir>`, reads the map fog, hunts, fights, and wins by reaching the Signal Cache tile `C`.
- **Turn-based loop**: actions cost energy, state persists across calls under `./game_state/world.json`, so GRID can play over many turns and learn navigation strategies.
- **MiniGrid RL bridge**: once `gymnasium` + `minigrid` are installed, `game minigrid start/step/reset` plugs GRID into standard benchmark navigation envs for reward/reinforcement practice.
- **Memory tie-in**: strategies and maps can be distilled into L1/L2 memory so GRID navigates new worlds faster next session.

## Recent Changes — GRID CTF Sandbox

- **Local-only CTF range**: `grid_ctf.py` generates isolated challenges under `./ctf_range/` with **no network egress** — safe autonomous practice.
- **5 challenges**: SQLite login bypass, python env-var flag, base64 hidden envelope, ROT13 cipher, localhost banner grab.
- **Full game loop**: `/ctf start` spawns, `/ctf hint` nudges, `/ctf submit <flag>` verifies `GRID_CTF{...}` tokens, `/ctf score` writes a scoreboard, `/ctf reset` clears artifacts.
- **Teaches the memory layer**: a solved challenge can be distilled into L1 atoms / L2 scenarios so GRID attacks similar challenges faster next session.

## Recent Changes — Autonomous Moltbook Social Agent

- **Auto-posting**: `/social auto` and the daemon now post **1 original, community-aware post** to the best-matching submolt — ranked against your interests (OSINT, security, AI, radio, vision, memory…) using each community's description and recent post tone.
- **Auto engagement**: reply to comments on your own posts, upvote promising posts & comments, comment on interesting threads, follow active agents — all in one cycle or on a 30-min daemon schedule.
- **Accurate analytics**: engagement counts only include comments/replies on **your own posts** (previously included threads you merely commented on).
- **Time-series trend**: `/social trend [day|week|month|year]` shows how karma, followers, engagement, and feed stats progress — snapshots auto-saved every auto cycle.
- **Rate-limit backoff**: Moltbook's 429 hourly cap pauses write actions for an hour and is logged once instead of spamming errors.
- **Secret guard hardening**: every reply/comment/post is scanned for credentials and refused if they look like API keys, tokens, or secrets.
- **Setup template**: `config.example.json` shows the backend config shape (replace placeholders, never your real keys).

## Recent Changes — Moltbook Verification & Reliability Fixes

- **LLM auto-verification**: Moltbook gates posts/comments behind an obfuscated math challenge. GRID now solves it with your LLM backend (`set_challenge_solver`) and submits the 2-decimal answer automatically, so posts no longer sit hidden at `pending`.
- **Auto-verify wired everywhere**: the post, comment, and reply cycles all run the verifier on their create response — fixes items that were created but never appeared on the feed.
- **Auto-post candidate walk**: the post cycle now tries each ranked submolt instead of only the top candidate, so a fresh post appears even when the best-matching community is already claimed.
- **Reply cycle sees all own posts**: `_own_post_ids` now merges the profile's `recentPosts` with `/posts?author=`, so comments on `pending` (unverified) posts are still answered.
- **Safe challenge solving**: the heuristic solver only runs when the LLM hook is unavailable, and manual `/social verify <code> <answer>` remains for fallback.

## Recent Changes — Memorable GRID (v2 Memory)

- Added 4-tier layered memory: persona / scenarios / atoms / offloaded refs.
- Automatic 5-turn distillation into long-term knowledge via the local LLM.
- Relevance-based context injection in place of blind last-5-turn truncation.
- Tool-output offload to reduce token usage on long multi-step tasks.
- New tools (`memory_recall`, `memory_status`, `ref_read`) and `/memory`, `/ref` commands.
- Broadened `.gitignore` to keep local memory/config state out of the repo.

## Commands

| Command | Action |
|---|---|
| `/exit` | Save and exit |
| `/back` | Return to main menu |
| `/model` | Switch LLM model |
| `/tools` | View all tools |
| `/clear` | Clear conversation |
| `/plan` | Toggle step-by-step planner mode |
| `/memory [query\|clear]` | View / recall / clear layered memory |
| `/ref <id>` | Read an offloaded tool output |
| `/apikey` | Configure API keys (YouTube, Shodan, VirusTotal, etc.) |
| `/help` | Show command reference |

## Documentation

Open `GRID_Tools_Test_Guide.docx` for the complete user manual, tool descriptions, examples, and quick-reference commands.

## License

GRID is MIT-licensed — see [LICENSE.md](LICENSE.md). PocketBase and other third-party components keep their own licenses; see [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and [third_party/pocketbase/LICENSE.md](third_party/pocketbase/LICENSE.md).