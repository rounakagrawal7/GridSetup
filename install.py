#!/usr/bin/env python3
"""
GRID v2 — First-Time Setup Installer
Installs all dependencies, downloads required models, and creates default config.
"""

import subprocess
import sys
import os
import json

REQUIREMENTS = [
    "rich", "openai", "ollama", "requests", "beautifulsoup4", "ddgs",
    "duckdb", "pyautogui", "keyboard", "pandas", "numpy", "matplotlib",
    "phonenumbers", "opencv-contrib-python", "pillow", "pytesseract",
    "google-auth", "google-auth-oauthlib", "google-api-python-client",
    "openpyxl", "pyserial", "pyrtlsdr", "youtube-transcript-api",
    "gymnasium", "minigrid", "miniupnpc", "upnpclient",
]

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
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        print("  [*] config.json already exists")
        return
    default = {
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
    with open(config_path, "w") as f:
        json.dump(default, f, indent=2)
    print(f"  [*] Created default config.json (edit with your Telegram/email settings)")


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
    print("|           GRID v2 Dependency Installer            |")
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
        print("  Next step:  python grid_agent.py")
        print("  Or read:    GRID_Tools_Test_Guide.docx")
    print()


if __name__ == "__main__":
    main()
