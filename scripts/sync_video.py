"""
Finds the exact video/telemetry offset and calibrates the camera, using the data itself.

    python scripts/sync_video.py sample-data/forza/<session>

Needs telemetry.csv (decode_forza.py) and events.jsonl (CV worker run with --obs-start).
1. Offset: the OBS file name gives the start to the second, and the capture card adds a delay.
   The yaw rate seen in the video is matched to the game's yaw rate (cross-correlation).
2. Camera: video yaw scales with focal length, video speed with focal length x camera height.
   Fitting both against the game gives the camera's real FOV and height.
Writes sync.json, which the CV worker reads with --calib. Run the worker again, then this again
to see the final accuracy.
"""
import argparse
import csv
import json
import math
import os

import numpy as np
from scipy.signal import lfilter

MAX_LAG_MS = 10_000


def load_telemetry(path):
    rows = list(csv.DictReader(open(path)))
    col = lambda k: np.array([float(r[k]) if r[k] != "" else np.nan for r in rows])
    return {k: col(k) for k in ("ts_ms", "speed_kmh", "yaw_rate_deg_s", "slip_angle_deg")}


def load_events(path, skip=10):
    ev = [json.loads(line) for line in open(path)][skip:]  # first frames: smoothing warms up
    col = lambda k: np.array([e[k] if e[k] is not None else np.nan for e in ev], float)
    return {"ts_ms": col("ts_ms"), "speed_kmh": col("speed_est_kmh"),
            "yaw_rate_deg_s": col("yaw_rate_deg_s"), "slip_angle_deg": col("slip_angle_deg")}


def as_seen_by_video(tel, key, ev_ts, lag, meta):
    """Game signal as the CV worker would report it if the video started `lag` ms later than assumed:
    sampled between two frames, then smoothed with the worker's own EMA."""
    half_frame = 500 * meta["stride"] / meta["fps"]
    g = np.interp(ev_ts + lag - half_frame, tel["ts_ms"], tel[key])
    a = meta["smooth"]
    return lfilter([1 - a], [1, -a], g, zi=[a * g[0]])[0]


def best_lag(ev, tel, meta):
    """Lag (ms) where video yaw matches the game's yaw best (|correlation|), coarse then fine."""
    yaw = ev["yaw_rate_deg_s"]
    ok = ~np.isnan(yaw)
    best = (0.0, 0)
    for lags in (range(-MAX_LAG_MS, MAX_LAG_MS + 1, 50), None):
        if lags is None:
            lags = range(best[1] - 50, best[1] + 51, 2)
        for lag in lags:
            t = ev["ts_ms"] + lag
            inside = ok & (t >= tel["ts_ms"][0]) & (t <= tel["ts_ms"][-1])
            if inside.mean() < 0.5:
                continue
            g = as_seen_by_video(tel, "yaw_rate_deg_s", ev["ts_ms"], lag, meta)
            c = float(np.corrcoef(yaw[inside], g[inside])[0, 1])
            if abs(c) > abs(best[0]):
                best = (c, lag)
    return best


def slope(est, true, mask):
    # Least squares through the origin: est = k * true
    e, t = est[mask], true[mask]
    return float((e * t).sum() / (t * t).sum())


def accuracy(name, est, true):
    ok = ~np.isnan(est) & ~np.isnan(true)
    if ok.sum() < 20:
        return None
    e, t = est[ok], true[ok]
    r = {"mae": round(float(np.abs(e - t).mean()), 2), "corr": round(float(np.corrcoef(e, t)[0, 1]), 2),
         "true_mean_abs": round(float(np.abs(t).mean()), 2), "n": int(ok.sum())}
    print(f"  {name:6s} MAE {r['mae']:6.2f}  corr {r['corr']:5.2f}  (true mean |x| {r['true_mean_abs']:.1f}, n={r['n']})")
    return r


def main():
    p = argparse.ArgumentParser()
    p.add_argument("session", help="folder with telemetry.csv, events.jsonl, events.meta.json")
    args = p.parse_args()
    path = lambda name: os.path.join(args.session, name)

    tel = load_telemetry(path("telemetry.csv"))
    ev = load_events(path("events.jsonl"))
    meta = json.load(open(path("events.meta.json")))
    if meta["video_start_ms"] is None:
        raise SystemExit("events were made without --obs-start, run make forza-cv")
    if ev["ts_ms"][-1] < tel["ts_ms"][0] - MAX_LAG_MS or ev["ts_ms"][0] > tel["ts_ms"][-1] + MAX_LAG_MS:
        raise SystemExit("video and telemetry don't overlap in time: same session? Mac clock changed?")

    # 1. Offset
    corr, lag = best_lag(ev, tel, meta)
    offset = meta["offset_ms"] + lag
    sign = 1 if corr > 0 else -1
    print(f"video vs game yaw: best match {lag:+d} ms from the current offset (corr {corr:+.2f})")
    print(f"  -> video starts {offset:+.0f} ms after the OBS file name time")
    if abs(corr) < 0.3:
        print("  weak match: few corners in the clip, or the video is from another session")
    if sign < 0:
        print("  video yaw has the opposite sign of the game's: check the decoder's sign")

    # 2. Camera, comparing like with like (game signals timed and smoothed as the video sees them)
    at = lambda k: as_seen_by_video(tel, k, ev["ts_ms"], lag, meta)
    yaw_t, spd_t = at("yaw_rate_deg_s"), at("speed_kmh")
    slip_t = np.interp(ev["ts_ms"] + lag, tel["ts_ms"], tel["slip_angle_deg"])  # has gaps, not smoothed
    yaw_e, spd_e = sign * ev["yaw_rate_deg_s"], ev["speed_kmh"]
    k_yaw = slope(yaw_e, yaw_t, ~np.isnan(yaw_e) & (np.abs(yaw_t) > 3))
    k_spd = slope(spd_e, spd_t, ~np.isnan(spd_e) & (spd_t > 30))
    hfov = math.degrees(2 * math.atan(math.tan(math.radians(meta["hfov"]) / 2) / k_yaw))
    cam_h = meta["cam_height"] / (k_yaw * k_spd)
    hfov, cam_h = float(np.clip(hfov, 30, 140)), float(np.clip(cam_h, 0.1, 3.0))
    print(f"camera: hfov {meta['hfov']:.1f} -> {hfov:.1f} deg, height {meta['cam_height']:.2f} -> {cam_h:.2f} m"
          f"  (video/game: yaw x{k_yaw:.2f}, speed x{k_spd:.2f})")

    print("accuracy of this run (video vs game):")
    acc = {"speed": accuracy("speed", spd_e, spd_t),
           "yaw": accuracy("yaw", yaw_e, yaw_t),
           "slip": accuracy("slip", ev["slip_angle_deg"], slip_t)}
    if abs(k_yaw - 1) > 0.05 or abs(k_spd - 1) > 0.05:
        print("calibration changed: run make forza-cv again (it reads sync.json), then this again")

    out = {"offset_ms": round(offset, 1), "hfov": round(hfov, 2), "cam_height": round(cam_h, 3),
           "yaw_corr": round(corr, 3), "accuracy": acc}
    json.dump(out, open(path("sync.json"), "w"), indent=2)
    print(f"wrote {path('sync.json')}")


if __name__ == "__main__":
    main()
