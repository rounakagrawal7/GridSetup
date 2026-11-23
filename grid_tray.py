"""Optional GRID tray host.

Start at login to keep an icon in the notification area. The tray opens GRID or
starts autopilot in a new console. It never runs tools itself.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent


def _python() -> str:
    candidate = HERE / ".venv" / "Scripts" / "python.exe"
    return str(candidate) if candidate.exists() else sys.executable


def _launch(extra=None) -> None:
    command = [_python(), str(HERE / "grid_agent.py"), "--no-input"]
    command.extend(extra or [])
    kwargs = {"cwd": str(HERE)}
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
    subprocess.Popen(command, **kwargs)


def _icon_image():
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (64, 64), (8, 12, 10))
    draw = ImageDraw.Draw(image)
    draw.ellipse((12, 12, 52, 52), outline=(0, 255, 0), width=5)
    draw.line((22, 32, 30, 40), fill=(0, 255, 0), width=5)
    draw.line((30, 40, 44, 22), fill=(0, 255, 0), width=5)
    return image


def main() -> int:
    try:
        import pystray
    except ImportError:
        print("pystray is not installed. Run: pip install pystray")
        return 1

    def open_grid(icon=None, item=None):
        _launch()

    def start_autopilot(icon=None, item=None):
        _launch(["--autopilot"])

    def quit_tray(icon, item=None):
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Open GRID", open_grid, default=True),
        pystray.MenuItem("Start autopilot", start_autopilot),
        pystray.MenuItem("Quit", quit_tray),
    )
    icon = pystray.Icon("grid", _icon_image(), "GRID v3", menu=menu)
    icon.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
