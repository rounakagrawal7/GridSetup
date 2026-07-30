"""
GRID Radio Module — HAM radio / SDR / shortwave integration
Radio-Browser.info (free, no key), KiwiSDR network, RTL-SDR (optional)
"""

import json
import re
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone

RADIO_BROWSER_APIS = [
    "https://de1.api.radio-browser.info",
    "https://at1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
]
KIWI_DIRECTORY = "http://kiwisdr.com/public/"
KIWI_FALLBACKS = [
    "http://rx.linkfanel.net/kiwisdr_com.js",
    "https://rx.skywavelinux.com/kiwisdr_com.js",
]

def _ensure_dep(pkg_name: str, import_name: str = ""):
    """Import and return a module, auto-installing if missing"""
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
                import importlib
                return importlib.import_module(mod)
            sys.stderr.write(f"Failed to install {pkg_name}\n")
            for line in result.stderr.strip().splitlines()[-3:]:
                sys.stderr.write(f"  {line}\n")
        except Exception as e:
            sys.stderr.write(f"Error installing {pkg_name}: {e}\n")
        raise ImportError(f"Required dependency '{pkg_name}' could not be installed. Run: pip install {pkg_name}")


def _fetch(url: str, timeout: int = 10) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GRID/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode()
    except urllib.error.HTTPError as e:
        return json.dumps({"error": f"HTTP {e.code}: {e.reason}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def _fetch_json(url: str, timeout: int = 10) -> dict:
    raw = _fetch(url, timeout)
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return {"error": "Invalid JSON response", "raw": raw[:500]}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _help() -> str:
    return (
        "  RADIO COMMAND REFERENCE\n"
        "  " + "=" * 50 + "\n\n"
        "  COMMAND                                        WHAT IT DOES\n"
        "  " + "-" * 70 + "\n"
        "  radio browser search <query>                   Search broadcast stations by name/tag\n"
        "  radio browser bycountry <country>               List top stations in a country\n"
        "  radio browser bytag <tag>                       Browse stations by genre (news, jazz, ham)\n"
        "  radio browser top [limit]                       Top voted stations globally\n"
        "  radio browser play <# or name>                  Get stream URL (open in browser)\n\n"
        "  radio kiwi list                                 List all public KiwiSDR receivers\n"
        "  radio kiwi bycountry <country>                  Filter KiwiSDRs by country\n"
        "  radio kiwi open <host>                          Open KiwiSDR Web UI in browser\n"
        "  radio kiwi stream <host> <freq_mhz>             Stream audio from KiwiSDR (WebSocket)\n"
        "  radio kiwi status <host>                        Query KiwiSDR node status\n\n"
        "  radio rtl list                                  List connected RTL-SDR devices (requires dongle)\n"
        "  radio rtl tune <freq_mhz> [duration_s]          Tune RTL-SDR, demodulate FM, save .wav\n"
        "  radio rtl scan [start_mhz] [end_mhz]            Scan frequencies for active signals\n\n"
        "  radio help                                      Show this reference\n\n"
        "  Radio-Browser.info:  free, no API key — broadcast stations worldwide\n"
        "  KiwiSDR:  public SDR receiver network — 10 kHz to 30 MHz\n"
        "  RTL-SDR:  local USB dongle (optional) — installed on first use\n"
    )


# ═══════════════════════════════════════════════════════════════════
# Radio-Browser.info API (Tier 1)
# ═══════════════════════════════════════════════════════════════════

def _rb_fetch(path: str) -> list:
    """Fetch from Radio-Browser API with fallback servers"""
    for api in RADIO_BROWSER_APIS:
        url = f"{api}{path}"
        data = _fetch(url, timeout=8)
        try:
            result = json.loads(data)
            if isinstance(result, list):
                return result
            if isinstance(result, dict) and "error" not in result:
                return result
        except (json.JSONDecodeError, ValueError):
            continue
    return []


def _rb_search(query: str, limit: int = 10) -> list:
    path = f"/json/stations/search?limit={limit}&name={urllib.parse.quote(query)}"
    return _rb_fetch(path)


def _rb_by_country(country: str, limit: int = 10) -> list:
    path = f"/json/stations/bycountry/{urllib.parse.quote(country)}?limit={limit}"
    return _rb_fetch(path)


def _rb_by_tag(tag: str, limit: int = 10) -> list:
    path = f"/json/stations/bytag/{urllib.parse.quote(tag)}?limit={limit}"
    return _rb_fetch(path)


def _rb_top(limit: int = 15) -> list:
    path = f"/json/stations/topvote?limit={limit}"
    return _rb_fetch(path)


def _format_stations(stations: list, title: str) -> str:
    if not stations:
        return f"No stations found for '{title}'."
    if isinstance(stations, dict) and "error" in stations:
        return f"API error: {stations['error']}"

    lines = [f"  {title}"]
    lines.append("  " + "=" * 60)
    lines.append(f"  {'#':<4} {'Name':<40} {'Country':<20} {'Codec':<6} {'Bitrate':<8}")
    lines.append("  " + "-" * 78)

    for i, s in enumerate(stations[:20], 1):
        name = (s.get("name", "?") or "?")[:38]
        country = (s.get("country", "?") or "?")[:18]
        codec = (s.get("codec", "?") or "?")[:5]
        bitrate = s.get("bitrate", 0) or 0
        lines.append(f"  {i:<4} {name:<40} {country:<20} {codec:<6} {bitrate:<8}")

    lines.append("")
    lines.append(f"  Showing {min(len(stations), 20)} of {len(stations)} stations")
    lines.append(f"  Use 'radio browser play <#>' to get a stream URL")
    return "\n".join(lines)


def _cmd_browser(args: str) -> str:
    parts = args.split(maxsplit=2)
    sub = parts[0].lower() if parts else ""

    if sub == "search":
        query = parts[1] if len(parts) > 1 else ""
        limit = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
        if not query:
            return "Usage: radio browser search <query> [limit]"
        stations = _rb_search(query, limit)
        return _format_stations(stations, f"Stations matching '{query}'")

    if sub == "bycountry":
        country = parts[1] if len(parts) > 1 else ""
        limit = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
        if not country:
            return "Usage: radio browser bycountry <country> [limit]"
        stations = _rb_by_country(country, limit)
        return _format_stations(stations, f"Stations in {country}")

    if sub == "bytag":
        tag = parts[1] if len(parts) > 1 else ""
        limit = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
        if not tag:
            return "Usage: radio browser bytag <tag> [limit]"
        stations = _rb_by_tag(tag, limit)
        return _format_stations(stations, f"Stations tagged '{tag}'")

    if sub == "top":
        limit = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 15
        stations = _rb_top(limit)
        return _format_stations(stations, "Top Voted Stations Worldwide")

    if sub == "play":
        query = parts[1] if len(parts) > 1 else ""
        if not query:
            return "Usage: radio browser play <# or name>"
        try:
            idx = int(query) - 1
            stations = _rb_top(50)
            if 0 <= idx < len(stations):
                s = stations[idx]
                url = s.get("url_resolved") or s.get("url", "")
                return (
                    f"Stream URL for #{idx + 1}: {s.get('name', '?')}\n"
                    f"  URL: {url}\n"
                    f"  Open in browser or media player to listen.\n"
                    f"  Codec: {s.get('codec', '?')}  Bitrate: {s.get('bitrate', '?')} kbps"
                )
            return f"Index {query} out of range. Use 'radio browser top' to see stations."
        except ValueError:
            stations = _rb_search(query, 5)
            if stations:
                s = stations[0]
                url = s.get("url_resolved") or s.get("url", "")
                return (
                    f"Stream URL for '{query}':\n"
                    f"  Name: {s.get('name', '?')}\n"
                    f"  URL: {url}\n"
                    f"  Country: {s.get('country', '?')}\n"
                    f"  Open in browser or media player."
                )
            return f"No stations found matching '{query}'."

    return (
        "Usage: radio browser <search|bycountry|bytag|top|play> [args]\n"
        "  radio browser search <query>       Search stations by name/tag\n"
        "  radio browser bycountry <country>  Stations in a country\n"
        "  radio browser bytag <tag>          Browse by genre\n"
        "  radio browser top [limit]          Top voted stations\n"
        "  radio browser play <#>             Get stream URL by list index"
    )


# ═══════════════════════════════════════════════════════════════════
# KiwiSDR Network (Tier 2)
# ═══════════════════════════════════════════════════════════════════

def _kiwi_parse_nodes(html: str) -> list:
    nodes = []
    pattern = r"<tr[^>]*>.*?</tr>"
    rows = re.findall(pattern, html, re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
        if len(cells) < 6:
            continue
        name = re.sub(r"<[^>]+>", "", cells[0]).strip()
        loc_raw = re.sub(r"<[^>]+>", "", cells[1]).strip()
        lat_match = re.search(r"([-.\d]+)", loc_raw)
        lon_match = re.findall(r"([-.\d]+)", loc_raw)
        lat = float(lat_match.group(1)) if lat_match else 0.0
        lon = float(lon_match[1]) if len(lon_match) > 1 else 0.0
        location = re.sub(r"\([-.\d, ]+\)", "", loc_raw).strip()
        url_match = re.search(r"(http://[^\s<\"']+)", row)
        url = url_match.group(1) if url_match else ""
        host = url.replace("http://", "").split(":")[0] if url else ""
        status = re.sub(r"<[^>]+>", "", cells[2]).strip()
        users = re.sub(r"<[^>]+>", "", cells[3]).strip() if len(cells) > 3 else "?"
        snr = re.sub(r"<[^>]+>", "", cells[4]).strip() if len(cells) > 4 else "?"
        band = re.sub(r"<[^>]+>", "", cells[5]).strip() if len(cells) > 5 else "?"
        nodes.append({
            "name": name, "host": host, "url": url,
            "lat": lat, "lon": lon, "location": location,
            "status": status, "users": users, "snr": snr, "band": band,
        })
    return nodes


def _kiwi_get_nodes() -> list:
    data = _fetch(KIWI_DIRECTORY, timeout=15)
    if data and "error" not in data[:50].lower() and "kiwisdr_com" not in data:
        parsed = _kiwi_parse_nodes(data)
        if parsed:
            return parsed
    for fallback in KIWI_FALLBACKS:
        raw = _fetch(fallback, timeout=15)
        if not raw or "error" in raw[:50].lower():
            continue
        try:
            match = re.search(r"var\s+kiwisdr_com\s*=\s*(\[.*?\])\s*;", raw, re.DOTALL)
            if match:
                cleaned = re.sub(r",\s*]", "]", match.group(1))
                cleaned = re.sub(r",\s*}", "}", cleaned)
                parsed = json.loads(cleaned)
                nodes = []
                for item in parsed:
                    url = item.get("url", "")
                    host = url.replace("http://", "").split(":")[0] if url else ""
                    gps = item.get("gps", "")
                    lat, lon = 0.0, 0.0
                    if gps and "," in str(gps):
                        try:
                            parts = str(gps).split(",")
                            lat = float(parts[0].strip())
                            lon = float(parts[1].strip())
                        except ValueError:
                            pass
                    nodes.append({
                        "name": item.get("name", ""),
                        "host": host,
                        "url": url,
                        "lat": lat,
                        "lon": lon,
                        "location": item.get("loc", ""),
                        "status": "active" if item.get("offline", "no") == "no" else "offline",
                        "users": str(item.get("users", "?")),
                        "snr": str(item.get("snr", "?")),
                        "band": "",
                    })
                return nodes
        except (json.JSONDecodeError, ValueError) as e:
            continue
    return []


def _format_kiwi(nodes: list, title: str) -> str:
    if not nodes:
        return "No KiwiSDR nodes found. Try again later or check http://kiwisdr.com/public/"

    lines = [f"  {title}"]
    lines.append("  " + "=" * 60)
    lines.append(f"  {'#':<4} {'Host':<22} {'Location':<30} {'Users':<6} {'SNR':<6}")
    lines.append("  " + "-" * 68)

    for i, n in enumerate(nodes[:30], 1):
        host = (n.get("host", "") or n.get("url", "").replace("http://", "")[:20])
        loc = (n.get("location", "") or "?")[:28]
        users = n.get("users", "?")
        snr = n.get("snr", "?")
        lines.append(f"  {i:<4} {host:<22} {loc:<30} {users:<6} {snr:<6}")

    lines.append("")
    lines.append(f"  Showing {min(len(nodes), 30)} of {len(nodes)} nodes")
    lines.append("  Use 'radio kiwi open <host>' to open Web UI in browser")
    lines.append("  Use 'radio kiwi stream <host> <freq_mhz>' for audio")
    lines.append("  Use 'radio kiwi status <host>' for detailed node info")
    return "\n".join(lines)


def _cmd_kiwi(args: str) -> str:
    parts = args.split(maxsplit=2)
    sub = parts[0].lower() if parts else ""

    if sub == "list":
        nodes = _kiwi_get_nodes()
        return _format_kiwi(nodes, "Public KiwiSDR Receivers")

    if sub == "bycountry":
        country = parts[1].lower() if len(parts) > 1 else ""
        if not country:
            return "Usage: radio kiwi bycountry <country>"
        nodes = _kiwi_get_nodes()
        matched = [n for n in nodes if country in n.get("location", "").lower()]
        if not matched:
            return f"No KiwiSDR nodes found matching '{country}'."
        return _format_kiwi(matched, f"KiwiSDR in/near '{country}'")

    if sub == "open":
        host = parts[1] if len(parts) > 1 else ""
        if not host:
            return "Usage: radio kiwi open <host>"
        if not host.startswith("http"):
            host = f"http://{host}:8073"
        return f"Open this URL in your browser:\n  {host}\n\nThe KiwiSDR Web UI lets you tune, listen, and view the waterfall."

    if sub == "status":
        host = parts[1] if len(parts) > 1 else ""
        if not host:
            return "Usage: radio kiwi status <host>"
        if "://" not in host:
            host = f"http://{host}:8073"
        data = _fetch_json(f"{host}/status", timeout=10)
        if "error" in data:
            return f"Could not query {host}: {data['error']}"
        lines = [f"  KiwiSDR Status — {host}"]
        lines.append("  " + "=" * 50)
        for k, v in sorted(data.items()):
            if isinstance(v, (int, float, str)):
                lines.append(f"  {k}: {v}")
        return "\n".join(lines[:40])

    if sub == "stream":
        websocket = _ensure_dep("websocket-client", "websocket")
        rest = args[len("stream"):].strip()
        parts = rest.split()
        if len(parts) < 2:
            return "Usage: radio kiwi stream <host> <freq_mhz> [duration_s]"
        host = parts[0]
        try:
            freq = float(parts[1])
        except ValueError:
            return f"Invalid frequency: {parts[1]}"
        duration = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 10
        domain = host.split(":")[0] if ":" in host else host
        port = host.split(":")[1] if ":" in host else "8073"
        ws_url = f"ws://{domain}:{port}/ws"
        try:
            ws = websocket.create_connection(ws_url, timeout=10)
        except Exception as e:
            msg = (
                f"Could not connect to KiwiSDR WebSocket at {ws_url}\n"
                f"  Reason: {e}\n\n"
                f"  Use 'radio kiwi open {domain}' to open the Web UI in your browser\n"
                f"  and tune/listen there with the full waterfall interface.\n"
            )
            try:
                http_url = f"http://{domain}:{port}/status"
                req = urllib.request.Request(http_url, headers={"User-Agent": "GRID/2.0"})
                urllib.request.urlopen(req, timeout=5)
                msg += (
                    f"\n  The node IS reachable (HTTP port {port} responds), but WebSocket"
                    f" access requires a browser session (captcha/auth).\n"
                )
            except Exception:
                msg += (
                    f"\n  The node is NOT reachable on port {port}."
                    f" It may be offline or blocking connections.\n"
                    f"  Try another node: radio kiwi list\n"
                )
            msg += (
                f"\n  For broadcast radio (no SDR needed), try:\n"
                f"    radio browser bycountry <country>\n"
                f"    radio browser play <#>"
            )
            return msg
        try:
            ws.send(json.dumps({"type": "tune", "freq": int(freq * 1e6)}))
            audio_data = b""
            for _ in range(duration * 20):
                try:
                    msg = ws.recv()
                    if isinstance(msg, bytes):
                        audio_data += msg
                except Exception:
                    break
            ws.close()
            wav_path = f"radio_kiwi_{freq}mhz_{_ts().replace(':', '-')[:19]}.wav"
            if audio_data:
                import struct
                sample_rate = 8000
                with open(wav_path, "wb") as f:
                    f.write(b"RIFF")
                    f.write(struct.pack("<I", 36 + len(audio_data)))
                    f.write(b"WAVE")
                    f.write(b"fmt ")
                    f.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
                    f.write(b"data")
                    f.write(struct.pack("<I", len(audio_data)))
                    f.write(audio_data)
                return f"Captured {len(audio_data)} bytes from {host} at {freq} MHz -> {wav_path}"
            return f"Connected but no audio received from {host} at {freq} MHz (duration: {duration}s)"
        except Exception as e:
            return f"KiwiSDR stream error: {e}"

    return (
        "Usage: radio kiwi <list|bycountry|open|stream|status> [args]\n"
        "  radio kiwi list                         List all public KiwiSDR nodes\n"
        "  radio kiwi bycountry <country>          Filter by country/location\n"
        "  radio kiwi open <host>                  Open Web UI in browser\n"
        "  radio kiwi stream <host> <freq> [dur]   Stream audio via WebSocket\n"
        "  radio kiwi status <host>                Query node status"
    )


# ═══════════════════════════════════════════════════════════════════
# RTL-SDR (Tier 3 — optional hardware)
# ═══════════════════════════════════════════════════════════════════

def _cmd_rtl(args: str) -> str:
    rtlsdr = _ensure_dep("pyrtlsdr", "rtlsdr")

    parts = args.split(maxsplit=3)
    sub = parts[0].lower() if parts else ""

    if sub == "list":
        try:
            from rtlsdr import RtlSdr
            sdr = RtlSdr()
            serial = sdr.serial_number
            sdr.close()
            return f"RTL-SDR detected: Serial {serial or 'unknown'}"
        except Exception as e:
            return f"Error detecting RTL-SDR: {e}\nMake sure the dongle is plugged in."

    if sub == "tune":
        if len(parts) < 2:
            return "Usage: radio rtl tune <freq_mhz> [duration_s]"
        try:
            freq = float(parts[1])
        except ValueError:
            return f"Invalid frequency: {parts[1]}"
        duration = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 5
        try:
            sdr = RtlSdr()
            sdr.sample_rate = 2.048e6
            sdr.center_freq = freq * 1e6
            sdr.gain = "auto"
            samples = sdr.read_samples(256 * 1024)
            sdr.close()
            import numpy as np
            import struct
            fm = np.diff(np.unwrap(np.angle(samples)))
            fm = np.concatenate([[0], fm])
            fm = fm / np.max(np.abs(fm)) if np.max(np.abs(fm)) > 0 else fm
            fm_int16 = (fm * 32767).astype(np.int16)
            sample_rate_audio = int(sdr.sample_rate / 4)
            wav_path = f"radio_rtl_{freq}mhz.wav"
            with open(wav_path, "wb") as f:
                f.write(b"RIFF")
                f.write(struct.pack("<I", 36 + len(fm_int16) * 2))
                f.write(b"WAVE")
                f.write(b"fmt ")
                f.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate_audio, sample_rate_audio * 2, 2, 16))
                f.write(b"data")
                f.write(struct.pack("<I", len(fm_int16) * 2))
                f.write(fm_int16.tobytes())
            return (
                f"Tuned to {freq} MHz — captured {len(samples)} samples\n"
                f"  Demodulated FM audio -> {wav_path}\n"
                f"  Sample rate: {sdr.sample_rate/1e6:.1f} MHz\n"
                f"  File size: {len(fm_int16) * 2} bytes\n"
                f"  Open the .wav file in any media player to listen."
            )
        except Exception as e:
            return f"RTL-SDR tune error: {e}"

    if sub == "scan":
        start_mhz = float(parts[1]) if len(parts) > 1 else 88.0
        end_mhz = float(parts[2]) if len(parts) > 2 else 108.0
        step_mhz = float(parts[3]) if len(parts) > 3 else 0.2
        try:
            sdr = RtlSdr()
            sdr.sample_rate = 2.048e6
            sdr.gain = "auto"
            results = []
            freq = start_mhz
            while freq <= end_mhz:
                sdr.center_freq = freq * 1e6
                samples = sdr.read_samples(128 * 1024)
                import numpy as np
                power = 10 * np.log10(np.mean(np.abs(samples) ** 2) + 1e-10)
                results.append((freq, power))
                freq += step_mhz
            sdr.close()
            lines = [f"  RTL-SDR Scan: {start_mhz} MHz to {end_mhz} MHz (step {step_mhz} MHz)"]
            lines.append("  " + "=" * 60)
            lines.append(f"  {'Freq (MHz)':<14} {'Signal (dB)':<14} {'Bar'}")
            lines.append("  " + "-" * 50)
            for f, p in results:
                bars = max(0, min(20, int((p + 50) / 3)))
                bar = "█" * bars + "░" * (20 - bars)
                lines.append(f"  {f:<14.1f} {p:<14.1f} {bar}")
            return "\n".join(lines)
        except Exception as e:
            return f"RTL-SDR scan error: {e}"

    return (
        "Usage: radio rtl <list|tune|scan> [args]\n"
        "  radio rtl list                          List RTL-SDR devices\n"
        "  radio rtl tune <freq_mhz> [duration_s]  Tune + demod FM + save .wav\n"
        "  radio rtl scan [start] [end] [step]     Scan frequencies with signal meter\n\n"
        "Note: Requires an RTL-SDR USB dongle and pyrtlsdr installed."
    )


# ═══════════════════════════════════════════════════════════════════
# Main dispatch
# ═══════════════════════════════════════════════════════════════════

def radio_main(input_str: str) -> str:
    if not input_str or input_str.strip().lower() in ("help", "-h", "--help", "?"):
        return _help()

    parts = input_str.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd == "browser":
        return _cmd_browser(args)

    if cmd == "kiwi":
        return _cmd_kiwi(args)

    if cmd == "rtl":
        return _cmd_rtl(args)

    if cmd == "browser" or cmd == "broadcast":
        return _cmd_browser(args)

    return (
        f"Unknown radio sub-command: {cmd}\n\n"
        f"Available: browser, kiwi, rtl\n"
        f"Use 'radio help' for full reference."
    )
