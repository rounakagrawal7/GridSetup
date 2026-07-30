# GRID v2 — General Reconnaissance & Intelligence Dashboard

All-in-one OSINT, networking, automation, and computer vision platform.

## Requirements

- **Python 3.10+**
- **Ollama** (for local LLM) — download from https://ollama.ai
- **Tesseract OCR** *(optional)* — for image text extraction. Install via:
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

## What's Included

| File | Purpose |
|---|---|
| `grid_agent.py` | Main application — CLI interface, tool registry, LLM orchestration |
| `grid_vision.py` | Computer vision tools (OpenCV) — OCR, face detection, camera validation, video forensics |
| `grid_osint.py` | OSINT engine — domain/IP/email/phone/username intelligence, camera search, dorking |
| `grid_db.py` | DuckDB database layer — tool logging, caching, analytics |
| `grid_pb.py` | PocketBase integration — cloud sync, artifact upload |
| `install.py` | One-time setup — installs all pip packages, downloads models, creates config |
| `requirements.txt` | Python package list |
| `GRID_Tools_Test_Guide.docx` | Full user manual with command reference and examples |
| `pocketbase.exe` | PocketBase server (optional — for cloud sync features) |

## Screenshots

| | |
|---|---|
| ![GRID Session](screenshots/grid_session.png) | ![Radio & SDR](screenshots/radio_sdr.png) |
| ![Satellite Tracking](screenshots/satellite.png) | ![Microcontroller](screenshots/microcontroller.png) |

## Capabilities

- **OSINT** — domains, IPs, emails, phones, usernames, camera search, Google dorking
- **Network** — ping, DNS, netstat, Nmap scanning
- **Netcat Suite** — TCP/UDP listener, client, scanner, proxy, file transfer, chat
- **Computer Vision** — image OCR, face detection/comparison, camera stream validation, video forensics
- **Computer Use** — mouse, keyboard, screenshots
- **Data & Code** — CSV/JSON analysis via pandas, arbitrary Python execution
- **Database** — DuckDB SQL queries, PocketBase sync
- **Communication** — Telegram, email
- **System** — hardware info, process management, weather

## Commands

| Command | Action |
|---|---|
| `/exit` | Save and exit |
| `/back` | Return to main menu |
| `/model` | Switch LLM model |
| `/tools` | View all tools |
| `/clear` | Clear conversation |
| `/plan` | Toggle step-by-step planner mode |
| `/apikey` | Configure API keys (YouTube, Shodan, VirusTotal, etc.) for enhanced tools |
| `/help` | Show command reference |

## Documentation

Open `GRID_Tools_Test_Guide.docx` for the complete user manual with tool descriptions, examples, and quick reference commands.
