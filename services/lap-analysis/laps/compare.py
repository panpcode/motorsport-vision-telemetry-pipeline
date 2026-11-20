"""Compares two laps by distance: time delta, corners, where time was lost and why.

Works with any source that gives per-sample t, speed, throttle, brake, gear, x, y
(OpenF1 now, game telemetry later).
"""
import numpy as np
from scipy.signal import find_peaks

STEP_M = 5          # common distance grid
BRAKE_DIFF_M = 15   # smaller differences are below the sample resolution (~4 Hz)
THROTTLE_DIFF_M = 15
SPEED_DIFF_KMH = 3
PROMINENCE_KMH = 12  # speed dip needed to count as a corner
CHICANE_KMH = 30     # less speed gained than this between two corners = one corner


def add_distance(lap):
    # Distance = integral of speed. Pad so the lap covers t = 0 .. lap_time
    t = np.r_[0.0, lap["t"], lap["lap_time"]]
    pad = lambda a: np.r_[a[0], a, a[-1]]
    v = pad(lap["speed"]) / 3.6
    d = np.r_[0.0, np.cumsum(np.diff(t) * (v[1:] + v[:-1]) / 2)]
    out = {k: pad(lap[k]) for k in ("speed", "throttle", "brake", "gear", "x", "y")}
    out.update(t=t, d=d)
    return out


def to_grid(lap, length):
    # Each lap's distance is scaled to the same track length, then resampled every STEP_M
    raw = add_distance(lap)
    d = raw["d"] / raw["d"][-1] * length
    grid = np.r_[np.arange(0, length, STEP_M), length]
    g = {k: np.interp(grid, d, raw[k]) for k in ("t", "speed", "throttle", "x", "y")}
    g["brake"] = (np.interp(grid, d, raw["brake"]) >= 0.5).astype(float)
    g["gear"] = np.round(np.interp(grid, d, raw["gear"]))
    g["d"] = grid
    return g


def smooth(a, n=5):
    return np.convolve(a, np.ones(n) / n, mode="same")


