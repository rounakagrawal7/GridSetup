"""
GRID Game Module — playable game environments for GRID.

Two play modes:
  1. `game world`  — a self-contained open-world sandbox (GRADDR). A
     procedurally-generated 2D map with terrain, items, monsters and a quest
     (recover the Signal Cache). GRID plays it turn-by-turn with its own tools,
     no network needed. State persists under ./game_state/.
  2. `game minigrid` — bridge to Gymnasium MiniGrid benchmark environments
     (if `gymnasium` + `minigrid` are installed). Step-by-step control loop
     so GRID can practice navigation/reward learning on standard RL tasks.

Sub-commands (prefix with the `game` tool or use /game):
  help                     — reference
  world                    — show the open-world control prompt
  world help|map|look|status|inv|take|attack|move <dir>|use <item>|rest|new
  minigrid status          — is the MiniGrid bridge installed & ready?
  minigrid envlist         — list available MiniGrid envs
  minigrid start <env>     — reset an environment for play
  minigrid step [action]   — apply one action (0..6, default: next best guess)
  minigrid obs             — show current observation as text
  minigrid reset           — reset the active environment
"""

import json
import os
import random

GAME_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "game_state")
WORLD_FILE = os.path.join(GAME_DIR, "world.json")
MG_STATE = {"env": None, "name": None, "actions": [], "t": 0}


# ---------------------------------------------------------------------------
# Open world: GRADDR (Glacial Ridge Archaeological & Data-Dive Reach)
# ---------------------------------------------------------------------------
TERRAIN_PASS = {"grass": True, "forest": True, "sand": True, "ruin": True, "cache": True}
TERRAIN = {"grass": ".", "forest": "T", "mountain": "^", "water": "~", "sand": "s", "ruin": "%", "cache": "*"}
TERRAIN_COST = {"grass": 1, "forest": 2, "sand": 2, "ruin": 3, "cache": 1}

ITEMS = [
    {"id": "water_jug", "name": "Water Jug", "desc": "Clear drinking water. Restores energy.", "biome": ["water", "grass"]},
    {"id": "field_ration", "name": "Field Ration", "desc": "Dried food. Restores energy.", "biome": ["forest", "ruin", "sand"]},
    {"id": "iron_key", "name": "Iron Key", "desc": "Old key, still fits old locks.", "biome": ["ruin", "mountain"]},
    {"id": "compass", "name": "Compass", "desc": "Points toward the cache.", "biome": ["ruin", "forest"]},
]

MOBS = [
    {"kind": "pack_dog", "name": "Ferrock Pack Dog", "hp": 6, "atk": (1, 2), "drop": "field_ration"},
    {"kind": "scavenger", "name": "Scavenger", "hp": 8, "atk": (1, 3), "drop": "compass"},
    {"kind": "wanderer", "name": "Cache Wanderer", "hp": 5, "atk": (1, 2), "drop": "water_jug"},
]


# ---------------------------------------------------------------------------
# World helpers
# ---------------------------------------------------------------------------
def _new_world(w=12, h=9):
    for attempt in range(30):
        g = _try_gen(w, h)
        if _cache_reachable(g):
            _save_world(g)
            return g
    _save_world(g)
    return g


def _cache_reachable(w):
    start = (w["player"]["x"], w["player"]["y"])
    target = w["cache_pos"]
    frontier = [start]
    visited = {start}
    while frontier:
        x, y = frontier.pop(0)
        if (x, y) == target:
            return True
        for dx, dy in ((0, -1), (0, 1), (1, 0), (-1, 0)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w["w"] and 0 <= ny < w["h"]):
                continue
            if (nx, ny) in visited:
                continue
            t = w["grid"].get((nx, ny), "grass")
            if t not in TERRAIN_PASS:
                continue
            visited.add((nx, ny))
            frontier.append((nx, ny))
    return False


