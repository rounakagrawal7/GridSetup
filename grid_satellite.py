"""
GRID Satellite Module — Free open-source satellite tracking & data
Celestrak TLE + wheretheiss.at + Open Notify — no API keys required
"""

import json
import re
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime, timezone


CELESTRAK_TLE = "https://celestrak.org/NORAD/elements/gp.php"
WHERETHEISS = "https://api.wheretheiss.at/v1/satellites"
OPEN_NOTIFY = "http://api.open-notify.org"

# Popular satellites for quick lookup
POPULAR_SATS = [
    (25544, "ISS (ZARYA)", "International Space Station"),
    (20580, "HUBBLE", "Hubble Space Telescope"),
    (25994, "NOAA 18", "NOAA weather satellite"),
    (33591, "NOAA 19", "NOAA weather satellite"),
    (43013, "NOAA 20", "NOAA weather satellite"),
    (27453, "NOAA 17", "NOAA weather satellite"),
    (28470, "NOAA 15", "NOAA weather satellite"),
    (26609, "METEOSAT-9", "EUMETSAT weather satellite"),
    (28912, "METEOSAT-10", "EUMETSAT weather satellite"),
    (38049, "METEOSAT-11", "EUMETSAT weather satellite"),
    (40938, "GOES-16", "NOAA GOES East"),
    (41866, "GOES-17", "NOAA GOES West"),
    (43226, "GOES-18", "NOAA GOES West"),
    (24876, "GPS BIIR-2", "GPS satellite"),
    (26605, "GPS BIIR-11", "GPS satellite"),
    (32711, "GPS BIIR-14", "GPS satellite"),
    (39533, "GALILEO 5", "Galileo navigation"),
    (40544, "GALILEO 9", "Galileo navigation"),
    (41175, "GALILEO 12", "Galileo navigation"),
    (25460, "GLONASS 786", "GLONASS navigation"),
    (32393, "GLONASS 730", "GLONASS navigation"),
    (39479, "IRIDIUM 101", "Iridium satellite"),
    (42803, "STARLINK-1007", "Starlink satellite"),
    (44713, "STARLINK-2380", "Starlink satellite"),
    (47940, "STARLINK-3359", "Starlink satellite"),
    (43908, "TIANGONG-1", "Chinese space station"),
    (48274, "TIANGONG-2", "Chinese space station"),
    (54216, "TIANGONG-3", "Chinese space station (CSS)"),
    (25338, "IRIDIUM 7", "Iridium satellite"),
    (40652, "SOYUZ-TMA", "Soyuz spacecraft"),
    (49272, "CREW DRAGON", "SpaceX Crew Dragon"),
    (4515, "VANGUARD", "Oldest satellite in orbit"),
    (9940, "GPS BII-09", "Early GPS satellite"),
    (40069, "SOFIA", "Stratospheric Observatory"),
    (38771, "NUSTAR", "NuSTAR space telescope"),
    (43480, "ICESAT-2", "NASA ice satellite"),
    (37820, "LANDSAT-8", "NASA Earth observation"),
    (49263, "LANDSAT-9", "NASA Earth observation"),
    (39084, "SENTINEL-1A", "ESA radar satellite"),
    (41456, "SENTINEL-2A", "ESA optical satellite"),
    (40663, "SENTINEL-3A", "ESA ocean satellite"),
    (42915, "SWARM-B", "ESA magnetic field"),
    (27424, "SWARM-A", "ESA magnetic field"),
    (37162, "KOMPSAT-3", "KARI Earth observation"),
    (38334, "AEDC-AERO-4", "US Air Force"),
    (47938, "CAPSTONE", "NASA lunar orbiter"),
    (25397, "XMM-NEWTON", "ESA X-ray telescope"),
    (31592, "FREGAT", "Space tug"),
]

SAT_GROUPS = {
    "active": "All active satellites",
    "iss": "ISS and crew vehicles",
    "weather": "Weather/NOAA/GOES/Meteosat",
    "gps": "GPS navigation satellites",
    "glonass": "GLONASS navigation",
    "galileo": "Galileo navigation",
    "starlink": "SpaceX Starlink",
    "science": "Science telescopes",
    "earth": "Earth observation",
    "amateur": "Amateur radio satellites",
}

