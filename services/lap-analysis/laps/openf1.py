"""Loads one lap of real F1 telemetry from OpenF1 (free, no account)."""
import hashlib
import json
import os
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timedelta

import numpy as np

API = "https://api.openf1.org/v1/"
CACHE = os.path.join(os.path.dirname(__file__), "../../../sample-data/openf1-cache")


def get(endpoint, *filters):
    # filters like "year=2025" or "date>=...". Cached on disk, historical data never changes
    qs = "&".join(f[:i] + urllib.parse.quote(f[i:], safe="=<>") for f in filters
                  for i in [next(j for j, ch in enumerate(f) if ch in "=<>")])
    url = f"{API}{endpoint}?{qs}"
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + ".json")
    if os.path.exists(path):
        return json.load(open(path))
    req = urllib.request.Request(url, headers={"User-Agent": "lap-analysis"})
    for attempt in range(6):
        try:
            data = json.load(urllib.request.urlopen(req, timeout=60))
            break
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(2 ** attempt)  # rate limited, back off
    json.dump(data, open(path, "w"))
    return data


def parse_date(s):
    return datetime.fromisoformat(s)


def find_session(year, location, session_name):
    loc = location.lower()
    for s in get("sessions", f"year={year}", f"session_name={session_name}"):
        if loc in s["location"].lower() or loc in s["circuit_short_name"].lower() or loc in s["country_name"].lower():
            return s
    raise SystemExit(f"no {session_name} session for '{location}' in {year}")


def load_lap(session_key, driver, lap_number=None):
    drivers = {d["name_acronym"]: d for d in get("drivers", f"session_key={session_key}")}
    if driver not in drivers:
        raise SystemExit(f"driver {driver} not in session, have: {', '.join(sorted(drivers))}")
    num = drivers[driver]["driver_number"]

    laps = [l for l in get("laps", f"session_key={session_key}", f"driver_number={num}") if l["lap_duration"]]
    if lap_number:
        lap = next(l for l in laps if l["lap_number"] == lap_number)
    else:
        lap = min(laps, key=lambda l: l["lap_duration"])  # fastest lap

    start = parse_date(lap["date_start"])
    end = start + timedelta(seconds=lap["lap_duration"])
    window = (f"session_key={session_key}", f"driver_number={num}",
              f"date>={start.isoformat()}", f"date<{end.isoformat()}")
    car = get("car_data", *window)
    loc = get("location", *window)

    t = np.array([(parse_date(c["date"]) - start).total_seconds() for c in car])
    t_loc = np.array([(parse_date(p["date"]) - start).total_seconds() for p in loc])
    col = lambda k: np.array([c[k] for c in car], float)
    return {
        "driver": driver,
        "team_colour": "#" + (drivers[driver].get("team_colour") or "888888"),
        "lap_number": lap["lap_number"],
        "lap_time": lap["lap_duration"],
        "sectors": [lap["duration_sector_1"], lap["duration_sector_2"], lap["duration_sector_3"]],
        "t": t,
        "speed": col("speed"),
        "throttle": col("throttle"),
        "brake": (col("brake") > 0).astype(float),
        "gear": col("n_gear"),
        # Position comes at a different rate, put it on the car_data times
        "x": np.interp(t, t_loc, [p["x"] for p in loc]),
        "y": np.interp(t, t_loc, [p["y"] for p in loc]),
    }