def _try_gen(w=12, h=9):
    rnd = random.Random()
    grid = {}
    for y in range(h):
        for x in range(w):
            r = rnd.random()
            if r < 0.08:
                t = "mountain"
            elif r < 0.22:
                t = "water"
            elif r < 0.40:
                t = "forest"
            elif r < 0.50:
                t = "sand"
            elif r < 0.55:
                t = "ruin"
            else:
                t = "grass"
            grid[(x, y)] = t
    px, py = w // 2, h // 2
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            grid[(px + dx, py + dy)] = "grass"
    cx, cy = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
    while (abs(cx - px) + abs(cy - py)) < 9:
        cx, cy = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            tx, ty = cx + dx, cy + dy
            if 0 <= tx < w and 0 <= ty < h:
                grid[(tx, ty)] = "grass"
    grid[(cx, cy)] = "cache"
    mobs = []
    seen_pts = {(px, py), (cx, cy)}
    for _ in range(rnd.randint(2, 4)):
        mx, my = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
        while (mx, my) in seen_pts or grid[(mx, my)] in ("water", "mountain"):
            mx, my = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
        seen_pts.add((mx, my))
        m = random.choice(MOBS).copy()
        m["x"], m["y"] = mx, my
        mobs.append(m)
    items = []
    used = set(seen_pts)
    for _ in range(rnd.randint(4, 7)):
        ix, iy = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
        attempts = 0
        while ((ix, iy) in used or (ix, iy) == (px, py)) and attempts < 40:
            ix, iy = rnd.randint(0, w - 1), rnd.randint(0, h - 1)
            attempts += 1
        used.add((ix, iy))
        biome = grid[(ix, iy)]
        cand = [i for i in ITEMS if biome in i["biome"]]
        drop = random.choice(cand) if cand else random.choice(ITEMS)
        items.append({"id": drop["id"], "name": drop["name"], "desc": drop["desc"], "x": ix, "y": iy})
    world = {
        "w": w, "h": h, "grid": grid,
        "player": {"x": px, "y": py, "hp": 20},
        "mobs": mobs, "items": items,
        "inventory": [], "cache_pos": (cx, cy),
        "steps": 0, "energy": 100, "won": False,
        "seen": {(px, py)},
    }
    return world


def _load_world():
    if not os.path.isfile(WORLD_FILE):
        return None
    with open(WORLD_FILE) as f:
        d = json.load(f)
    g = d["grid"]
    grid = {(int(k.split(",")[0]), int(k.split(",")[1])): v for k, v in g.items()}
    p = d["player"]
    return {
        "w": d["w"], "h": d["h"], "grid": grid,
        "player": {"x": p["x"], "y": p["y"], "hp": p["hp"]},
        "mobs": d["mobs"], "items": d["items"],
        "inventory": d["inventory"],
        "cache_pos": tuple(d["cache_pos"]), "steps": d["steps"],
        "energy": d["energy"], "won": d.get("won", False),
        "seen": {tuple(s) for s in d.get("seen", [])},
    }


def _save_world(w):
    if not os.path.isdir(GAME_DIR):
        os.makedirs(GAME_DIR, exist_ok=True)
    ww = {
        "w": w["w"], "h": w["h"],
        "grid": {f"{k[0]},{k[1]}": v for k, v in w["grid"].items()},
        "player": w["player"], "mobs": w["mobs"], "items": w["items"],
        "inventory": w["inventory"],
        "cache_pos": list(w["cache_pos"]), "steps": w["steps"],
        "energy": w["energy"], "won": w["won"],
        "seen": sorted(f"{a[0]},{a[1]}" for a in w["seen"]),
    }
    with open(WORLD_FILE, "w") as f:
        json.dump(ww, f, indent=1)


def _tile_char(w, x, y):
    t = w["grid"].get((x, y), "grass")
    if (x, y) == w["cache_pos"] and t == "cache":
        return "C"
    if any(m["x"] == x and m["y"] == y and m.get("hp", 0) > 0 for m in w["mobs"]):
        return "&"
    if any(i.get("x") == x and i.get("y") == y for i in w["items"]):
        return "*"
    if (x, y) == (w["player"]["x"], w["player"]["y"]):
        return "@"
    if (x, y) not in w["seen"]:
        return "~"
    return TERRAIN[t]


def _render(w):
    lines = ["+" + "-" * w["w"] + "+"]
    for y in range(w["h"]):
        lines.append("|" + "".join(_tile_char(w, x, y) for x in range(w["w"])) + "|")
    lines.append("+" + "-" * w["w"] + "+")
    lines.append("Legend: @=you C=cache &=monster *=item ~=unexplored ."
                 "=grass T=forest s=sand %=ruin ^=mountain ~(blocked)=water")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# World actions