# Group membership (NORAD IDs by group name)
SAT_GROUP_IDS = {
    "iss": [25544, 49272, 54216, 48274],
    "weather": [25994, 33591, 43013, 27453, 28470, 26609, 28912, 38049, 40938, 41866, 43226],
    "gps": [24876, 26605, 32711, 9940],
    "glonass": [25460, 32393],
    "galileo": [39533, 40544, 41175],
    "starlink": [42803, 44713, 47940],
    "science": [20580, 40069, 38771, 25397],
    "earth": [37820, 49263, 39084, 41456, 40663, 42915, 27424, 37162],
    "amateur": [25338, 39479],
}


def _fetch(url: str, timeout: int = 10) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
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
        return {"error": "Invalid JSON response"}


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _help() -> str:
    return (
        "  SATELLITE COMMAND REFERENCE\n"
        "  " + "=" * 55 + "\n\n"
        "  COMMAND                                    WHAT IT DOES\n"
        "  " + "-" * 70 + "\n"
        "  satellite iss                              ISS current position + crew onboard\n"
        "  satellite position <id>                    Current position of any satellite (NORAD ID)\n"
        "  satellite passes <id> <lat> <lon> [days]   Pass predictions for a ground location\n"
        "  satellite tle <id>                         Get TLE orbital data for analysis\n"
        "  satellite search <query>                   Search satellite catalog by name\n"
        "  satellite list [group]                     List satellites (active, iss, weather, gps, etc.)\n"
        "  satellite analyze <id>                     Full orbit analysis (altitude, velocity, position)\n\n"
        "  satellite help                             Show this reference\n\n"
        "  Data sources: Celestrak, wheretheiss.at, Open Notify — all free, no API keys.\n"
        "  Use a NORAD ID (e.g. 25544 for ISS) or a satellite name.\n"
    )


def _cmd_iss() -> str:
    """ISS current position + crew"""
    pos_data = _fetch_json(f"{WHERETHEISS}/25544", timeout=10)
    astro_data = _fetch_json(f"{OPEN_NOTIFY}/astros.json", timeout=10)
    iss_now = _fetch_json(f"{OPEN_NOTIFY}/iss-now.json", timeout=10)

    lines = ["  INTERNATIONAL SPACE STATION"]
    lines.append("  " + "=" * 50)

    if "error" not in pos_data:
        lines.append(f"  Latitude:  {pos_data.get('latitude', '?'):.4f}")
        lines.append(f"  Longitude: {pos_data.get('longitude', '?'):.4f}")
        lines.append(f"  Altitude:  {pos_data.get('altitude', 0):.1f} km")
        lines.append(f"  Velocity:  {pos_data.get('velocity', 0):.1f} km/h")
        lines.append(f"  Units:     feet: {pos_data.get('velocity', 0) / 1.609:.0f} mph")
        lines.append(f"  Updated:   {pos_data.get('timestamp' ,'?')}")
        lines.append("")
        map_url = (
            f"https://www.google.com/maps?"
            f"q={pos_data.get('latitude', 0)},{pos_data.get('longitude', 0)}"
            f"&z=3"
        )
        lines.append(f"  Map: {map_url}")

    if "error" not in astro_data:
        people = astro_data.get("people", [])
        iss_crew = [p for p in people if p.get("craft") == "ISS"]
        tn_crew = [p for p in people if p.get("craft") == "Tiangong"]
        lines.append("")
        lines.append(f"  Crew (ISS): {len(iss_crew)}")
        for p in iss_crew:
            lines.append(f"    {p['name']}")
        lines.append(f"  Crew (Tiangong): {len(tn_crew)}")
        for p in tn_crew:
            lines.append(f"    {p['name']}")
        lines.append(f"  Total humans in space: {astro_data.get('number', 0)}")

    if "error" in pos_data and "error" in astro_data:
        return "  Satellite API unavailable. Try again later."

    return "\n".join(lines)


