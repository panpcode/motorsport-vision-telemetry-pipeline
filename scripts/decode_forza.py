"""
Decodes Forza Motorsport "Data Out" packets (recorded by record_udp_telemetry.py) into telemetry.csv.

    python scripts/decode_forza.py sample-data/forza/<session>

Packet layout: Forza Motorsport 2023 (331 bytes) and Forza Motorsport 7 "Car Dash" (311 bytes).
Signs follow the rest of the project: yaw, steer, accel_lat + = left; slip + = moving right of heading.
"""
import argparse
import csv
import glob
import math
import os
import struct

import numpy as np

# name: (byte offset, struct type)
FIELDS = {
    "is_race_on": (0, "i"), "game_ms": (4, "I"), "rpm": (16, "f"),
    "acc_x": (20, "f"), "acc_z": (28, "f"),            # car space: x right, y up, z forward
    "vel_x": (32, "f"), "vel_z": (40, "f"),
    "ang_vel_y": (48, "f"), "yaw": (56, "f"),
    "pos_x": (232, "f"), "pos_z": (240, "f"),          # track space, metres (y is up)
    "speed": (244, "f"), "distance": (280, "f"),
    "last_lap": (288, "f"), "current_lap": (292, "f"), "lap": (300, "H"),
    "accel": (303, "B"), "brake": (304, "B"), "gear": (307, "B"), "steer": (308, "b"),
}
SIZES = {331: "Forza Motorsport (2023)", 311: "Forza Motorsport 7"}
COLUMNS = ["ts_ms", "lap", "lap_t", "last_lap_s", "distance_m", "speed_kmh", "throttle", "brake",
           "gear", "rpm", "steer", "x", "y", "yaw_rate_deg_s", "accel_long", "accel_lat",
           "heading_deg", "slip_angle_deg"]


def read_raw(path):
    """Yields (pc_time_ns, packet bytes) from the recorder's CSV."""
    with open(path) as f:
        next(f)  # header
        for line in f:
            ts, hexdata = line.rstrip().split(",")
            yield int(ts), bytes.fromhex(hexdata)


def unpack(data):
    return {k: struct.unpack_from("<" + t, data, off)[0] for k, (off, t) in FIELDS.items()}


def align_clock(recv_ms, game_ms, window_ms=2000):
    # Wi-Fi delays packets by a few ms (sometimes 50+). The game's own clock has no jitter,
    # so use it, shifted to the PC clock by the smallest delay seen in each 2 s window.
    game = game_ms.astype(float)
    off = recv_ms - game
    bucket = ((recv_ms - recv_ms[0]) // window_ms).astype(int)
    mins = np.full(bucket.max() + 1, np.inf)
    np.minimum.at(mins, bucket, off)
    return game + mins[bucket]


def decode(raw_path):
    rows, recv, sizes = [], [], {}
    for ts_ns, data in read_raw(raw_path):
        sizes[len(data)] = sizes.get(len(data), 0) + 1
        if len(data) not in SIZES:
            continue
        p = unpack(data)
        if p["is_race_on"]:  # 0 in menus
            rows.append(p)
            recv.append(ts_ns / 1e6)
    if not rows:
        raise SystemExit(f"no Forza packets in {raw_path} (packet sizes seen: {sizes}). "
                         f"Expected {', '.join(f'{n} bytes = {g}' for n, g in SIZES.items())}")

    ts = align_clock(np.array(recv), np.array([r["game_ms"] for r in rows]))
    out = []
    for i in np.argsort(ts, kind="stable"):  # UDP can arrive out of order
        t, p = ts[i], rows[i]
        moving = math.hypot(p["vel_x"], p["vel_z"]) > 5  # slip angle is noise when nearly stopped
        out.append({
            "ts_ms": round(t, 1), "lap": p["lap"], "lap_t": round(p["current_lap"], 4),
            "last_lap_s": round(p["last_lap"], 4), "distance_m": round(p["distance"], 2),
            "speed_kmh": round(p["speed"] * 3.6, 3),
            "throttle": round(p["accel"] / 2.55, 1), "brake": round(p["brake"] / 255, 3),
            "gear": p["gear"], "rpm": round(p["rpm"]), "steer": round(-p["steer"] / 127, 3),
            "x": round(p["pos_x"], 3), "y": round(p["pos_z"], 3),
            "yaw_rate_deg_s": round(-math.degrees(p["ang_vel_y"]), 3),
            "accel_long": round(p["acc_z"], 3), "accel_lat": round(-p["acc_x"], 3),
            "heading_deg": round(math.degrees(p["yaw"]), 2),
            "slip_angle_deg": round(math.degrees(math.atan2(p["vel_x"], p["vel_z"])), 3) if moving else "",
        })
    return out, sizes


def summary(rows, sizes):
    ts = np.array([r["ts_ms"] for r in rows])
    dur = (ts[-1] - ts[0]) / 1000
    print(f"packets: {sizes}  ->  {len(rows)} on track, {dur:.0f} s, {len(rows) / max(dur, 1e-9):.0f} Hz")

    # Lap times as the game reports them (LastLap in the first packet of the next lap)
    for prev, cur in zip(rows, rows[1:]):
        if cur["lap"] == prev["lap"] + 1:
            print(f"  lap {prev['lap'] + 1}: {int(cur['last_lap_s'] // 60)}:{cur['last_lap_s'] % 60:06.3f}")

    # Sign check: turning left (steer > 0) should mean yaw > 0
    fast = [(r["steer"], r["yaw_rate_deg_s"]) for r in rows if r["speed_kmh"] > 40]
    if len(fast) > 100:
        c = np.corrcoef(np.array(fast).T)[0, 1]
        print(f"steer vs yaw correlation {c:+.2f}" + ("  <- negative: a sign is wrong, check FIELDS" if c < 0 else ""))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("session", help="folder with telemetry_*.csv from record_udp_telemetry.py")
    args = p.parse_args()

    raws = sorted(glob.glob(os.path.join(args.session, "telemetry_*.csv")))
    if not raws:
        raise SystemExit(f"no telemetry_*.csv in {args.session}")
    rows, sizes = decode(raws[-1])
    out = os.path.join(args.session, "telemetry.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print(f"{raws[-1]} -> {out}")
    summary(rows, sizes)


if __name__ == "__main__":
    main()
