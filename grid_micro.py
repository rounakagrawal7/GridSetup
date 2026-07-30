"""
GRID Micro Module — microcontroller connectivity (ESP32, Arduino, LoRa, etc.)
Serial (USB), TCP/IP (WiFi), and LoRa (via serial AT) support.
"""

import json
import re
import socket
import threading
import time
from datetime import datetime

SERIAL_BAUDS = [300, 1200, 2400, 4800, 9600, 19200, 38400, 57600, 74880, 115200, 230400, 250000, 921600]

_conn = {
    "type": None,
    "ser": None,
    "sock": None,
    "port": None,
    "baud": None,
    "host": None,
    "tcp_port": None,
    "monitor": False,
    "buffer": "",
}

def _ensure_dep(pkg_name: str, import_name: str = ""):
    import importlib, subprocess, sys
    mod = import_name or pkg_name
    try:
        return importlib.import_module(mod)
    except ImportError:
        sys.stderr.write(f"-> Installing {pkg_name}...\n")
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", pkg_name],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                sys.stderr.write(f"-> {pkg_name} installed\n")
                return importlib.import_module(mod)
            else:
                return None
        except Exception:
            return None


def micro_main(cmd: str) -> str:
    if not cmd or cmd.strip() in ("help", "-h", "--help", "?"):
        return _help()
    parts = cmd.strip().split()
    sub = parts[0].lower()
    rest = " ".join(parts[1:]) if len(parts) > 1 else ""

    if sub == "scan":
        return _cmd_scan()
    elif sub == "connect":
        return _cmd_connect(rest)
    elif sub == "disconnect":
        return _cmd_disconnect()
    elif sub in ("send", "write", "command"):
        return _cmd_send(rest)
    elif sub in ("read", "recv", "receive"):
        return _cmd_read(rest)
    elif sub == "monitor":
        return _cmd_monitor(rest)
    elif sub == "info":
        return _cmd_info()
    elif sub in ("tcp", "wifi", "network"):
        return _cmd_tcp_connect(rest)
    elif sub in ("lora", "radio"):
        return _cmd_lora(rest)
    else:
        return f"Unknown sub-command '{sub}'. Use 'micro help'."


def _help() -> str:
    return (
        "  MICROCONTROLLER COMMAND REFERENCE\n"
        "  =========================================\n\n"
        "  COMMAND                    WHAT IT DOES\n"
        "  ---------------------------------------------------------\n"
        "  micro scan                Scan for serial ports\n"
        "  micro connect <port>      Connect via serial (e.g. COM3)\n"
        "    [baud]                  Optional baud rate (default 115200)\n"
        "  micro connect <host>:<p>  Connect via TCP (e.g. 192.168.1.100:8080)\n"
        "  micro disconnect          Close connection\n"
        "  micro send <data>         Send data/command to microcontroller\n"
        "  micro read [N]            Read N lines from device (default 10)\n"
        "  micro monitor [on|off]    Continuous read mode\n"
        "  micro info                Show connection state\n"
        "  micro lora send <data>    Send via LoRa (serial AT)\n"
        "  micro lora recv           Receive LoRa data\n\n"
        "  EXAMPLES:\n"
        "  \"connect to ESP32 on COM3\"\n"
        "  \"send LED ON to the microcontroller\"\n"
        "  \"read temperature from ESP32\"\n"
        "  \"monitor serial data\"\n"
        '  "set pin 13 high"\n'
        '  "turn on the relay"\n'
    )


def _cmd_scan() -> str:
    ser_mod = _ensure_dep("serial", "serial")
    if ser_mod is None:
        return "  pyserial not available. Install: pip install pyserial"

    try:
        import serial.tools.list_ports as list_ports
        ports = list_ports.comports()
    except ImportError:
        ports = []

    if not ports:
        return "  No serial ports found."

    lines = ["  AVAILABLE SERIAL PORTS"]
    lines.append("  " + "=" * 60)
    lines.append(f"  {'Device':<12} {'Description':<40}")
    lines.append("  " + "-" * 54)
    for p in sorted(ports, key=lambda x: x.device):
        desc = (p.description or "")[:38]
        lines.append(f"  {p.device:<12} {desc:<40}")
    return "\n".join(lines)