def _cmd_position(norad_id: str) -> str:
    """Current position of a satellite by NORAD ID"""
    try:
        int(norad_id)
    except ValueError:
        return f"Invalid NORAD ID: '{norad_id}'. Use a numeric ID (e.g. 25544 for ISS)."

    data = _fetch_json(f"{WHERETHEISS}/{norad_id}", timeout=10)
    if "error" in data:
        return f"  Satellite {norad_id} not found. Try 'satellite list' or 'satellite search'."

    name = data.get("name", "?").upper()
    lines = [f"  SATELLITE {norad_id} — {name}"]
    lines.append("  " + "=" * 50)
    lines.append(f"  Latitude:   {data.get('latitude', '?'):.4f}")
    lines.append(f"  Longitude:  {data.get('longitude', '?'):.4f}")
    lines.append(f"  Altitude:   {data.get('altitude', 0):.1f} km")
    lines.append(f"  Velocity:   {data.get('velocity', 0):.1f} km/h ({data.get('velocity', 0) / 1.609:.0f} mph)")
    lines.append(f"  Visibility: {data.get('visibility', '?')}")
    lines.append(f"  Footprint:  {data.get('footprint', 0):.0f} km")
    lines.append(f"  Perigee:    {data.get('perigee', 0):.1f} km")
    lines.append(f"  Apogee:     {data.get('apogee', 0):.1f} km")
    lines.append(f"  Inclination: {data.get('inclination', 0):.2f} deg")
    lines.append(f"  Period:     {data.get('period', 0):.2f} min")
    lines.append(f"  Days since launch: {data.get('days_since_launch', 0):.0f}")
    lines.append("")
    map_url = f"https://www.google.com/maps?q={data.get('latitude', 0)},{data.get('longitude', 0)}&z=3"
    lines.append(f"  Map: {map_url}")
    return "\n".join(lines)


def _cmd_passes(norad_id: str, lat: str, lon: str, days_str: str = "2") -> str:
    """Pass predictions for a satellite over a ground location"""
    try:
        int(norad_id)
        lat_f = float(lat)
        lon_f = float(lon)
        days = int(days_str) if days_str.isdigit() else 2
    except ValueError:
        return "Usage: satellite passes <norad_id> <latitude> <longitude> [days]"

    seconds = days * 86400
    url = f"{WHERETHEISS}/{norad_id}/positions?latitude={lat_f}&longitude={lon_f}&altitude=0&seconds={seconds}"
    raw = _fetch(url, timeout=15)
    try:
        positions = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return f"No pass data available for satellite {norad_id}."

    if isinstance(positions, dict) and "error" in positions:
        return f"  Error: {positions['error']}"

    if not positions or not isinstance(positions, list):
        return f"  No passes found for satellite {norad_id} over {lat_f},{lon_f} in the next {days} day(s)."

    name = positions[0].get("name", norad_id).upper()
    lines = [f"  SATELLITE {norad_id} — {name}  |  Location: {lat_f}, {lon_f}"]
    lines.append("  " + "=" * 65)
    lines.append(f"  {'Time (UTC)':<25} {'Lat':<10} {'Lon':<10} {'Alt(km)':<10}")
    lines.append("  " + "-" * 55)

    shown = 0
    for p in positions:
        if shown >= 20:
            break
        ts = p.get("timestamp", "")
        if ts:
            from datetime import datetime
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            ts_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        else:
            ts_str = "?"
        lines.append(f"  {ts_str:<25} {p.get('latitude', 0):<10.2f} {p.get('longitude', 0):<10.2f} {p.get('altitude', 0):<10.1f}")
        shown += 1

    lines.append(f"\n  Showing {shown} positions over {days} day(s)")
    return "\n".join(lines)


def _cmd_tle(norad_id: str) -> str:
    """Fetch TLE data for analysis"""
    try:
        int(norad_id)
    except ValueError:
        return f"Invalid NORAD ID: '{norad_id}'."

    raw = _fetch(f"{CELESTRAK_TLE}?CATNR={norad_id}&FORMAT=TLE", timeout=10)
    lines = raw.strip().splitlines()
    if len(lines) < 3 or "error" in raw[:50].lower():
        return f"No TLE data available for satellite {norad_id}."

    name = lines[0].strip()
    line1 = lines[1].strip()
    line2 = lines[2].strip()

    result = [f"  TLE DATA — {name} (NORAD {norad_id})"]
    result.append("  " + "=" * 55)
    result.append(f"  Line 0: {name}")
    result.append(f"  Line 1: {line1}")
    result.append(f"  Line 2: {line2}")
    result.append("")

    # Parse key TLE fields
    try:
        epoch = line1[18:32].strip()
        inc = float(line2[8:16].strip())
        raan = float(line2[17:25].strip())
        ecc = float("0." + line2[26:33].strip())
        arg_perigee = float(line2[34:42].strip())
        mean_anomaly = float(line2[43:51].strip())
        mean_motion = float(line2[52:63].strip())
        rev_num = int(line2[63:68].strip())

        result.append("  PARSED ORBITAL ELEMENTS")
        result.append(f"    Epoch:          {epoch}")
        result.append(f"    Inclination:    {inc:.4f} deg")
        result.append(f"    RAAN:           {raan:.4f} deg")
        result.append(f"    Eccentricity:   {ecc:.7f}")
        result.append(f"    Arg of Perigee: {arg_perigee:.4f} deg")
        result.append(f"    Mean Anomaly:   {mean_anomaly:.4f} deg")
        result.append(f"    Mean Motion:    {mean_motion:.8f} rev/day")
        result.append(f"    Orbit #:        {rev_num}")
        result.append(f"    Period:         {1440 / mean_motion:.2f} min")
        try:
            alt_km = (6378.137 * (mean_motion / 86400 * 86400)**(2/3)) - 6378.137  # rough
            result.append(f"    Approx Altitude: {alt_km:.0f} km")
        except Exception:
            pass
    except (IndexError, ValueError) as e:
        result.append(f"  (Could not parse all TLE fields: {e})")

    result.append("")
    result.append("  Use 'satellite analyze <id>' for a richer position-based analysis.")
    return "\n".join(result)