# ---------------------------------------------------------------------------
def _move(w, dx, dy):
    p = w["player"]
    nx, ny = p["x"] + dx, p["y"] + dy
    if not (0 <= nx < w["w"] and 0 <= ny < w["h"]):
        return "The world ends there. Pick another direction."
    t = w["grid"].get((nx, ny), "grass")
    if t not in TERRAIN_PASS:
        return "A wall of %s blocks the way." % t
    p["x"], p["y"] = nx, ny
    w["seen"].add((nx, ny))
    w["energy"] = max(0, w["energy"] - TERRAIN_COST[t])
    w["steps"] += 1
    msgs = ["Moved to (%d,%d) on %s. Energy %d." % (nx, ny, t, w["energy"])]
    if t == "cache":
        w["won"] = True
        msgs.append("*** CACHE FOUND! You recovered the Signal Amp. ***")
    mob = next((m for m in w["mobs"] if m["x"] == nx and m["y"] == ny and m.get("hp", 0) > 0), None)
    if mob:
        d = mob["hp"] - mob["atk"][0] * random.randint(*mob["atk"])
        msgs.append("A %s ambushes you but you drive it back." % mob["name"])
    return "\n".join(msgs)


# ---------------------------------------------------------------------------
# game world front-end
# ---------------------------------------------------------------------------
def game_world(input_str):
    parts = input_str.split()
    cmd = parts[0] if parts else "help"
    w = _load_world()
    if w is None:
        w = _new_world() if cmd != "new" else _new_world()

    if cmd in ("help", "-h", "--help"):
        return (
            "GRADD — GRID exploration sandbox. Recover the Signal Cache.\n\n"
            "  map      render the world (unseen tiles are ~)\n"
            "  look     inspect where you and your surroundings are\n"
            "  scan <x> <y>   view an area at coords\n"
            "  move n|s|e|w / north|south|east|west\n"
            "  take     pick up items at your tile\n"
            "  inventory  list carried items\n"
"  hunt     sees range of nearby monsters/items (metadata)\n"
        "  attack   fight the monster at your tile\n"
        "  rest     regain energy (spends a turn)\n"
        "  new      regenerate the world\n\n"
        "Tool usage: game world map, game world look, game world move north, ...\n"
        "The Cache (C) is the goal tile — step onto it to win. Explore by moving."
        )
    if cmd == "new":
        w = _new_world()
        return "Fresh world generated.\n" + _render(w)
    if cmd in ("map", "grid"):
        return _render(w)
    if cmd in ("status", "stats"):
        return (
            "Energy %d/100  HP %d/20  Steps %d  Won=%s\n"
            "Inventory: %s" % (
                w["energy"], w["player"]["hp"], w["steps"], w["won"],
                ", ".join(i["id"] for i in w["inventory"]) or "empty"))
    if cmd in ("inv", "inventory", "i"):
        if not w["inventory"]:
            return "Inventory empty."
        return "\n".join("* %s (%s)" % (i["name"], i["desc"]) for i in w["inventory"])

    p = w["player"]
    if cmd in ("look", "l"):
        return _describe_look(w, p["x"], p["y"])
    if cmd in ("move", "m"):
        if len(parts) < 2:
            return "move <north|south|east|west>"
        dir_map = {"n": (0, -1), "s": (0, 1), "e": (1, 0), "w": (-1, 0),
                   "north": (0, -1), "south": (0, 1), "east": (1, 0), "west": (-1, 0)}
        if parts[1] not in dir_map:
            return "unknown direction: %s" % parts[1]
        _repl = _move(w, dir_map[parts[1]][0], dir_map[parts[1]][1])
        _save_world(w)
        return _repl
    if cmd in ("take", "t"):
        at = [i for i in w["items"] if i.get("x") == p["x"] and i.get("y") == p["y"]]
        if not at:
            return "Nothing to take here."
        for i in at:
            w["inventory"].append(i)
            w["items"].remove(i)
        _save_world(w)
        return "Took: %s" % (", ".join(i["name"] for i in at))
    if cmd in ("attack", "hit"):
        mob = next((m for m in w["mobs"] if m["x"] == p["x"] and m["y"] == p["y"] and m.get("hp", 0) > 0), None)
        if not mob:
            return "Nothing to attack here."
        dmg = random.randint(*mob["atk"])
        mob["hp"] = max(0, mob["hp"] - dmg)
        lines = ["You strike the %s for %d hp." % (mob["name"], dmg)]
        if mob["hp"] == 0:
            w["mobs"].remove(mob)
            w["inventory"].append({"id": mob["drop"], "name": mob["drop"], "desc": "dropped by %s" % mob["name"]})
            lines.append("It falls! You pick up: %s" % mob["drop"])
        w["steps"] += 1
        _save_world(w)
        return "\n".join(lines)
    if cmd in ("use",):
        if len(parts) < 2:
            return "use <item id>"
        for i in w["inventory"]:
            if i["id"] == parts[1] and i["id"] in ("water_jug", "field_ration"):
                w["inventory"].remove(i)
                w["energy"] = min(100, w["energy"] + 30)
                _save_world(w)
                return "Used %s. Energy %d." % (i["name"], w["energy"])
        return "No usable item '%s' (water_jug or field_ration)." % parts[1]
    if cmd == "rest":
        w["steps"] += 1
        w["energy"] = min(100, w["energy"] + 15)
        _save_world(w)
        return "You rest. Energy %d." % w["energy"]
    if cmd in ("hunt", "detect"):
        lines = ["Nearby monsters:"]
        for m in w["mobs"]:
            if m.get("hp", 0) <= 0:
                continue
            d = abs(m["x"] - p["x"]) + abs(m["y"] - p["y"])
            ns = "N" if m["y"] < p["y"] else ("S" if m["y"] > p["y"] else "-")
            ew = "E" if m["x"] > p["x"] else ("W" if m["x"] < p["x"] else "-")
            lines.append("  %s at (%d,%d)  dist %d  bearing %s%s" % (m["name"], m["x"], m["y"], d, ns, ew))
        return "\n".join(lines) or "No monsters nearby."
    return "Unknown world command '%s'. Try 'game world help'." % cmd