def _cmd_connect(args: str) -> str:
    if not args.strip():
        return "  Usage: micro connect <port> [baud]   or   micro connect <host>:<port>"

    if _conn["ser"] is not None or _conn["sock"] is not None:
        _cmd_disconnect()

    args = args.strip()

    # TCP: host:port
    if ":" in args and not re.match(r"^COM\d+", args, re.IGNORECASE):
        parts = args.rsplit(":", 1)
        host = parts[0].strip()
        try:
            tcp_port = int(parts[1])
        except ValueError:
            return f"  Invalid port number: {parts[1]}"
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            sock.connect((host, tcp_port))
            _conn["type"] = "tcp"
            _conn["sock"] = sock
            _conn["host"] = host
            _conn["tcp_port"] = tcp_port
            return f"  Connected to {host}:{tcp_port} via TCP."
        except Exception as e:
            return f"  TCP connection failed: {e}"

    # Serial: COM port [baud]
    parts = args.split()
    port = parts[0].strip().upper()
    if not port.startswith("COM"):
        port = "COM" + port.lstrip("COM")

    baud = SERIAL_BAUDS[-2]
    if len(parts) > 1:
        try:
            baud = int(parts[1])
        except ValueError:
            pass

    ser_mod = _ensure_dep("serial", "serial")
    if ser_mod is None:
        return "  pyserial not available. Install: pip install pyserial"

    try:
        ser = ser_mod.Serial(port, baud, timeout=1, write_timeout=2)
        _conn["type"] = "serial"
        _conn["ser"] = ser
        _conn["port"] = port
        _conn["baud"] = baud
        return f"  Connected to {port} @ {baud} baud."
    except Exception as e:
        return f"  Serial connection failed: {e}"


def _cmd_tcp_connect(args: str) -> str:
    return _cmd_connect(args)


def _cmd_disconnect() -> str:
    if _conn["ser"]:
        try:
            _conn["ser"].close()
        except:
            pass
        _conn["ser"] = None
        msg = f"  Disconnected from {_conn['port']}."
        _conn["port"] = None
        _conn["baud"] = None
    elif _conn["sock"]:
        try:
            _conn["sock"].close()
        except:
            pass
        _conn["sock"] = None
        msg = f"  Disconnected from {_conn['host']}:{_conn['tcp_port']}."
        _conn["host"] = None
        _conn["tcp_port"] = None
    else:
        return "  Not connected."
    _conn["type"] = None
    _conn["monitor"] = False
    _conn["buffer"] = ""
    return msg


def _cmd_send(data: str) -> str:
    if not data.strip():
        return "  Usage: micro send <data>"

    if _conn["ser"]:
        try:
            _conn["ser"].write((data + "\n").encode("utf-8", errors="replace"))
            # Try to read response
            time.sleep(0.3)
            response = ""
            while _conn["ser"].in_waiting:
                response += _conn["ser"].read(1024).decode("utf-8", errors="replace")
            if response.strip():
                return f"  Sent: {data}\n  Response: {response.strip()}"
            return f"  Sent: {data}"
        except Exception as e:
            return f"  Send error: {e}"
    elif _conn["sock"]:
        try:
            _conn["sock"].sendall((data + "\n").encode("utf-8", errors="replace"))
            _conn["sock"].settimeout(2)
            try:
                response = _conn["sock"].recv(4096).decode("utf-8", errors="replace")
                if response.strip():
                    return f"  Sent: {data}\n  Response: {response.strip()}"
            except socket.timeout:
                pass
            return f"  Sent: {data}"
        except Exception as e:
            return f"  Send error: {e}"
    else:
        return "  Not connected. Use 'micro connect <port>' first."


def _cmd_read(args: str) -> str:
    n = 10
    if args.strip():
        try:
            n = int(args.strip())
        except ValueError:
            pass

    if _conn["ser"]:
        try:
            lines = []
            for _ in range(n):
                line = _conn["ser"].readline().decode("utf-8", errors="replace").strip()
                if line:
                    lines.append(line)
            if lines:
                return "  RECEIVED:\n" + "\n".join(f"  {l}" for l in lines)
            return "  No data received."
        except Exception as e:
            return f"  Read error: {e}"
    elif _conn["sock"]:
        try:
            _conn["sock"].settimeout(2)
            data = _conn["sock"].recv(4096).decode("utf-8", errors="replace").strip()
            if data:
                return "  RECEIVED:\n  " + data
            return "  No data received."
        except socket.timeout:
            return "  No data received (timeout)."
        except Exception as e:
            return f"  Read error: {e}"
    else:
        return "  Not connected. Use 'micro connect <port>' first."


