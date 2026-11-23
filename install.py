#!/usr/bin/env python3
"""
GRID v3 — First-Time Setup Installer
Installs all dependencies, downloads required models, and creates default config.
"""

import subprocess
import sys
import os
import json

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIREMENTS_FILE = os.path.join(HERE, "requirements.txt")

# Heavy or hardware-specific extras stay opt-in from requirements.txt.
OPTIONAL_EXTRAS = ["pyrtlsdr", "gymnasium", "minigrid", "miniupnpc", "upnpclient"]


def load_requirements() -> list[str]:
    """Keep the installer in sync with requirements.txt."""
    if not os.path.exists(REQUIREMENTS_FILE):
        return []
    packages = []
    with open(REQUIREMENTS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                packages.append(line)
    return packages


REQUIREMENTS = load_requirements() + OPTIONAL_EXTRAS

CASCADE_URL = "https://raw.githubusercontent.com/opencv/opencv/4.x/data/haarcascades/haarcascade_frontalface_default.xml"
CASCADE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "haarcascade_frontalface_default.xml")


def pip_install(pkg: str) -> bool:
    print(f"  [+] Installing {pkg}...")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return True
    except subprocess.CalledProcessError:
        return False


def download_cascade():
    if os.path.exists(CASCADE_PATH):
        print(f"  [*] Haar cascade already exists: {CASCADE_PATH}")
        return True
    print("  [+] Downloading Haar cascade for face detection...")
    try:
        import urllib.request
        urllib.request.urlretrieve(CASCADE_URL, CASCADE_PATH)
        print(f"  [*] Saved to: {CASCADE_PATH}")
        return True
    except Exception as e:
        print(f"  [!] Could not download cascade: {e}")
        return False


def create_config():
    config_path = os.path.join(HERE, "config.json")
    if os.path.exists(config_path):
        print("  [*] config.json already exists")
        return

    default = {
        "backend_type": "ollama",
        "base_url": "http://localhost:11434",
        "model": "gemma4:e4b",
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "email": {
            "smtp_server": "",
            "smtp_port": 587,
            "smtp_user": "",
            "smtp_pass": "",
            "from_addr": ""
        }
    }

    # Prefer the checked-in template so the installer and example never drift.
    example_path = os.path.join(HERE, "config.example.json")
    if os.path.exists(example_path):
        try:
            with open(example_path, encoding="utf-8") as f:
                default = json.load(f)
        except (OSError, json.JSONDecodeError):
            pass

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(default, f, indent=2)
    print("  [*] Created config.json (edit with your Telegram/email settings)")


def check_tesseract():
    print("\n  [*] Checking Tesseract OCR binary...")
    try:
        subprocess.run(["tesseract", "--version"], capture_output=True, timeout=5)
        print("  [*] Tesseract OCR binary found! OCR features enabled.")
    except Exception:
        print("  [!] Tesseract OCR binary not found.")
        print("      OCR features (analyze_image, screenshot_ocr) will skip text extraction.")
        print("      To install: https://github.com/UB-Mannheim/tesseract/wiki")
        print("      Or:  winget install UB-Mannheim.TesseractOCR")
        print("      Or:  choco install tesseract")


def main():
    print()
    print("+--------------------------------------------------+")
    print("|           GRID v3 Dependency Installer            |")
    print("+--------------------------------------------------+")
    print()

    # Step 1: Install pip packages
    print("--- Step 1: pip packages ---")
    successes = 0
    failures = 0
    for pkg in REQUIREMENTS:
        if pip_install(pkg):
            successes += 1
        else:
            failures += 1
            print(f"  [!] Failed: {pkg}")

    print(f"\n  Result: {successes} installed, {failures} failed")

    # Step 2: Download Haar cascade
    print("\n--- Step 2: Model files ---")
    download_cascade()

    # Step 3: Create config
    print("\n--- Step 3: Configuration ---")
    create_config()

    # Step 4: Check Tesseract
    print("\n--- Step 4: OCR binary check ---")
    check_tesseract()

    print()
    if failures > 0:
        print(f"  [!] {failures} package(s) failed. Try installing manually:")
        for pkg in REQUIREMENTS:
            print(f"      pip install {pkg}")
    else:
        print("  [*] All dependencies installed!")
        print()
        print("  Next step:  python grid_agent.py --check")
        print("  Then:       python grid_agent.py --no-input")
        print("  Or read:    GRID_Tools_Test_Guide.docx")
    print()


if __name__ == "__main__":
    main()
