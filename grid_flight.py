"""
GRID Flight Module — Real-time flight tracking using OpenSky Network API
Sub-commands for `osint flight` and `osint flight_tracker`
Generates timestamped intelligence reports with data analysis.
"""

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone


OPENSKY_API = "https://opensky-network.org/api"


def _fetch(url: str, timeout: int = 10) -> dict:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GRID/2.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _build_report(title: str, states: list, label: str = "", max_rows: int = 30) -> str:
    now = _ts()
    lines = []
    sep = "=" * 60
    dashes = "-" * 60

    lines.append(f"  FLIGHT INTELLIGENCE REPORT")
    lines.append(f"  {title}")
    lines.append(f"  Generated: {now}")
    lines.append(sep)

    total = len(states)
    altitudes = [s[7] for s in states if s[7] is not None]
    velocities = [s[9] for s in states if s[9] is not None]
    countries = {}
    callsigns = []
    for s in states:
        c = (s[2] or "Unknown").strip()
        countries[c] = countries.get(c, 0) + 1
        cs = (s[1] or "N/A").strip()
        if cs != "N/A":
            callsigns.append(cs)

    avg_alt = sum(altitudes) / len(altitudes) if altitudes else 0
    avg_spd = sum(velocities) / len(velocities) if velocities else 0
    max_alt = max(altitudes) if altitudes else 0
    min_alt = min(altitudes) if altitudes else 0
    max_spd = max(velocities) if velocities else 0
    top_countries = sorted(countries.items(), key=lambda x: -x[1])[:5]

    airline_codes = set()
    for cs in callsigns:
        if len(cs) >= 2:
            airline_codes.add(cs[:2] if cs[:2].isalpha() else cs[:3])

    lines.append(f"\n  [ANALYSIS]")
    lines.append(dashes)
    lines.append(f"  Total active flights:   {total}")
    lines.append(f"  Unique airline codes:   {len(airline_codes)}")
    lines.append(f"  Countries represented:  {len(countries)}")
    if altitudes:
        lines.append(f"  Altitude range:         {min_alt:.0f}m - {max_alt:.0f}m")
        lines.append(f"  Average altitude:       {avg_alt:.0f}m")
        lines.append(f"  Average speed:          {avg_spd:.0f} m/s ({avg_spd * 3.6:.0f} km/h)")
        lines.append(f"  Max speed observed:     {max_spd:.0f} m/s ({max_spd * 3.6:.0f} km/h)")
    if label:
        lines.append(f"  Search area:            {label}")

    if top_countries:
        lines.append(f"\n  Top countries:")
        for c, n in top_countries:
            pct = n / total * 100 if total else 0
            lines.append(f"    {c:<20} {n:>4} flights ({pct:.1f}%)")

    lines.append(f"\n  [FLIGHT LIST]")
    lines.append(dashes)
    lines.append(f"  {'Callsign':<14} {'Country':<20} {'Alt(m)':<10} {'Speed':<8} {'Heading':<8} {'Lat':<10} {'Lon':<10}")
    lines.append(f"  {'-'*14} {'-'*20} {'-'*10} {'-'*8} {'-'*8} {'-'*10} {'-'*10}")

    sorted_states = sorted(states, key=lambda s: s[7] if s[7] is not None else -1, reverse=True)

    for s in sorted_states[:max_rows]:
        callsign = (s[1] or "N/A").strip()[:12]
        country = (s[2] or "Unknown")[:18]
        alt = f"{s[7]:.0f}" if s[7] is not None else "N/A"
        spd = f"{s[9]:.0f}" if s[9] is not None else "N/A"
        hdg = f"{s[10]:.0f}" if s[10] is not None else "N/A"
        lat = f"{s[6]:.2f}" if s[6] is not None else "N/A"
        lon = f"{s[5]:.2f}" if s[5] is not None else "N/A"
        lines.append(f"  {callsign:<14} {country:<20} {alt:<10} {spd:<8} {hdg:<8} {lat:<10} {lon:<10}")

    shown = min(total, max_rows)
    lines.append(f"\n  Showing {shown} of {total} flights ({total - shown} omitted)")
    lines.append(sep)
    lines.append(f"  GRID Flight Intelligence  |  {now}")
    return "\n".join(lines)


def flight_search(query: str) -> str:
    q = query.strip().strip('"').strip("'")
    if not q:
        return "Usage: osint flight <callsign | airline | country | airport>"

    data = _fetch(f"{OPENSKY_API}/states/all")
    if "error" in data:
        return f"Error contacting OpenSky: {data['error']}"

    all_states = data.get("states", [])
    if not all_states:
        return "No flight data available from OpenSky."

    q_lower = q.lower()
    matches = []
    for s in all_states:
        callsign = (s[1] or "").strip().lower()
        country = (s[2] or "").lower()
        icao = (s[0] or "").lower()
        match_callsign = q_lower in callsign or callsign.startswith(q_lower)
        match_country = q_lower in country if len(q_lower) > 3 else False
        match_icao = q_lower == icao[:len(q_lower)]
        if match_callsign or match_country or match_icao:
            matches.append(s)

    if not matches:
        return (
            f"No live flights found matching '{q}'.\n"
            f"  Try: osint flight AI101        (by callsign)\n"
            f"       osint flight India        (by country/airline)\n"
            f"       osint flight_tracker      (worldwide snapshot)\n"
            f"       osint flight_tracker 27.71 85.32 100"
        )

    return _build_report(f"Search: {q.upper()}", matches, label=f"Matched {len(matches)} of {len(all_states)} total flights")


def flight_tracker(params: str) -> str:
    p = params.strip()

    lamin, lamax, lomin, lomax = -90, 90, -180, 180
    label = "Worldwide"

    if p:
        parts = p.split()
        if len(parts) >= 2:
            try:
                lat, lon = float(parts[0]), float(parts[1])
                radius = float(parts[2]) if len(parts) >= 3 else 50.0
                delta = radius / 111.0
                lamin = lat - delta
                lamax = lat + delta
                lomin = lon - delta
                lomax = lon + delta
                label = f"{lat}, {lon} +/-{radius:.0f}km"
            except ValueError:
                pass

    url = f"{OPENSKY_API}/states/all?lamin={lamin}&lamax={lamax}&lomin={lomin}&lomax={lomax}"
    data = _fetch(url)
    if "error" in data:
        return f"Error: {data['error']}"

    states = data.get("states", [])
    if not states:
        return (
            f"No live flights found in area: {label}\n\n"
            f"Try a larger radius or check coordinates.\n"
            f"Use 'osint flight_tracker' alone for a worldwide snapshot."
        )

    return _build_report(f"Regional Tracker: {label}", states, label=label)