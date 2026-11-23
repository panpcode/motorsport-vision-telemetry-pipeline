"""Loads laps from game telemetry (telemetry.csv from scripts/decode_forza.py)."""
import csv

import numpy as np

COLOURS = ["#EB0A1E", "#1F5FAD"]  # reference lap, compared lap


def read_csv(path):
    rows = list(csv.DictReader(open(path)))
    num = lambda v: float(v) if v != "" else np.nan
    return {k: np.array([num(r[k]) for r in rows]) for k in rows[0]}


def laps(path):
    """Complete laps: {lap number shown in game: samples}. The first lap (out lap / standing start) is skipped."""
    c = read_csv(path)
    out = {}
    for n in np.unique(c["lap"]).astype(int):
        i = np.flatnonzero(c["lap"] == n)
        nxt = np.flatnonzero(c["lap"] == n + 1)
        if n == 0 or not len(nxt):  # out lap, or lap not finished
            continue
        t = c["lap_t"][i]
        if np.any(np.diff(t) < -0.05):
            print(f"lap {n + 1} skipped: lap timer went back (rewind?)")
            continue
        out[n + 1] = {
            "lap_number": n + 1,
            "lap_time": float(c["last_lap_s"][nxt[0]]),  # official, from the game
            "game_distance_m": float(c["distance_m"][i[-1]] - c["distance_m"][i[0]]),
            "sectors": None,
            "t": t,
            "speed": c["speed_kmh"][i],
            "throttle": c["throttle"][i],
            "brake": (c["brake"][i] > 0.1).astype(float),
            "gear": c["gear"][i],
            "x": c["x"][i],
            "y": c["y"][i],
        }
    return out


def load_pair(path, lap_a=None, lap_b=None):
    """Two laps to compare. Default: fastest vs second fastest."""
    all_laps = laps(path)
    if len(all_laps) < 2:
        raise SystemExit(f"need 2 complete laps, found {sorted(all_laps)} (first lap is skipped)")
    by_time = sorted(all_laps, key=lambda n: all_laps[n]["lap_time"])
    a = lap_a or by_time[0]
    b = lap_b or next(n for n in by_time if n != a)
    for n in (a, b):
        if n not in all_laps:
            raise SystemExit(f"lap {n} not available, have {sorted(all_laps)}")
    pair = []
    for n, colour in zip((a, b), COLOURS):
        lap = dict(all_laps[n], driver=f"L{n}", team_colour=colour)
        pair.append(lap)
    return pair, all_laps