def _describe_loc(w, x, y):
    if not (0 <= x < w["w"] and 0 <= y < w["h"]):
        return "out of bounds"
    t = w["grid"].get((x, y), "grass")
    s = "the %s" % t
    if (x, y) == w["cache_pos"] and t == "cache":
        s = "a low-glowing Cache tile"
    for i in w["items"]:
        if i.get("x") == x and i.get("y") == y:
            s += "; %s" % i["name"]
    for m in w["mobs"]:
        if m["x"] == x and m["y"] == y and m.get("hp", 0) > 0:
            s += "; %s (HP %d)" % (m["name"], m["hp"])
    return s


def _describe_loc(w, x, y):
    if not (0 <= x < w["w"] and 0 <= y < w["h"]):
        return "out of bounds"
    t = w["grid"].get((x, y), "grass")
    s = "the %s" % t
    if (x, y) == w["cache_pos"] and t == "cache":
        s = "a low-glowing Cache tile"
    for i in w["items"]:
        if i.get("x") == x and i.get("y") == y:
            s += "; %s" % i["name"]
    for m in w["mobs"]:
        if m["x"] == x and m["y"] == y and m.get("hp", 0) > 0:
            s += "; %s (HP %d)" % (m["name"], m["hp"])
    return s


def _describe_look(w, cx, cy):
    pool = {
        "n": _describe_loc(w, cx, cy - 1),
        "s": _describe_loc(w, cx, cy + 1),
        "e": _describe_loc(w, cx + 1, cy),
        "w": _describe_loc(w, cx - 1, cy),
    }
    you = _describe_loc(w, cx, cy)
    return "You are on %s\nN: %s\nS: %s\nE: %s\nW: %s" % (you, pool["n"], pool["s"], pool["e"], pool["w"])


# ---------------------------------------------------------------------------
# MiniGrid bridge
# ---------------------------------------------------------------------------
def _mg_available():
    try:
        import gymnasium  # noqa
        import minigrid  # noqa
        return True
    except Exception:
        return False


def minigrid_status():
    if not _mg_available():
        return "MiniGrid bridge NOT installed.\nRun: pip install gymnasium minigrid\nThen 'game minigrid envlist'."
    return "MiniGrid bridge ready (gymnasium + minigrid found)."


def minigrid_envlist():
    if not _mg_available():
        return minigrid_status()
    import minigrid.minigrid_envs  # noqa: F401  (registers all envs)
    regs = []
    def visit(mod, prefix):
        for k, v in list(getattr(mod, "__dict__", {}).items()):
            if isinstance(v, type) and hasattr(v, "environment") and v not in regs:
                regs.append(v)
    try:
        from minigrid import envs
        visit(envs, "")
    except Exception:
        pass
    names = []
    for cls in regs:
        for env_id in getattr(cls, "environment", []):
            names.append(env_id)
    names = sorted(set(names))
    if not names:
        # fallback: gym registry keys
        try:
            from gymnasium import envs as _ge
            names = sorted(x for x in _ge.registry if "MiniGrid" in x)
        except Exception:
            pass
    return "Available MiniGrid environments (%d):\n%s" % (len(names), "\n".join("  " + n for n in names))