def _cmd_monitor(args: str) -> str:
    sub = args.strip().lower()
    if sub in ("off", "stop", "0", "false"):
        _conn["monitor"] = False
        return "  Monitor stopped."
    elif sub in ("on", "start", "1", "true") or not sub:
        if _conn["ser"] is None and _conn["sock"] is None:
            return "  Not connected. Connect first."
        _conn["monitor"] = True
        thread = threading.Thread(target=_monitor_loop, daemon=True)
        thread.start()
        return "  Monitor started. Data will appear in responses."
    else:
        return "  Usage: micro monitor [on|off]"


def _monitor_loop():
    while _conn["monitor"]:
        try:
            if _conn["ser"] and _conn["ser"].in_waiting:
                data = _conn["ser"].read(1024).decode("utf-8", errors="replace")
                _conn["buffer"] += data
            elif _conn["sock"]:
                _conn["sock"].settimeout(0.5)
                try:
                    data = _conn["sock"].recv(1024).decode("utf-8", errors="replace")
                    _conn["buffer"] += data
                except socket.timeout:
                    pass
        except:
            _conn["monitor"] = False
            break
        time.sleep(0.1)


def _cmd_info() -> str:
    if _conn["ser"]:
        return (
            f"  Microcontroller Connection\n"
            f"  Type:   Serial\n"
            f"  Port:   {_conn['port']}\n"
            f"  Baud:   {_conn['baud']}\n"
            f"  Status: Connected\n"
            f"  Buffer: {len(_conn['buffer'])} bytes\n"
            f"  Monitor: {'ON' if _conn['monitor'] else 'OFF'}"
        )
    elif _conn["sock"]:
        return (
            f"  Microcontroller Connection\n"
            f"  Type:   TCP/IP\n"
            f"  Host:   {_conn['host']}:{_conn['tcp_port']}\n"
            f"  Status: Connected\n"
            f"  Buffer: {len(_conn['buffer'])} bytes\n"
            f"  Monitor: {'ON' if _conn['monitor'] else 'OFF'}"
        )
    else:
        return (
            "  Microcontroller Connection\n"
            "  Status: Disconnected\n"
            "  Use 'micro scan' to find ports, then 'micro connect <port>'."
        )


def _cmd_lora(args: str) -> str:
    parts = args.strip().split(maxsplit=1)
    if not parts:
        return "  Usage: micro lora send <data>  or  micro lora recv"
    sub = parts[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if sub == "send":
        if not rest:
            return "  Usage: micro lora send <data>"
        if _conn["ser"] is None:
            return "  Not connected. Connect to LoRa module serial first."
        # LoRa modules use AT commands via serial
        at_cmd = f"AT+SEND={rest}\r\n"
        try:
            _conn["ser"].write(at_cmd.encode())
            time.sleep(0.5)
            response = ""
            while _conn["ser"].in_waiting:
                response += _conn["ser"].read(1024).decode("utf-8", errors="replace")
            return f"  LoRa sent: {rest}\n  Response: {response.strip() or 'OK'}"
        except Exception as e:
            return f"  LoRa send error: {e}"
    elif sub in ("recv", "receive", "read"):
        if _conn["ser"] is None:
            return "  Not connected. Connect to LoRa module serial first."
        try:
            _conn["ser"].write(b"AT+RECV\r\n")
            time.sleep(0.5)
            response = ""
            while _conn["ser"].in_waiting:
                response += _conn["ser"].read(1024).decode("utf-8", errors="replace")
            return f"  LoRa received: {response.strip() or 'No data'}"
        except Exception as e:
            return f"  LoRa receive error: {e}"
    else:
        return f"  Unknown LoRa sub-command '{sub}'. Use: micro lora send <data> | recv"