def _search_catalog(query: str) -> list:
    """Search the built-in popular satellite catalog"""
    q = query.strip().lower()
    matches = []
    # Search by NORAD ID
    if q.isdigit():
        for sid, sname, sdesc in POPULAR_SATS:
            if str(sid) == q or q in sname.lower() or q in sdesc.lower():
                matches.append((sid, sname, sdesc))
    # Search by name/description
    for sid, sname, sdesc in POPULAR_SATS:
        if q and (q in sname.lower() or q in sdesc.lower()):
            if (sid, sname, sdesc) not in matches:
                matches.append((sid, sname, sdesc))
    return matches[:30]


def _cmd_search(query: str) -> str:
    """Search satellite catalog by name"""
    q = query.strip().lower()
    if not q:
        return "Usage: satellite search <name> (e.g. 'satellite search hubble' or 'satellite search noaa')"

    matches = _search_catalog(q)
    if not matches:
        return f"  No satellites found matching '{query}'."

    lines = [f"  SATELLITE SEARCH: '{query}'  ({len(matches)} found)"]
    lines.append("  " + "=" * 65)
    lines.append(f"  {'NORAD':<8} {'Name':<35} {'Description':<30}")
    lines.append("  " + "-" * 75)
    for sid, sname, sdesc in matches:
        name = sname[:33]
        desc = sdesc[:28] if sdesc else ""
        lines.append(f"  {sid:<8} {name:<35} {desc:<30}")
    return "\n".join(lines)


def _cmd_list(group: str = "active") -> str:
    """List satellites in a group"""
    group_lower = group.lower()
    group_name = group_lower.upper()
    group_desc = SAT_GROUPS.get(group_lower, "")

    if group_lower == "active":
        # Show all popular satellites
        sats = POPULAR_SATS
        lines = [f"  SATELLITE CATALOG  ({len(sats)} popular satellites)"]
        lines.append("  " + "=" * 65)
        lines.append(f"  {'NORAD':<8} {'Name':<35} {'Description':<30}")
        lines.append("  " + "-" * 75)
        for sid, sname, sdesc in sats:
            lines.append(f"  {sid:<8} {sname[:33]:<35} {(sdesc or '')[:28]:<30}")
        return "\n".join(lines)

    ids = SAT_GROUP_IDS.get(group_lower, [])
    if not ids:
        available = ", ".join(sorted(SAT_GROUPS.keys()))
        return (
            f"  Unknown group '{group}'. Available groups: {available}\n"
            f"  Or use 'satellite search <name>' instead."
        )

    sats = [s for s in POPULAR_SATS if s[0] in ids]
    lines = [f"  SATELLITE GROUP: {group_name}  {group_desc}  ({len(sats)} satellites)"]
    lines.append("  " + "=" * 65)
    lines.append(f"  {'NORAD':<8} {'Name':<35} {'Description':<30}")
    lines.append("  " + "-" * 75)
    for sid, sname, sdesc in sats:
        lines.append(f"  {sid:<8} {sname[:33]:<35} {(sdesc or '')[:28]:<30}")
    return "\n".join(lines)