def minigrid_start(env_name):
    if not _mg_available():
        return minigrid_status()
    try:
        import gymnasium
        if not env_name.endswith("v0"):
            env_name += "-v0"
        env = gymnasium.make(env_name)
        obs, info = env.reset()
        MG_STATE["env"] = env
        MG_STATE["name"] = env_name
        MG_STATE["t"] = 0
        return "Started %s. Step with 'game minigrid step <action>'.\n%s" % (env_name, _obs_text(obs))
    except Exception as e:
        return "Failed to start %s: %s\nCheck 'game minigrid envlist' for valid ids." % (env_name, e)


def _obs_text(obs):
    if obs is None:
        return "(no observation)"
    if isinstance(obs, dict):
        img = obs.get("image")
        if img is not None:
            shape = getattr(img, "shape", None) or img.shape
            view = img[:, :, 0] if img.ndim >= 3 else img
        else:
            view = None
        parts = []
        for k in ("direction", "mission", "goal"):
            if k in obs:
                parts.append("%s=%s" % (k, obs[k]))
        extra = " ".join(parts)
        return "observation keys: %s  %s" % (", ".join(str(k) for k in obs.keys()), extra)
    return "observation: %s" % (obs,)


MINIGRID_ACTIONS = ["left", "forward", "right", "pickup", "drop", "toggle", "done"]


def minigrid_step(action=None):
    env = MG_STATE.get("env")
    if env is None:
        return "No active MiniGrid env. Run 'game minigrid start <env>' first."
    import gymnasium
    if action is None:
        action = env.action_space.sample()
    else:
        try:
            action = int(action)
        except (TypeError, ValueError):
            hits = [i for i, a in enumerate(MINIGRID_ACTIONS) if a == action]
            action = hits[0] if hits else 0
    obs, rew, term, trunc, info = env.step(action)
    MG_STATE["t"] += 1
    msg = "Step %d, action=%s reward=%.2f done=%s\n%s" % (
        MG_STATE["t"], action, float(rew), term or trunc, _obs_text(obs))
    if term or trunc:
        msg += "\n== episode over =="
    return msg


def game_minigrid(input_str):
    parts = input_str.split()
    cmd = parts[0] if parts else "status"
    if cmd in ("status",):
        return minigrid_status()
    if cmd in ("envlist", "list"):
        return minigrid_envlist()
    if cmd == "start":
        if len(parts) < 2:
            return "usage: game minigrid start <env> (e.g. MiniGrid-Empty-8x8 or -v0)"
        return minigrid_start(parts[1])
    if cmd in ("step", "act"):
        return minigrid_step(parts[1] if len(parts) > 1 else None)
    if cmd in ("obs", "observe"):
        env = MG_STATE.get("env")
        if env is None:
            return "No active env."
        return _obs_text({"image": None, "direction": "?", "mission": "?"})
    if cmd == "reset":
        rem = MG_STATE.get("name")
        if not rem:
            return "No active env to reset."
        env = MG_STATE["env"]
        try:
            obs, info = env.reset()
            MG_STATE["t"] = 0
            return "Reset %s.\n%s" % (rem, _obs_text(obs))
        except Exception as e:
            return "reset failed: %s" % e
    if cmd in ("help", "-h"):
        return (
            "MinGrid bridge — play standard navigation environments.\n"
            "  status       installed? ready?\n"
            "  envlist      environment ids\n"
            "  start <env>  begin an episode (e.g. MiniGrid-Empty-8x8-v0)\n"
            "  step <act>   apply action (0-6: left/forward/right/pickup/drop/toggle/done)\n"
            "  obs          current observation\n"
            "  reset        restart episode\n")
    return "unknown minigrid cmd. Try 'game minigrid help'."


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------
def game_main(input_str=""):
    parts = input_str.strip().split()
    top = parts[0] if parts else "help"
    rest = " ".join(parts[1:]) if len(parts) > 1 else ""
    if top in ("world", "play", "adventure"):
        return game_world(rest)
    if top in ("minigrid", "mg", "rl"):
        return game_minigrid(rest)
    if top in ("help", "-h", "--help", ""):
        return (
            "GRID Game Module\n\n"
            "  game world help              open-world sandbox (no deps)\n"
            "  game minigrid status         MiniGrid RL bridge\n"
            "  game help                    this text\n"
            "\n"
            "0 deps required for the world. For RL games run: pip install gymnasium minigrid")
    return "Unknown segment '%s'. Try 'game help'." % top