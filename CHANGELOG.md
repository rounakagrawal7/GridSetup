# Changelog

## v2.0.1 — clean run

- Added `--check`: a non-interactive setup check for Python, required imports,
  `config.json`, Ollama, the selected model, DuckDB and the tool registry.
- Added `--no-input`: start from `config.json` without the backend/model wizard.
- Added `--no-banner`: skip the five-second Matrix banner.
- Added `--install-missing`: optional-package install is now opt-in. Missing
  optional packages are reported and their tools stay disabled.
- Added `run.ps1` and a “Clean start” README section with a venv workflow.
- The app starts Ollama itself when it is not running, then reaches the menu.
- Ollama now uses `num_ctx=16384`, so the 70-tool schema is not truncated and
  natural-language tool calls work on `gemma4:e2b`.
- `system_info` now uses PowerShell CIM instead of the removed `wmic`, so it
  reports memory, disk and the LAN IP without a partial-error line.
- Moved PocketBase’s upstream license and changelog to
  `third_party/pocketbase/`. The repository now has its own MIT license and a
  third-party notices file.
- Added a CI gate: syntax check, config validation and an import/tool-registry
  check on Windows.
- README: corrected the tool count (70+), capability-group count, local-first
  wording and broken/missing references.

## v2.0 — layered memory and field tools

- Added the four-tier memory engine: persona, scenarios, atoms, transcript and
  offloaded refs, with distillation every five turns.
- Added the local CTF sandbox and the GRAD open-world / MiniGrid game bridge.
- Added the autonomous Moltbook social agent and trend reporting.
- Added the 70-tool registry, including OSINT, network, radio, satellite,
  microcontroller, vision, Google, data and automation tools.

## v1.0 — initial release

- Local-first CLI agent with Ollama, LM Studio and OpenRouter backends.
- Tool registry, planner, streaming, config, export and persistent memory.