def _cmd_analyze(norad_id: str) -> str:
    """Full satellite analysis combining position + TLE"""
    try:
        int(norad_id)
    except ValueError:
        return f"Invalid NORAD ID: '{norad_id}'."

    pos = _fetch_json(f"{WHERETHEISS}/{norad_id}", timeout=10)
    if "error" in pos:
        return f"  Satellite {norad_id} not found."

    name = pos.get("name", "?").upper()
    lines = [f"  SATELLITE ANALYSIS — {name} (NORAD {norad_id})"]
    lines.append("  " + "=" * 55)
    lines.append("")
    lines.append("  CURRENT STATE")
    lines.append(f"    Latitude:     {pos.get('latitude', 0):.4f} deg")
    lines.append(f"    Longitude:    {pos.get('longitude', 0):.4f} deg")
    lines.append(f"    Altitude:     {pos.get('altitude', 0):.1f} km")
    lines.append(f"    Velocity:     {pos.get('velocity', 0):.1f} km/h")
    lines.append(f"    Visibility:   {pos.get('visibility', '?')}")
    lines.append("")
    lines.append("  ORBIT CHARACTERISTICS")
    perigee = pos.get('perigee', 0)
    apogee = pos.get('apogee', 0)
    inclination = pos.get('inclination', 0)
    period = pos.get('period', 0)
    footprint = pos.get('footprint', 0)

    if perigee and apogee:
        lines.append(f"    Perigee:      {perigee:.1f} km")
        lines.append(f"    Apogee:       {apogee:.1f} km")
    if inclination:
        lines.append(f"    Inclination:  {inclination:.2f} deg")
    if period:
        lines.append(f"    Period:       {period:.2f} min")
    if footprint:
        lines.append(f"    Footprint:    {footprint:.0f} km")
    lines.append("")

    # Derive additional info from available data
    try:
        alt = pos.get('altitude', 400)
        vel = pos.get('velocity', 27600)
        p = period if period else (2 * 3.14159 * (6378 + alt) / (vel / 3600))
        lines.append("  DERIVED DATA")
        if p:
            lines.append(f"    Orbits per day:  {1440 / p:.2f}")
        lines.append(f"    Speed:           {vel / 3600:.2f} km/s")
        if alt:
            lines.append(f"    Ground track speed: {vel * (6378 / (6378 + alt)) / 3600:.1f} km/s")
            lines.append(f"    Round-trip latency: {2 * alt / 299792 * 1000:.1f} ms (at nadir)")
    except Exception:
        pass

    lines.append("")
    lines.append("  MAP")
    map_url = f"https://www.google.com/maps?q={pos.get('latitude', 0)},{pos.get('longitude', 0)}&z=3"
    lines.append(f"    {map_url}")

    # Add TLE if available
    raw = _fetch(f"{CELESTRAK_TLE}?CATNR={norad_id}&FORMAT=TLE", timeout=10)
    tle_lines = raw.strip().splitlines()
    if len(tle_lines) >= 3 and "error" not in raw[:50].lower():
        lines.append("")
        lines.append("  TLE DATA (for further analysis)")
        lines.append(f"    {tle_lines[0].strip()}")
        lines.append(f"    {tle_lines[1].strip()}")
        lines.append(f"    {tle_lines[2].strip()}")

    return "\n".join(lines)


def satellite_main(args: str) -> str:
    """Main entry point: satellite <subcommand> [args]"""
    if not args or args.strip().lower() in ("help", "-h", "--help", "?"):
        return _help()

    parts = args.split(maxsplit=5)
    sub = parts[0].lower().strip() if parts else "help"

    if sub == "iss":
        return _cmd_iss()

    if sub == "position":
        norad = parts[1] if len(parts) > 1 else ""
        if not norad:
            return "Usage: satellite position <norad_id> (e.g. 'satellite position 25544')"
        return _cmd_position(norad)

    if sub == "passes":
        norad = parts[1] if len(parts) > 1 else ""
        lat = parts[2] if len(parts) > 2 else ""
        lon = parts[3] if len(parts) > 3 else ""
        days = parts[4] if len(parts) > 4 else "2"
        if not norad or not lat or not lon:
            return "Usage: satellite passes <norad_id> <latitude> <longitude> [days]"
        return _cmd_passes(norad, lat, lon, days)

    if sub == "tle":
        norad = parts[1] if len(parts) > 1 else ""
        if not norad:
            return "Usage: satellite tle <norad_id> (e.g. 'satellite tle 25544')"
        return _cmd_tle(norad)

    if sub == "search":
        query = args[len("search"):].strip()
        if not query:
            return "Usage: satellite search <name> (e.g. 'satellite search hubble')"
        return _cmd_search(query)

    if sub == "list":
        group = parts[1].strip() if len(parts) > 1 else "active"
        return _cmd_list(group)

    if sub == "analyze":
        norad = parts[1] if len(parts) > 1 else ""
        if not norad:
            return "Usage: satellite analyze <norad_id> (e.g. 'satellite analyze 25544')"
        return _cmd_analyze(norad)

    return _help()