def find_corners(v):
    # Corners = clear speed minima. Two minima with no real straight between them
    # (chicane) count as one corner, keeping the slower one
    apexes = list(find_peaks(-v, prominence=PROMINENCE_KMH, distance=150 // STEP_M)[0])
    i = 0
    while i < len(apexes) - 1:
        p, q = apexes[i], apexes[i + 1]
        if v[p:q].max() < max(v[p], v[q]) + CHICANE_KMH:
            apexes[i:i + 2] = [p if v[p] < v[q] else q]
        else:
            i += 1
    return apexes


def first(mask, lo, hi):
    idx = np.flatnonzero(mask[lo:hi])
    return lo + idx[0] if len(idx) else None


def corner_stats(g, lo, apex, hi):
    w0, w1 = max(lo, apex - 150 // STEP_M), min(hi, apex + 150 // STEP_M)
    i_min = w0 + int(np.argmin(g["speed"][w0:w1]))
    brake = first(g["brake"] > 0, lo, apex + 1)
    full = first(g["throttle"] >= 98, i_min, hi)
    return {
        "brake_m": float(g["d"][brake]) if brake is not None else None,
        "min_speed": float(g["speed"][i_min]),
        "full_throttle_m": float(g["d"][full]) if full is not None else None,
        "top_speed": float(g["speed"][apex:hi].max()),
    }


def reasons(fast, slow):
    # What the faster driver did differently: (text, helped?) pairs
    out = []
    if fast["brake_m"] and slow["brake_m"]:
        diff = fast["brake_m"] - slow["brake_m"]
        if abs(diff) >= BRAKE_DIFF_M:
            out.append((f"brakes {abs(diff):.0f} m {'later' if diff > 0 else 'earlier'}", diff > 0))
    elif slow["brake_m"] and not fast["brake_m"]:
        out.append(("no braking, lift only", True))
    diff = fast["min_speed"] - slow["min_speed"]
    if abs(diff) >= SPEED_DIFF_KMH:
        out.append((f"{diff:+.0f} km/h at the slowest point", diff > 0))
    if fast["full_throttle_m"] and slow["full_throttle_m"]:
        diff = slow["full_throttle_m"] - fast["full_throttle_m"]
        if abs(diff) >= THROTTLE_DIFF_M:
            out.append((f"full throttle {abs(diff):.0f} m {'earlier' if diff > 0 else 'later'}", diff > 0))
    diff = fast["top_speed"] - slow["top_speed"]
    if abs(diff) >= SPEED_DIFF_KMH:
        out.append((f"{diff:+.0f} km/h top speed after", diff > 0))
    return out


def explain(rs):
    helped = [t for t, ok in rs if ok]
    despite = [t for t, ok in rs if not ok]
    text = ", ".join(helped) or "no single clear cause"
    return text + (f" (despite {', '.join(despite)})" if despite else "")


def anchor_to_sectors(a, delta, lap_a, lap_b):
    # Distance from integrated speed drifts a few metres. Official sector times are exact,
    # so shift the delta to match them at each sector line (in place). Returns the errors found.
    sa, sb = lap_a.get("sectors"), lap_b.get("sectors")
    if not sa or not sb or None in sa + sb:
        return []
    ds, fix, errors = [0.0], [0.0], []
    for i in range(1, len(sa)):
        d = float(np.interp(sum(sa[:i]), a["t"], a["d"]))
        official = sum(sb[:i]) - sum(sa[:i])
        ours = float(np.interp(d, a["d"], delta))
        ds.append(d)
        fix.append(official - ours)
        errors.append({"sector": i, "at_m": d, "official_s": official, "error_s": ours - official})
    ds.append(a["d"][-1])
    fix.append(0.0)
    delta += np.interp(a["d"], ds, fix)
    return errors


def compare(lap_a, lap_b):
    length = add_distance(lap_a)["d"][-1]   # A is the reference
    a = to_grid(lap_a, length)
    v = smooth(a["speed"])
    apexes = find_corners(v)
    b = to_grid(lap_b, length)
    delta = b["t"] - a["t"]                 # > 0: B is behind A at this point
    sector_check = anchor_to_sectors(a, delta, lap_a, lap_b)

    # Corner zone starts at the fastest point before its apex (end of the straight)
    starts = [int(np.argmax(v[:apexes[0]]))]
    for p, q in zip(apexes[:-1], apexes[1:]):
        starts.append(p + int(np.argmax(v[p:q])))
    ends = starts[1:] + [len(v) - 1]

    corners = []
    for n, (lo, apex, hi) in enumerate(zip(starts, apexes, ends), 1):
        # Measured between straights, where the delta is most reliable
        diff = delta[hi] - delta[lo]
        if n == len(apexes):  # last corner's exit wraps onto the start straight
            diff += delta[starts[0]]
        sa, sb = corner_stats(a, lo, apex, hi), corner_stats(b, lo, apex, hi)
        fast, slow = (lap_a, lap_b) if diff > 0 else (lap_b, lap_a)
        fs, ss = (sa, sb) if diff > 0 else (sb, sa)
        corners.append({
            "corner": n,
            "apex_m": float(a["d"][apex]),
            "time_diff_s": float(diff),
            "faster": fast["driver"],
            "why": explain(reasons(fs, ss)),
            "a": sa, "b": sb,
        })

    return {"a": a, "b": b, "delta": delta, "length_m": float(length), "corners": corners,
            "lap_a": lap_a, "lap_b": lap_b, "sector_check": sector_check}


def report(res):
    A, B = res["lap_a"], res["lap_b"]
    gap = B["lap_time"] - A["lap_time"]
    lines = [f"{A['driver']} {fmt_lap(A['lap_time'])}  vs  {B['driver']} {fmt_lap(B['lap_time'])}"
             f"  (gap {gap:+.3f} s, track {res['length_m']:.0f} m)"]
    if res["sector_check"]:
        worst = max(abs(e["error_s"]) for e in res["sector_check"])
        lines.append(f"Delta checked against official sector times: max error {worst:.3f} s, corrected")
    lines.append("")
    for c in sorted(res["corners"], key=lambda c: -abs(c["time_diff_s"])):
        if abs(c["time_diff_s"]) < 0.01:
            continue
        slow = B["driver"] if c["faster"] == A["driver"] else A["driver"]
        lines.append(f"C{c['corner']:<2} @ {c['apex_m']:>4.0f} m  {slow} loses {abs(c['time_diff_s']):.3f} s "
                     f" -  {c['faster']}: {c['why']}")
    return "\n".join(lines)


def fmt_lap(s):
    return f"{int(s // 60)}:{s % 60:06.3f}"
